"""
Messaging Effectiveness Model

2-stage hierarchical Bayesian logistic regression for email campaign effectiveness.
Funnel: Send -> Open -> Click

Model Structure:
- Stage 1: P(Open | features) - Logistic regression with campaign random effects
- Stage 2: P(Click | Open, features) - Conditional logistic regression
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import arviz as az
import numpy as np
import pymc as pm

from src.bayesian_models.base_model import BaseBayesianModel
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class MessagingEffectivenessModel(BaseBayesianModel):
    """
    2-Stage Hierarchical Bayesian Model for Email Campaign Effectiveness

    This model uses partial pooling through campaign random effects to share
    information across campaigns while allowing individual variation.

    Key Features:
    - Non-centered parameterization for better MCMC sampling
    - Message type, location, and monthly effects
    - Offer characteristics (savings, cost, kwh) as continuous predictors
    """

    def __init__(self, model_dir: Optional[Path] = None):
        if model_dir is None:
            model_dir = Path(__file__).parent
        super().__init__(model_dir)

        # Data paths
        self.data_dir = PROJECT_ROOT / 'data' / 'processed'

        # Store trace and data for predictions
        self.trace = None
        self.data = None
        self.prior_config = None

    def load_data(self, data_file: Optional[str] = None, use_full: bool = False) -> Dict[str, Any]:
        """
        Load prepared data from pickle file.

        Args:
            data_file: Path to pickle file. If None, uses default location.
            use_full: If True, loads full dataset; otherwise loads POC subset.

        Returns:
            Dictionary with prepared model data
        """
        if data_file:
            data_path = Path(data_file)
        else:
            dataset_type = 'full' if use_full else 'poc'
            data_path = self.data_dir / f'messaging_{dataset_type}_data.pkl'

        if not data_path.exists():
            raise FileNotFoundError(
                f"Data file not found: {data_path}\n"
                f"Run 'python src/bayesian_scripts_orig/prepare_messaging_data.py' first."
            )

        logger.info(f"Loading data from {data_path}")

        with open(data_path, 'rb') as f:
            data = pickle.load(f)

        # Validate required fields
        required_fields = [
            'n_campaigns', 'n_msg_types', 'n_locations',
            'campaign_idx', 'msg_type_idx', 'location_idx', 'month_idx',
            'opened', 'clicked', 'savings_std', 'monthly_cost_std', 'kwh_std'
        ]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields in data: {missing}")

        self.data = data
        logger.info(
            f"Loaded {data['n_records']} records, "
            f"{data['n_campaigns']} campaigns, "
            f"{data['n_msg_types']} message types"
        )

        return data

    def _build_model(self, data: Dict[str, Any], prior_config: Optional[Dict] = None) -> pm.Model:
        """Build the 2-stage hierarchical PyMC model."""
        # Load prior config from YAML if not provided
        if prior_config is None:
            prior_config = self.metadata.config.get('prior_config', {})
            if not prior_config:
                # Default prior configuration
                prior_config = {
                    'mu_alpha_open': {'mu': -3.0, 'sigma': 1.0},
                    'sigma_alpha_open': {'sigma': 0.5},
                    'mu_alpha_click': {'mu': -2.5, 'sigma': 1.0},
                    'sigma_alpha_click': {'sigma': 0.5},
                    'msg_type_effect': {'sigma': 0.5},
                    'location_effect': {'sigma': 0.3},
                    'month_effect': {'sigma': 0.2},
                    'offer_effect': {'sigma': 0.3}
                }

        self.prior_config = prior_config

        # Extract dimensions
        n_campaigns = data['n_campaigns']
        n_msg_types = data['n_msg_types']
        n_locations = data['n_locations']

        # Extract data arrays
        campaign_idx = data['campaign_idx']
        msg_type_idx = data['msg_type_idx']
        location_idx = data['location_idx']
        month_idx = data['month_idx']

        opened = data['opened']
        clicked = data['clicked']

        savings_std = data['savings_std']
        monthly_cost_std = data['monthly_cost_std']
        kwh_std = data['kwh_std']

        with pm.Model() as model:
            # ========================================
            # STAGE 1: OPEN RATE MODEL
            # ========================================

            # Population-level parameters (non-centered parameterization)
            mu_alpha_open = pm.Normal(
                'mu_alpha_open',
                mu=prior_config['mu_alpha_open']['mu'],
                sigma=prior_config['mu_alpha_open']['sigma']
            )
            sigma_alpha_open = pm.HalfNormal(
                'sigma_alpha_open',
                sigma=prior_config['sigma_alpha_open']['sigma']
            )

            # Campaign random effects (non-centered)
            z_alpha_open = pm.Normal('z_alpha_open', 0, 1, shape=n_campaigns)
            alpha_open = pm.Deterministic(
                'alpha_open',
                mu_alpha_open + z_alpha_open * sigma_alpha_open
            )

            # Message type effects
            msg_type_effect_open = pm.Normal(
                'msg_type_effect_open', 0,
                prior_config['msg_type_effect']['sigma'],
                shape=n_msg_types
            )

            # Location effects
            location_effect_open = pm.Normal(
                'location_effect_open', 0,
                prior_config['location_effect']['sigma'],
                shape=n_locations
            )

            # Temporal effects (monthly seasonality)
            month_effect_open = pm.Normal(
                'month_effect_open', 0,
                prior_config['month_effect']['sigma'],
                shape=12
            )

            # Offer characteristic effects
            beta_savings_open = pm.Normal(
                'beta_savings_open', 0, prior_config['offer_effect']['sigma']
            )
            beta_cost_open = pm.Normal(
                'beta_cost_open', 0, prior_config['offer_effect']['sigma']
            )
            beta_kwh_open = pm.Normal(
                'beta_kwh_open', 0, prior_config['offer_effect']['sigma']
            )

            # Linear predictor for open rate
            logit_open = (
                alpha_open[campaign_idx] +
                msg_type_effect_open[msg_type_idx] +
                location_effect_open[location_idx] +
                month_effect_open[month_idx] +
                beta_savings_open * savings_std +
                beta_cost_open * monthly_cost_std +
                beta_kwh_open * kwh_std
            )

            # Open probability
            p_open = pm.Deterministic('p_open', pm.math.sigmoid(logit_open))

            # Likelihood for open
            pm.Bernoulli('opened_obs', p=p_open, observed=opened)

            # ========================================
            # STAGE 2: CLICK RATE MODEL (conditional on opened)
            # ========================================

            # Filter to only opened emails
            opened_mask = opened == 1
            n_opened = int(opened.sum())

            if n_opened > 0:
                # Population-level parameters (non-centered)
                mu_alpha_click = pm.Normal(
                    'mu_alpha_click',
                    mu=prior_config['mu_alpha_click']['mu'],
                    sigma=prior_config['mu_alpha_click']['sigma']
                )
                sigma_alpha_click = pm.HalfNormal(
                    'sigma_alpha_click',
                    sigma=prior_config['sigma_alpha_click']['sigma']
                )

                # Campaign random effects (non-centered)
                z_alpha_click = pm.Normal('z_alpha_click', 0, 1, shape=n_campaigns)
                alpha_click = pm.Deterministic(
                    'alpha_click',
                    mu_alpha_click + z_alpha_click * sigma_alpha_click
                )

                # Message type effects
                msg_type_effect_click = pm.Normal(
                    'msg_type_effect_click', 0,
                    prior_config['msg_type_effect']['sigma'],
                    shape=n_msg_types
                )

                # Location effects
                location_effect_click = pm.Normal(
                    'location_effect_click', 0,
                    prior_config['location_effect']['sigma'],
                    shape=n_locations
                )

                # Offer characteristic effects
                beta_savings_click = pm.Normal(
                    'beta_savings_click', 0, prior_config['offer_effect']['sigma']
                )
                beta_cost_click = pm.Normal(
                    'beta_cost_click', 0, prior_config['offer_effect']['sigma']
                )
                beta_kwh_click = pm.Normal(
                    'beta_kwh_click', 0, prior_config['offer_effect']['sigma']
                )

                # Linear predictor for click rate (only for opened emails)
                logit_click = (
                    alpha_click[campaign_idx[opened_mask]] +
                    msg_type_effect_click[msg_type_idx[opened_mask]] +
                    location_effect_click[location_idx[opened_mask]] +
                    beta_savings_click * savings_std[opened_mask] +
                    beta_cost_click * monthly_cost_std[opened_mask] +
                    beta_kwh_click * kwh_std[opened_mask]
                )

                # Click probability (conditional on opened)
                p_click = pm.Deterministic('p_click', pm.math.sigmoid(logit_click))

                # Likelihood for click (conditional on opened)
                pm.Bernoulli('clicked_obs', p=p_click, observed=clicked[opened_mask])

                # ========================================
                # DERIVED QUANTITIES
                # ========================================

                # Average open rate per campaign
                avg_p_open_campaign = pm.Deterministic(
                    'avg_p_open_campaign', pm.math.sigmoid(alpha_open)
                )

                # Average click rate per campaign (conditional)
                avg_p_click_campaign = pm.Deterministic(
                    'avg_p_click_campaign', pm.math.sigmoid(alpha_click)
                )

                # End-to-end conversion rate estimate per campaign
                pm.Deterministic(
                    'conversion_rate_campaign',
                    avg_p_open_campaign * avg_p_click_campaign
                )

        return model

    def train(self, data: Dict[str, Any], draws: int = 2000, tune: int = 1000,
              chains: int = 4, target_accept: float = 0.95,
              random_seed: int = 42, **kwargs) -> Dict[str, Any]:
        """
        Train the messaging effectiveness model using MCMC sampling.

        Args:
            data: Prepared data dictionary from load_data()
            draws: Number of samples per chain
            tune: Number of tuning samples
            chains: Number of MCMC chains
            target_accept: Target acceptance rate
            random_seed: Random seed for reproducibility

        Returns:
            Dictionary with training results
        """
        self.ensure_output_dirs()
        logger.info("Building messaging effectiveness model...")

        model = self._build_model(data)

        logger.info(f"Sampling: {draws} draws, {tune} tuning, {chains} chains")

        with model:
            trace = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                target_accept=target_accept,
                random_seed=random_seed,
                return_inferencedata=True
            )

        self.trace = trace
        self.data = data

        # Save trace
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        trace_path = self.traces_dir / f'trace_{timestamp}.nc'
        trace.to_netcdf(trace_path)
        logger.info(f"Trace saved to {trace_path}")

        # Compute diagnostics
        diagnostics = self._compute_diagnostics(trace)

        # Compute effect summaries
        effects = self._compute_effect_summaries(trace, data)

        # Generate and save reports
        self._save_reports(trace, data, diagnostics, effects, timestamp)

        # Generate visualizations
        self._generate_visualizations(trace, data, timestamp)

        results = {
            'trace_path': str(trace_path),
            'diagnostics': diagnostics,
            'effects': effects,
            'n_records': data['n_records'],
            'n_campaigns': data['n_campaigns'],
            'n_msg_types': data['n_msg_types'],
            'open_rate': float(data['opened'].mean()),
            'click_rate_given_open': float(
                data['clicked'][data['opened'] == 1].mean()
            ) if data['opened'].sum() > 0 else 0.0
        }

        return results

    def _compute_diagnostics(self, trace: az.InferenceData) -> Dict[str, Any]:
        """Compute MCMC diagnostics."""
        summary = az.summary(trace, var_names=[
            'mu_alpha_open', 'sigma_alpha_open',
            'mu_alpha_click', 'sigma_alpha_click',
            'beta_savings_open', 'beta_cost_open', 'beta_kwh_open',
            'beta_savings_click', 'beta_cost_click', 'beta_kwh_click'
        ])

        return {
            'r_hat_max': float(summary['r_hat'].max()),
            'ess_bulk_min': float(summary['ess_bulk'].min()),
            'ess_tail_min': float(summary['ess_tail'].min()),
            'divergences': int(trace.sample_stats['diverging'].sum().values),
            'summary': summary.to_dict()
        }

    def _compute_effect_summaries(self, trace: az.InferenceData,
                                   data: Dict[str, Any]) -> Dict[str, Any]:
        """Compute summaries for all effect types."""
        posterior = trace.posterior
        effects = {}

        # Open stage effects
        effects['open'] = {
            'population_intercept': self._summarize_var(posterior, 'mu_alpha_open'),
            'between_campaign_sd': self._summarize_var(posterior, 'sigma_alpha_open'),
            'savings_effect': self._summarize_var(posterior, 'beta_savings_open'),
            'cost_effect': self._summarize_var(posterior, 'beta_cost_open'),
            'kwh_effect': self._summarize_var(posterior, 'beta_kwh_open'),
        }

        # Click stage effects
        if 'mu_alpha_click' in posterior:
            effects['click'] = {
                'population_intercept': self._summarize_var(posterior, 'mu_alpha_click'),
                'between_campaign_sd': self._summarize_var(posterior, 'sigma_alpha_click'),
                'savings_effect': self._summarize_var(posterior, 'beta_savings_click'),
                'cost_effect': self._summarize_var(posterior, 'beta_cost_click'),
                'kwh_effect': self._summarize_var(posterior, 'beta_kwh_click'),
            }

        # Message type effects
        msg_type_names = data.get('msg_type_names', {})
        if 'msg_type_effect_open' in posterior:
            open_effects = posterior['msg_type_effect_open'].values.reshape(-1, data['n_msg_types'])
            effects['message_types_open'] = {
                msg_type_names.get(i, f'type_{i}'): {
                    'mean': float(open_effects[:, i].mean()),
                    'hdi_lower': float(np.percentile(open_effects[:, i], 5.5)),
                    'hdi_upper': float(np.percentile(open_effects[:, i], 94.5)),
                    'odds_ratio': float(np.exp(open_effects[:, i].mean()))
                }
                for i in range(data['n_msg_types'])
            }

        # Campaign rankings
        if 'avg_p_open_campaign' in posterior:
            campaign_names = data.get('campaign_names', {})
            open_rates = posterior['avg_p_open_campaign'].values.reshape(-1, data['n_campaigns'])
            effects['campaign_rankings'] = {
                campaign_names.get(i, f'campaign_{i}'): {
                    'mean_open_rate': float(open_rates[:, i].mean()),
                    'hdi_lower': float(np.percentile(open_rates[:, i], 5.5)),
                    'hdi_upper': float(np.percentile(open_rates[:, i], 94.5))
                }
                for i in range(data['n_campaigns'])
            }

        return effects

    def _summarize_var(self, posterior, var_name: str) -> Dict[str, float]:
        """Compute summary statistics for a variable."""
        samples = posterior[var_name].values.flatten()
        return {
            'mean': float(samples.mean()),
            'std': float(samples.std()),
            'hdi_lower': float(np.percentile(samples, 5.5)),
            'hdi_upper': float(np.percentile(samples, 94.5)),
            'odds_ratio': float(np.exp(samples.mean()))
        }

    def _save_reports(self, trace: az.InferenceData, data: Dict[str, Any],
                      diagnostics: Dict, effects: Dict, timestamp: str) -> None:
        """Save summary reports."""
        # Save diagnostics
        diag_path = self.reports_dir / f'diagnostics_{timestamp}.json'
        with open(diag_path, 'w') as f:
            # Convert numpy types for JSON serialization
            diag_serializable = {
                k: v if not isinstance(v, dict) else v
                for k, v in diagnostics.items()
                if k != 'summary'
            }
            json.dump(diag_serializable, f, indent=2)

        # Save effects summary
        effects_path = self.reports_dir / f'effects_{timestamp}.json'
        with open(effects_path, 'w') as f:
            json.dump(effects, f, indent=2, default=str)

        # Save full ArviZ summary
        summary = az.summary(trace)
        summary_path = self.reports_dir / f'full_summary_{timestamp}.csv'
        summary.to_csv(summary_path)

        logger.info(f"Reports saved to {self.reports_dir}")

    def _generate_visualizations(self, trace: az.InferenceData,
                                  data: Dict[str, Any], timestamp: str) -> None:
        """Generate and save model visualizations."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            # Trace plots for key parameters
            fig, axes = plt.subplots(4, 2, figsize=(12, 12))
            az.plot_trace(
                trace,
                var_names=['mu_alpha_open', 'sigma_alpha_open',
                           'beta_savings_open', 'beta_cost_open'],
                axes=axes
            )
            plt.tight_layout()
            trace_path = self.diagrams_dir / f'trace_open_{timestamp}.png'
            plt.savefig(trace_path, dpi=150)
            plt.close()

            # Forest plot for message type effects
            if 'msg_type_effect_open' in trace.posterior:
                fig, ax = plt.subplots(figsize=(10, 6))
                az.plot_forest(
                    trace,
                    var_names=['msg_type_effect_open'],
                    combined=True,
                    ax=ax
                )
                plt.title('Message Type Effects on Open Rate')
                forest_path = self.diagrams_dir / f'forest_msg_types_{timestamp}.png'
                plt.savefig(forest_path, dpi=150, bbox_inches='tight')
                plt.close()

            # Campaign rankings
            if 'avg_p_open_campaign' in trace.posterior:
                fig, ax = plt.subplots(figsize=(12, 8))
                az.plot_forest(
                    trace,
                    var_names=['avg_p_open_campaign'],
                    combined=True,
                    ax=ax
                )
                plt.title('Campaign Open Rates with Credible Intervals')
                campaign_path = self.diagrams_dir / f'campaign_rankings_{timestamp}.png'
                plt.savefig(campaign_path, dpi=150, bbox_inches='tight')
                plt.close()

            logger.info(f"Visualizations saved to {self.diagrams_dir}")

        except ImportError as e:
            logger.warning(f"Could not generate visualizations: {e}")

    def get_dynamic_options(self) -> Dict[str, list]:
        """
        Get dynamic options for select fields (e.g., campaign_id).

        Returns:
            Dictionary mapping parameter names to their available options.
        """
        options = {}

        # Try to load data to get campaign names
        try:
            if self.data is None:
                self.data = self.load_data()

            campaign_names = self.data.get('campaign_names', {})
            # Create friendly display names from full campaign IDs
            campaign_options = ['__all__']  # Add "All" option first
            for idx in sorted(campaign_names.keys()):
                campaign_options.append(campaign_names[idx])

            options['campaign_id'] = campaign_options

        except FileNotFoundError:
            logger.warning("Could not load data for dynamic options")
            options['campaign_id'] = ['__all__']

        return options

    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict campaign performance using the trained model.

        Args:
            inference_params: Dictionary with campaign parameters

        Returns:
            Predicted open rate, click rate, and conversion rate with credible intervals
        """
        # Load trace if not in memory
        if self.trace is None:
            trace_path = self.get_latest_trace()
            if trace_path is None:
                return {'error': 'No trained model found. Run training first.', 'success': False}
            self.trace = az.from_netcdf(trace_path)

        # Load data for lookups if needed
        if self.data is None:
            try:
                self.data = self.load_data()
            except FileNotFoundError:
                return {'error': 'Data file not found.', 'success': False}

        posterior = self.trace.posterior
        hdi_prob = float(inference_params.get('credible_interval', 0.89))

        # Get campaign index
        campaign_id = inference_params.get('campaign_id')

        # Handle "All" campaigns - use population-level parameters
        if campaign_id == '__all__':
            return self._predict_all_campaigns(posterior, hdi_prob)

        campaign_lookup = self.data.get('campaign_lookup', {})

        if campaign_id not in campaign_lookup:
            return {
                'error': f'Campaign not found: {campaign_id}',
                'available_campaigns': list(campaign_lookup.keys()),
                'success': False
            }

        campaign_idx = campaign_lookup[campaign_id]

        # Extract campaign-specific predictions
        open_rate_samples = posterior['avg_p_open_campaign'].values[:, :, campaign_idx].flatten()
        open_rate_mean = float(open_rate_samples.mean())
        open_rate_hdi = az.hdi(open_rate_samples, hdi_prob=hdi_prob)

        result = {
            'success': True,
            'campaign_id': campaign_id,
            'open_rate': {
                'mean': open_rate_mean,
                'hdi_lower': float(open_rate_hdi[0]),
                'hdi_upper': float(open_rate_hdi[1]),
                'hdi_prob': hdi_prob
            }
        }

        # Click rate (if available)
        if 'avg_p_click_campaign' in posterior:
            click_rate_samples = posterior['avg_p_click_campaign'].values[:, :, campaign_idx].flatten()
            click_rate_mean = float(click_rate_samples.mean())
            click_rate_hdi = az.hdi(click_rate_samples, hdi_prob=hdi_prob)

            result['click_rate_given_open'] = {
                'mean': click_rate_mean,
                'hdi_lower': float(click_rate_hdi[0]),
                'hdi_upper': float(click_rate_hdi[1]),
                'hdi_prob': hdi_prob
            }

            # Conversion rate
            conversion_samples = posterior['conversion_rate_campaign'].values[:, :, campaign_idx].flatten()
            conversion_mean = float(conversion_samples.mean())
            conversion_hdi = az.hdi(conversion_samples, hdi_prob=hdi_prob)

            result['conversion_rate'] = {
                'mean': conversion_mean,
                'hdi_lower': float(conversion_hdi[0]),
                'hdi_upper': float(conversion_hdi[1]),
                'hdi_prob': hdi_prob
            }

        return result

    def _predict_all_campaigns(self, posterior, hdi_prob: float) -> Dict[str, Any]:
        """
        Predict average performance across all campaigns using population-level parameters.

        Uses mu_alpha_open and mu_alpha_click (population intercepts) to compute
        the expected performance for a "typical" campaign.
        """
        # Population-level open rate: sigmoid(mu_alpha_open)
        mu_open_samples = posterior['mu_alpha_open'].values.flatten()
        pop_open_rate = 1 / (1 + np.exp(-mu_open_samples))  # sigmoid
        open_rate_mean = float(pop_open_rate.mean())
        open_rate_hdi = az.hdi(pop_open_rate, hdi_prob=hdi_prob)

        result = {
            'success': True,
            'campaign_id': 'All Campaigns (Population Average)',
            'description': 'Expected performance for a typical campaign based on population-level parameters',
            'open_rate': {
                'mean': open_rate_mean,
                'hdi_lower': float(open_rate_hdi[0]),
                'hdi_upper': float(open_rate_hdi[1]),
                'hdi_prob': hdi_prob
            }
        }

        # Population-level click rate (if available)
        if 'mu_alpha_click' in posterior:
            mu_click_samples = posterior['mu_alpha_click'].values.flatten()
            pop_click_rate = 1 / (1 + np.exp(-mu_click_samples))  # sigmoid
            click_rate_mean = float(pop_click_rate.mean())
            click_rate_hdi = az.hdi(pop_click_rate, hdi_prob=hdi_prob)

            result['click_rate_given_open'] = {
                'mean': click_rate_mean,
                'hdi_lower': float(click_rate_hdi[0]),
                'hdi_upper': float(click_rate_hdi[1]),
                'hdi_prob': hdi_prob
            }

            # Population conversion rate
            pop_conversion = pop_open_rate * pop_click_rate
            conversion_mean = float(pop_conversion.mean())
            conversion_hdi = az.hdi(pop_conversion, hdi_prob=hdi_prob)

            result['conversion_rate'] = {
                'mean': conversion_mean,
                'hdi_lower': float(conversion_hdi[0]),
                'hdi_upper': float(conversion_hdi[1]),
                'hdi_prob': hdi_prob
            }

        # Add campaign variation info
        if 'sigma_alpha_open' in posterior:
            sigma_samples = posterior['sigma_alpha_open'].values.flatten()
            result['campaign_variation'] = {
                'open_rate_sd': float(sigma_samples.mean()),
                'interpretation': f'Campaigns vary by ~{sigma_samples.mean():.2f} on logit scale'
            }

        return result

    def get_campaign_rankings(self, metric: str = 'open_rate',
                               top_n: int = 10) -> Dict[str, Any]:
        """
        Get ranked list of campaigns by performance metric.

        Args:
            metric: 'open_rate', 'click_rate', or 'conversion_rate'
            top_n: Number of top campaigns to return

        Returns:
            Ranked campaigns with credible intervals
        """
        if self.trace is None:
            trace_path = self.get_latest_trace()
            if trace_path is None:
                return {'error': 'No trained model found.'}
            self.trace = az.from_netcdf(trace_path)

        if self.data is None:
            self.data = self.load_data()

        posterior = self.trace.posterior
        campaign_names = self.data.get('campaign_names', {})

        var_map = {
            'open_rate': 'avg_p_open_campaign',
            'click_rate': 'avg_p_click_campaign',
            'conversion_rate': 'conversion_rate_campaign'
        }

        var_name = var_map.get(metric, 'avg_p_open_campaign')

        if var_name not in posterior:
            return {'error': f'Metric {metric} not available in trained model.'}

        samples = posterior[var_name].values.reshape(-1, self.data['n_campaigns'])
        means = samples.mean(axis=0)

        # Sort by mean performance
        sorted_indices = np.argsort(means)[::-1][:top_n]

        rankings = []
        for rank, idx in enumerate(sorted_indices, 1):
            campaign_samples = samples[:, idx]
            hdi = az.hdi(campaign_samples, hdi_prob=0.89)
            rankings.append({
                'rank': rank,
                'campaign_id': campaign_names.get(idx, f'campaign_{idx}'),
                'mean': float(means[idx]),
                'hdi_lower': float(hdi[0]),
                'hdi_upper': float(hdi[1])
            })

        return {
            'metric': metric,
            'rankings': rankings,
            'n_campaigns': self.data['n_campaigns']
        }
