"""
Model 04: Campaign Treatment Effects Model

Hierarchical Bayesian model for estimating causal effects of campaign
message types on click behavior.

Key Features:
- Multi-label treatment: message_types (6 categories, additive effects)
- Confounding control: income, energy_burden
- Random effects: county intercepts (partial pooling)
- Causal identification through adjustment set

Research Question:
"Which campaign message types are most effective at driving clicks,
controlling for participant characteristics and geography?"

Expected Effects (from prior knowledge):
- personalized_qualified: Strongest positive (personalization works)
- urgency_deadline: Positive (creates action pressure)
- savings_financial: Positive (financial motivation)
- motivational_struggle: Positive (empathy-based)
- relief_reassurance: Slight positive (comfort messaging)
- informational: Baseline/reference (pure information)
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt

from src.bayesian_models.base_model import BaseBayesianModel
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

# Message type codes matching classifications.json
MESSAGE_TYPES = [
    'urgency_deadline',
    'savings_financial',
    'relief_reassurance',
    'informational',
    'personalized_qualified',
    'motivational_struggle'
]


class CampaignTreatmentEffectsModel(BaseBayesianModel):
    """Model 4: Campaign Treatment Effects for click prediction."""

    def __init__(self, model_dir: Optional[Path] = None):
        """Initialize the model."""
        if model_dir is None:
            model_dir = Path(__file__).parent
        super().__init__(model_dir)

        self.pymc_model = None
        self.trace = None
        self._scaler_params = None
        self._county_mapping = None
        self._message_type_indices = {mt: i for i, mt in enumerate(MESSAGE_TYPES)}

    def load_data(self, **kwargs) -> Dict[str, np.ndarray]:
        """
        Load and prepare data for model training.

        Uses campaign_exposures collection joined with participants to create
        observation-level dataset with treatment (message_types) and confounders.

        Returns:
            Dictionary with prepared arrays for model training
        """
        from src.tools.mongo import get_campaign_db

        db = get_campaign_db()
        min_campaigns_per_county = kwargs.get('min_campaigns_per_county', 10)

        # Step 1: Load campaign message_types
        logger.info("Loading campaign message_types...")
        campaigns = list(db.campaigns.find(
            {'message_types': {'$exists': True, '$ne': []}},
            {'campaign_id': 1, 'message_types': 1}
        ))
        campaign_types = {c['campaign_id']: c['message_types'] for c in campaigns}
        logger.info(f"Loaded {len(campaign_types)} campaigns with message_types")

        # Step 2: Build participant lookup (email -> demographics)
        logger.info("Building participant demographics lookup...")
        participant_lookup = {}
        for doc in db.participants.find(
            {'linkage.county_key': {'$exists': True},
             'demographics.income_level': {'$type': 'number'}},
            {'email': 1, 'demographics.total_energy_burden': 1,
             'demographics.income_level': 1, 'linkage.county_key': 1}
        ):
            email = doc.get('email')
            if not email:
                continue
            demographics = doc.get('demographics', {}) or {}
            linkage = doc.get('linkage', {}) or {}

            energy_burden = demographics.get('total_energy_burden')
            income_level = demographics.get('income_level')
            county_key = linkage.get('county_key')

            if energy_burden is not None and income_level is not None and county_key:
                # Normalize county name (remove "County" suffix if present)
                county = county_key[:-6] if county_key.endswith('County') else county_key
                participant_lookup[email] = {
                    'energy_burden': float(energy_burden),
                    'income': float(income_level),
                    'county': county
                }
        logger.info(f"Built lookup for {len(participant_lookup)} participants with demographics")

        # Step 3: Load campaign_exposures and join with participant data
        logger.info("Loading campaign exposures...")
        data_rows = []
        exposures_checked = 0

        for exposure in db.campaign_exposures.find(
            {'channel': 'email'},  # Focus on email campaigns for now
            {'participant_id': 1, 'campaign_id': 1, 'email_clicked': 1}
        ):
            exposures_checked += 1
            participant_id = exposure.get('participant_id')
            campaign_id = exposure.get('campaign_id')

            # Skip if campaign has no message_types
            if campaign_id not in campaign_types:
                continue

            # Skip if participant not in lookup (missing demographics)
            if participant_id not in participant_lookup:
                continue

            participant = participant_lookup[participant_id]
            message_types = campaign_types[campaign_id]
            clicked = 1 if exposure.get('email_clicked', False) else 0

            # Create multi-hot encoding for message types
            msg_encoding = [1 if mt in message_types else 0 for mt in MESSAGE_TYPES]

            data_rows.append({
                'participant_id': participant_id,
                'campaign_id': campaign_id,
                'energy_burden': participant['energy_burden'],
                'income': participant['income'],
                'county': participant['county'],
                'clicked': clicked,
                **{f'has_{mt}': enc for mt, enc in zip(MESSAGE_TYPES, msg_encoding)}
            })

        logger.info(f"Checked {exposures_checked} exposures, matched {len(data_rows)}")

        df = pd.DataFrame(data_rows)
        logger.info(f"Created {len(df)} observations (participant x campaign)")

        if len(df) == 0:
            raise ValueError("No valid observations found. Check database fields.")

        # Step 4: Filter counties with sufficient data
        county_counts = df.groupby('county').size()
        valid_counties = county_counts[county_counts >= min_campaigns_per_county].index.tolist()
        df = df[df['county'].isin(valid_counties)]
        logger.info(f"After county filter: {len(df)} observations in {len(valid_counties)} counties")

        # Step 5: Create county index mapping
        self._county_mapping = {county: i for i, county in enumerate(sorted(valid_counties))}
        df['county_idx'] = df['county'].map(self._county_mapping)

        # Step 6: Standardize continuous predictors
        burden_mean, burden_std = df['energy_burden'].mean(), df['energy_burden'].std()
        income_mean, income_std = df['income'].mean(), df['income'].std()

        self._scaler_params = {
            'burden_mean': float(burden_mean),
            'burden_std': float(burden_std),
            'income_mean': float(income_mean),
            'income_std': float(income_std),
            'county_mapping': self._county_mapping
        }

        # Log summary statistics
        click_rate = df['clicked'].mean()
        logger.info(f"Overall click rate: {click_rate:.2%}")
        logger.info(f"Counties: {len(valid_counties)}")
        logger.info(f"Unique participants: {df['participant_id'].nunique()}")
        logger.info(f"Unique campaigns: {df['campaign_id'].nunique()}")

        # Log message type frequencies
        for mt in MESSAGE_TYPES:
            freq = df[f'has_{mt}'].mean()
            click_when_has = df[df[f'has_{mt}'] == 1]['clicked'].mean()
            logger.info(f"  {mt}: {freq:.1%} of campaigns, "
                       f"click rate when present: {click_when_has:.2%}")

        # Prepare model data
        data = {
            'energy_burden': ((df['energy_burden'] - burden_mean) / burden_std).values,
            'income': ((df['income'] - income_mean) / income_std).values,
            'county_idx': df['county_idx'].values.astype(int),
            'n_counties': len(valid_counties),
            'y_clicked': df['clicked'].astype(int).values,
        }

        # Add message type indicators
        for mt in MESSAGE_TYPES:
            data[f'has_{mt}'] = df[f'has_{mt}'].values.astype(int)

        return data

    def _build_model(self, data: Dict[str, np.ndarray]) -> pm.Model:
        """Build the hierarchical PyMC model."""
        n_counties = data['n_counties']

        with pm.Model() as model:
            # Data containers
            energy_burden = pm.Data("energy_burden", data['energy_burden'])
            income = pm.Data("income", data['income'])
            county_idx = pm.Data("county_idx", data['county_idx'])

            # Message type indicators
            has_urgency = pm.Data("has_urgency", data['has_urgency_deadline'])
            has_savings = pm.Data("has_savings", data['has_savings_financial'])
            has_relief = pm.Data("has_relief", data['has_relief_reassurance'])
            has_informational = pm.Data("has_informational", data['has_informational'])
            has_personalized = pm.Data("has_personalized", data['has_personalized_qualified'])
            has_motivational = pm.Data("has_motivational", data['has_motivational_struggle'])

            # === PRIORS ===

            # Intercept: Low base rate (~5% -> logit(-3.0) approx 0.047)
            intercept = pm.Normal("intercept", mu=-3.0, sigma=1.0)

            # Message type effects (informative priors based on expected directions)
            # Using slight positive priors for action-oriented message types
            beta_urgency = pm.Normal("beta_urgency", mu=0.3, sigma=0.3)
            beta_savings = pm.Normal("beta_savings", mu=0.2, sigma=0.3)
            beta_relief = pm.Normal("beta_relief", mu=0.1, sigma=0.3)
            beta_informational = pm.Normal("beta_informational", mu=0.0, sigma=0.3)
            beta_personalized = pm.Normal("beta_personalized", mu=0.4, sigma=0.3)
            beta_motivational = pm.Normal("beta_motivational", mu=0.2, sigma=0.3)

            # Confounder effects
            beta_income = pm.Normal("beta_income", mu=0.0, sigma=0.5)
            beta_burden = pm.Normal("beta_burden", mu=0.3, sigma=0.3)

            # County random effects (non-centered parameterization)
            sigma_county = pm.HalfNormal("sigma_county", sigma=0.5)
            county_offset = pm.Normal("county_offset", mu=0, sigma=1, shape=n_counties)
            gamma_county = pm.Deterministic("gamma_county", sigma_county * county_offset)

            # === LINEAR MODEL ===
            logit_p = (
                intercept +
                # Treatment effects (multi-label, additive)
                beta_urgency * has_urgency +
                beta_savings * has_savings +
                beta_relief * has_relief +
                beta_informational * has_informational +
                beta_personalized * has_personalized +
                beta_motivational * has_motivational +
                # Confounder control
                beta_income * income +
                beta_burden * energy_burden +
                # County random effect
                gamma_county[county_idx]
            )

            # === LIKELIHOOD ===
            y = pm.Bernoulli("y_clicked", logit_p=logit_p, observed=data['y_clicked'])

        self.pymc_model = model
        return model

    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """
        Train the Bayesian model.

        Args:
            data: Prepared data from load_data()
            **kwargs: Additional training parameters

        Returns:
            Dictionary with training results and metrics
        """
        self.ensure_output_dirs()

        draws = kwargs.get('draws', 2000)
        tune = kwargs.get('tune', 1000)
        chains = kwargs.get('chains', 4)
        target_accept = kwargs.get('target_accept', 0.95)
        random_seed = kwargs.get('random_seed', 42)

        if self.pymc_model is None:
            self._build_model(data)

        logger.info(f"Training {self.metadata.name}")
        logger.info(f"Observations: {len(data['y_clicked'])}")
        logger.info(f"Counties: {data['n_counties']}")
        logger.info(f"Click rate: {data['y_clicked'].mean():.2%}")
        logger.info(f"Sampling: {draws} draws x {chains} chains (tune={tune})")

        with self.pymc_model:
            self.trace = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                target_accept=target_accept,
                random_seed=random_seed,
                return_inferencedata=True,
            )

            # Posterior predictive
            logger.info("Generating posterior predictive samples...")
            pm.sample_posterior_predictive(
                self.trace,
                extend_inferencedata=True,
                random_seed=random_seed,
            )

        # Generate results
        results = self._generate_training_results()

        # Save artifacts
        self._save_training_artifacts(results)

        logger.info("Training complete!")
        return results

    def _generate_training_results(self) -> Dict[str, Any]:
        """Generate comprehensive training results and diagnostics."""
        treatment_vars = [
            "beta_urgency", "beta_savings", "beta_relief",
            "beta_informational", "beta_personalized", "beta_motivational"
        ]
        confounder_vars = ["beta_income", "beta_burden"]
        variance_vars = ["sigma_county"]
        all_vars = ["intercept"] + treatment_vars + confounder_vars + variance_vars

        summary = az.summary(self.trace, var_names=all_vars, hdi_prob=0.89)

        # Compute treatment effect estimates with odds ratios
        treatment_effects = {}
        for var in treatment_vars:
            # Extract message type name from variable name
            msg_type = var.replace("beta_", "")
            if msg_type == "urgency":
                msg_type = "urgency_deadline"
            elif msg_type == "savings":
                msg_type = "savings_financial"
            elif msg_type == "relief":
                msg_type = "relief_reassurance"
            elif msg_type == "personalized":
                msg_type = "personalized_qualified"
            elif msg_type == "motivational":
                msg_type = "motivational_struggle"

            mean_coef = summary.loc[var, 'mean']
            lower_ci = summary.loc[var, 'hdi_5.5%']
            upper_ci = summary.loc[var, 'hdi_94.5%']

            treatment_effects[msg_type] = {
                'coefficient': float(mean_coef),
                'odds_ratio': float(np.exp(mean_coef)),
                'or_lower': float(np.exp(lower_ci)),
                'or_upper': float(np.exp(upper_ci)),
                'effect_pct': float((np.exp(mean_coef) - 1) * 100),
                'credibly_positive': bool(lower_ci > 0),
                'credibly_negative': bool(upper_ci < 0),
                'credibly_nonzero': bool((lower_ci > 0) or (upper_ci < 0))
            }

        # Rank treatment effects by odds ratio
        effect_ranking = sorted(
            treatment_effects.items(),
            key=lambda x: x[1]['odds_ratio'],
            reverse=True
        )

        # Compute E-values for sensitivity analysis
        e_values = {}
        for msg_type, effect in treatment_effects.items():
            or_val = effect['odds_ratio']
            if or_val >= 1:
                e_value = or_val + np.sqrt(or_val * (or_val - 1))
            else:
                # For protective effects
                or_inv = 1 / or_val
                e_value = or_inv + np.sqrt(or_inv * (or_inv - 1))
            e_values[msg_type] = float(e_value)

        # Diagnostics
        diagnostics = {
            'r_hat_max': float(summary['r_hat'].max()),
            'ess_bulk_min': float(summary['ess_bulk'].min()),
            'ess_tail_min': float(summary['ess_tail'].min()),
            'divergences': int(self.trace.sample_stats['diverging'].sum().item()),
            'converged': bool(summary['r_hat'].max() < 1.01)
        }

        # County effects summary
        county_summary = az.summary(self.trace, var_names=['gamma_county'], hdi_prob=0.89)
        county_effects = {
            f"county_{i}": {
                'mean': float(county_summary.loc[f'gamma_county[{i}]', 'mean']),
                'sd': float(county_summary.loc[f'gamma_county[{i}]', 'sd'])
            }
            for i in range(len(county_summary))
        }

        # ICC (Intraclass Correlation Coefficient)
        sigma_county_samples = self.trace.posterior['sigma_county'].values.flatten()
        # For logistic: residual variance is pi^2/3
        residual_var = np.pi**2 / 3
        icc_samples = sigma_county_samples**2 / (sigma_county_samples**2 + residual_var)
        icc = {
            'mean': float(np.mean(icc_samples)),
            'lower': float(np.percentile(icc_samples, 5.5)),
            'upper': float(np.percentile(icc_samples, 94.5))
        }

        return {
            'summary': summary.to_dict(),
            'treatment_effects': treatment_effects,
            'effect_ranking': [(k, v) for k, v in effect_ranking],
            'e_values': e_values,
            'county_effects': county_effects,
            'icc': icc,
            'diagnostics': diagnostics,
            'scaler_params': self._scaler_params,
            'trained_at': datetime.now().isoformat()
        }

    def _save_training_artifacts(self, results: Dict[str, Any]) -> None:
        """Save trace, reports, and visualizations."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save trace
        trace_path = self.traces_dir / f'trace_{timestamp}.nc'
        self.trace.to_netcdf(trace_path)
        logger.info(f"Trace saved to {trace_path}")

        # Save scaler params
        scaler_path = self.checkpoints_dir / 'scaler_params.json'
        with open(scaler_path, 'w') as f:
            json.dump(self._scaler_params, f)

        # Save results summary
        results_path = self.reports_dir / f'results_{timestamp}.json'
        serializable_results = self._make_serializable(results)
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2)

        # Generate plots
        self._generate_plots(timestamp)
        self._generate_treatment_effects_plot(results, timestamp)
        self._generate_dag()

    def _make_serializable(self, obj: Any) -> Any:
        """Convert numpy types to Python types for JSON."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(v) for v in obj]
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def _generate_plots(self, timestamp: str) -> None:
        """Generate diagnostic plots."""
        var_names = [
            "intercept", "beta_urgency", "beta_savings", "beta_relief",
            "beta_informational", "beta_personalized", "beta_motivational",
            "beta_income", "beta_burden", "sigma_county"
        ]

        # Trace plot
        fig = az.plot_trace(self.trace, var_names=var_names)
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'trace_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Posterior plot
        fig = az.plot_posterior(self.trace, var_names=var_names, hdi_prob=0.89, ref_val=0)
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'posterior_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Diagnostic plots saved to {self.diagrams_dir}")

    def _generate_treatment_effects_plot(self, results: Dict[str, Any], timestamp: str) -> None:
        """Generate forest plot of treatment effects."""
        effects = results['treatment_effects']

        fig, ax = plt.subplots(figsize=(10, 6))

        # Sort by effect size
        sorted_effects = sorted(effects.items(), key=lambda x: x[1]['odds_ratio'], reverse=True)

        y_positions = range(len(sorted_effects))
        labels = []
        means = []
        errors_low = []
        errors_high = []
        colors = []

        for msg_type, effect in sorted_effects:
            labels.append(msg_type.replace('_', ' ').title())
            or_val = effect['odds_ratio']
            means.append(or_val)
            errors_low.append(or_val - effect['or_lower'])
            errors_high.append(effect['or_upper'] - or_val)

            # Color by significance
            if effect['credibly_positive']:
                colors.append('green')
            elif effect['credibly_negative']:
                colors.append('red')
            else:
                colors.append('gray')

        ax.errorbar(means, y_positions, xerr=[errors_low, errors_high],
                   fmt='o', capsize=5, capthick=2, color='black', ecolor='black')

        for i, (mean, color) in enumerate(zip(means, colors)):
            ax.scatter([mean], [i], color=color, s=100, zorder=5)

        ax.axvline(x=1, color='black', linestyle='--', alpha=0.5, label='No Effect (OR=1)')

        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels)
        ax.set_xlabel('Odds Ratio (89% CI)')
        ax.set_title('Campaign Message Type Treatment Effects\n(Green=Credibly Positive, Gray=Inconclusive)')

        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'treatment_effects_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        logger.info("Treatment effects forest plot saved")

    def _generate_dag(self) -> None:
        """Generate DAG visualization."""
        fig, ax = plt.subplots(figsize=(14, 10))
        ax.set_xlim(-1, 15)
        ax.set_ylim(-1, 12)
        ax.set_aspect('equal')
        ax.axis('off')

        # Node positions
        nodes = {
            'message_types': (2, 8),
            'income': (1, 4),
            'energy_burden': (4, 4),
            'county': (7, 4),
            'logit_p': (8, 8),
            'clicked': (12, 8),
            'selection': (4, 11),
        }

        # Node styles
        treatment_style = dict(boxstyle='round,pad=0.4', facecolor='lightcoral', edgecolor='red', linewidth=2)
        confounder_style = dict(boxstyle='round,pad=0.3', facecolor='lightyellow', edgecolor='orange', linewidth=2)
        det_style = dict(boxstyle='round,pad=0.3', facecolor='lightgray', edgecolor='gray', linewidth=2)
        outcome_style = dict(boxstyle='round,pad=0.4', facecolor='lightgreen', edgecolor='green', linewidth=2)
        mechanism_style = dict(boxstyle='round,pad=0.3', facecolor='lightblue', edgecolor='blue', linewidth=2)

        node_labels = {
            'message_types': 'message_types\n(Treatment)',
            'income': 'income\n(Confounder)',
            'energy_burden': 'energy_burden\n(Confounder)',
            'county': 'county\n(Random Effect)',
            'logit_p': 'logit(p)',
            'clicked': 'CLICKED\n(Outcome)',
            'selection': 'Selection\nMechanism',
        }

        styles = {
            'message_types': treatment_style,
            'income': confounder_style,
            'energy_burden': confounder_style,
            'county': confounder_style,
            'logit_p': det_style,
            'clicked': outcome_style,
            'selection': mechanism_style,
        }

        for name, (x, y) in nodes.items():
            ax.text(x, y, node_labels[name], ha='center', va='center',
                   fontsize=10, bbox=styles[name], fontweight='bold')

        # Arrows
        arrows = [
            ('selection', 'message_types'),
            ('selection', 'income'),
            ('selection', 'energy_burden'),
            ('message_types', 'logit_p'),
            ('income', 'logit_p'),
            ('energy_burden', 'logit_p'),
            ('county', 'logit_p'),
            ('logit_p', 'clicked'),
        ]

        for start, end in arrows:
            x1, y1 = nodes[start]
            x2, y2 = nodes[end]
            dx, dy = x2 - x1, y2 - y1
            ax.annotate('', xy=(x2 - dx*0.15, y2 - dy*0.15),
                       xytext=(x1 + dx*0.15, y1 + dy*0.15),
                       arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

        ax.set_title('Campaign Treatment Effects DAG\nBackdoor paths blocked by conditioning on confounders',
                    fontsize=12, fontweight='bold', pad=20)

        # Legend
        legend_items = [
            ('Treatment', 'lightcoral', 'red'),
            ('Confounder', 'lightyellow', 'orange'),
            ('Outcome', 'lightgreen', 'green'),
            ('Mechanism', 'lightblue', 'blue'),
        ]
        for i, (label, fc, ec) in enumerate(legend_items):
            ax.add_patch(plt.Rectangle((11, 3 - i*0.6), 0.4, 0.4, facecolor=fc, edgecolor=ec, linewidth=2))
            ax.text(11.6, 3.2 - i*0.6, label, fontsize=9, va='center')

        plt.tight_layout()
        plt.savefig(self.diagrams_dir / 'dag.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()

        logger.info("DAG saved to diagrams/dag.png")

    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run inference with the trained model.

        Args:
            inference_params: Dictionary with:
                - message_types: List of message types
                - energy_burden: Energy burden percentage
                - income: Annual income
                - county: County name
                - credible_interval: CI width (optional)

        Returns:
            Dictionary with prediction results
        """
        # Validate parameters
        is_valid, error = self.validate_inference_params(inference_params)
        if not is_valid:
            return {'error': error}

        # Load trained model if needed
        if self.trace is None:
            if not self._load_latest_model():
                return {'error': 'No trained model found. Please train the model first.'}

        # Load scaler params
        if self._scaler_params is None:
            scaler_path = self.checkpoints_dir / 'scaler_params.json'
            if scaler_path.exists():
                with open(scaler_path, 'r') as f:
                    self._scaler_params = json.load(f)
            else:
                return {'error': 'Scaler parameters not found. Please retrain.'}

        # Standardize inputs
        energy_burden = float(inference_params['energy_burden'])
        income = float(inference_params['income'])
        county = inference_params['county']
        message_types = inference_params.get('message_types', ['informational'])

        # Ensure message_types is a list
        if isinstance(message_types, str):
            message_types = [message_types]

        logger.info(f"Inference inputs: income={income}, energy_burden={energy_burden}, "
                   f"county={county}, message_types={message_types}")

        burden_scaled = (energy_burden - self._scaler_params['burden_mean']) / self._scaler_params['burden_std']
        income_scaled = (income - self._scaler_params['income_mean']) / self._scaler_params['income_std']

        logger.info(f"Scaled inputs: income_scaled={income_scaled:.3f}, burden_scaled={burden_scaled:.3f}")

        county_mapping = self._scaler_params.get('county_mapping', {})
        if county not in county_mapping:
            return {'error': f'County "{county}" not in training data. Available: {list(county_mapping.keys())}'}
        county_idx = county_mapping[county]

        # Extract posterior samples
        posterior = self.trace.posterior
        intercept = posterior['intercept'].values.flatten()
        beta_urgency = posterior['beta_urgency'].values.flatten()
        beta_savings = posterior['beta_savings'].values.flatten()
        beta_relief = posterior['beta_relief'].values.flatten()
        beta_informational = posterior['beta_informational'].values.flatten()
        beta_personalized = posterior['beta_personalized'].values.flatten()
        beta_motivational = posterior['beta_motivational'].values.flatten()
        beta_income = posterior['beta_income'].values.flatten()
        beta_burden = posterior['beta_burden'].values.flatten()
        gamma_county = posterior['gamma_county'].values[:, :, county_idx].flatten()

        # Create message type indicators
        has_urgency = 1 if 'urgency_deadline' in message_types else 0
        has_savings = 1 if 'savings_financial' in message_types else 0
        has_relief = 1 if 'relief_reassurance' in message_types else 0
        has_informational = 1 if 'informational' in message_types else 0
        has_personalized = 1 if 'personalized_qualified' in message_types else 0
        has_motivational = 1 if 'motivational_struggle' in message_types else 0

        logger.info(f"Message indicators: urgency={has_urgency}, savings={has_savings}, "
                   f"relief={has_relief}, info={has_informational}, personal={has_personalized}, "
                   f"motivational={has_motivational}")

        # Compute predicted probability
        logit_p = (
            intercept +
            beta_urgency * has_urgency +
            beta_savings * has_savings +
            beta_relief * has_relief +
            beta_informational * has_informational +
            beta_personalized * has_personalized +
            beta_motivational * has_motivational +
            beta_income * income_scaled +
            beta_burden * burden_scaled +
            gamma_county
        )
        prob = 1 / (1 + np.exp(-logit_p))

        logger.info(f"Computed probability: mean={np.mean(prob):.4f}, std={np.std(prob):.4f}, "
                   f"range=[{np.min(prob):.4f}, {np.max(prob):.4f}]")

        # Summary statistics
        ci = float(inference_params.get('credible_interval', 0.89))
        lower_q = (1 - ci) / 2
        upper_q = 1 - lower_q

        return {
            'mean_probability': float(np.mean(prob)),
            'median_probability': float(np.median(prob)),
            'std_probability': float(np.std(prob)),
            'credible_interval': {
                'lower': float(np.quantile(prob, lower_q)),
                'upper': float(np.quantile(prob, upper_q)),
                'level': ci
            },
            'input_values': {
                'message_types': message_types,
                'energy_burden': energy_burden,
                'income': income,
                'county': county
            },
            'interpretation': self._generate_interpretation(np.mean(prob), message_types)
        }

    def _load_latest_model(self) -> bool:
        """Load the most recent trained model."""
        latest_trace = self.get_latest_trace()
        if latest_trace is None:
            return False
        self.trace = az.from_netcdf(latest_trace)
        logger.info(f"Loaded trace from {latest_trace}")
        return True

    def _generate_interpretation(self, prob: float, message_types: List[str]) -> str:
        """Generate human-readable interpretation."""
        types_str = ", ".join(mt.replace('_', ' ') for mt in message_types)

        if prob >= 0.10:
            return (f"High click probability ({prob:.1%}) for campaign using {types_str}. "
                   f"This message combination shows strong engagement potential.")
        elif prob >= 0.05:
            return (f"Average click probability ({prob:.1%}) for campaign using {types_str}. "
                   f"Consider adding personalization or urgency elements.")
        else:
            return (f"Below-average click probability ({prob:.1%}) for campaign using {types_str}. "
                   f"Review message framing and targeting strategy.")

    def get_dynamic_options(self) -> Dict[str, list]:
        """
        Get dynamic options for select fields.

        Returns:
            Dictionary mapping parameter names to their available options.
            - county: Available counties from training data (loaded from scaler_params)
            - message_types: All available message types (always static)
        """
        options = {}

        # Message types are always the full list
        options['message_types'] = MESSAGE_TYPES.copy()

        # Load county options from scaler_params (saved during training)
        scaler_path = self.checkpoints_dir / 'scaler_params.json'
        if scaler_path.exists():
            try:
                with open(scaler_path, 'r') as f:
                    scaler_params = json.load(f)
                county_mapping = scaler_params.get('county_mapping', {})
                # Return list of county names sorted alphabetically
                options['county'] = sorted(county_mapping.keys())
                logger.info(f"Loaded {len(options['county'])} counties from training data")
            except Exception as e:
                logger.warning(f"Could not load county options: {e}")
                options['county'] = []
        else:
            # If no scaler_params, try to load from database
            try:
                from src.tools.mongo import get_campaign_db
                db = get_campaign_db()

                # Get unique counties from participants with numeric income_level
                counties = db.participants.distinct('linkage.county_key', {
                    'linkage.county_key': {'$exists': True},
                    'demographics.income_level': {'$type': 'number'}
                })
                # Normalize county names (remove "County" suffix)
                normalized = []
                for c in counties:
                    if c:
                        normalized.append(c[:-6] if c.endswith('County') else c)
                options['county'] = sorted(set(normalized))
                logger.info(f"Loaded {len(options['county'])} counties from database")
            except Exception as e:
                logger.warning(f"Could not load county options from database: {e}")
                options['county'] = []

        return options

    def get_model_summary(self) -> Dict[str, Any]:
        """Get comprehensive model summary for UI display."""
        summary = {
            'metadata': self.get_metadata_dict(),
            'has_trained_model': self.has_trained_model(),
            'latest_trace': str(self.get_latest_trace()) if self.get_latest_trace() else None,
            'message_types': MESSAGE_TYPES,
            'diagram_files': [],
            'report_files': []
        }

        if self.diagrams_dir.exists():
            summary['diagram_files'] = [f.name for f in self.diagrams_dir.glob('*')]

        if self.reports_dir.exists():
            summary['report_files'] = [f.name for f in self.reports_dir.glob('*')]

        return summary
