"""
Model 01: Baseline Email Open Model

Predicts email opens based on:
- Annual energy cost
- Annual savings potential

This is the simplest model to establish baseline predictive performance
before adding energy burden and demographic confounders.

Research Question:
"Does energy cost and savings potential predict email open rates?"
"""

from pathlib import Path
from typing import Dict, Any, Optional
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt

from src.bayesian_models.base_model import BaseBayesianModel
from src.utils.engagement import attach_engagement_summaries
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


class BaselineOpenModel(BaseBayesianModel):
    """Model 1: Baseline logistic regression for email opens."""

    def __init__(self, model_dir: Optional[Path] = None):
        """Initialize the model."""
        if model_dir is None:
            model_dir = Path(__file__).parent
        super().__init__(model_dir)

        self.pymc_model = None
        self.trace = None
        self._scaler_params = None  # Store standardization params for inference

    def load_data(self, **kwargs) -> Dict[str, np.ndarray]:
        """
        Load and prepare data for model training.

        Kwargs:
            collection: MongoDB collection name (default: 'participants')
            filters: Query filters for data selection

        Returns:
            Dictionary with standardized features and outcome
        """
        from src.tools.mongo import get_campaign_db

        db = get_campaign_db()
        collection_name = kwargs.get('collection', 'participants')

        # Load data from MongoDB with projection for efficiency
        query = kwargs.get('filters', {})
        projection = {
            'participant_id': 1,
            'energy_snapshot.annual_cost': 1,
            'demographics.total_energy_burden': 1,
        }

        cursor = db[collection_name].find(query, projection)
        records = list(cursor)
        attach_engagement_summaries(db, records)
        logger.info(f"Loaded {len(records)} records from {collection_name}")

        # Extract and flatten relevant fields
        data_rows = []
        for doc in records:
            energy = doc.get('energy_snapshot', {}) or {}
            demographics = doc.get('demographics', {}) or {}
            engagement = doc.get('engagement_summary', {}) or {}

            annual_cost = energy.get('annual_cost')
            # Use energy burden as proxy for savings potential (higher burden = more savings potential)
            energy_burden = demographics.get('total_energy_burden')

            # Check for email engagement (opened/clicked)
            email_engaged = engagement.get('by_channel', {}).get('email', {}).get('engaged', 0)
            ever_engaged = engagement.get('ever_engaged', False)

            # For email open model, we want email engagement
            opened = 1 if email_engaged > 0 else 0

            if annual_cost is not None and energy_burden is not None:
                data_rows.append({
                    'annual_cost': annual_cost,
                    'energy_burden': energy_burden,  # Using as savings proxy
                    'opened': opened
                })

        df = pd.DataFrame(data_rows)
        logger.info(f"After filtering: {len(df)} records with complete data")

        if len(df) == 0:
            raise ValueError("No valid data found. Check database fields.")

        # Log engagement rate
        open_rate = df['opened'].mean()
        logger.info(f"Open rate: {open_rate:.2%} ({df['opened'].sum()}/{len(df)})")

        # Standardize predictors
        cost_mean = df['annual_cost'].mean()
        cost_std = df['annual_cost'].std()
        burden_mean = df['energy_burden'].mean()
        burden_std = df['energy_burden'].std()

        # Store scaler params for inference
        self._scaler_params = {
            'cost_mean': float(cost_mean),
            'cost_std': float(cost_std),
            'burden_mean': float(burden_mean),
            'burden_std': float(burden_std)
        }

        data = {
            'annual_cost': ((df['annual_cost'] - cost_mean) / cost_std).values,
            'annual_savings': ((df['energy_burden'] - burden_mean) / burden_std).values,  # Using burden as savings proxy
            'y_opened': df['opened'].astype(int).values
        }

        return data

    def _build_model(self, data: Dict[str, np.ndarray]) -> pm.Model:
        """Build the PyMC model."""
        with pm.Model() as model:
            # Data containers
            annual_cost = pm.Data("annual_cost", data['annual_cost'])
            annual_savings = pm.Data("annual_savings", data['annual_savings'])

            # Priors - weakly informative
            intercept = pm.Normal("intercept", mu=0, sigma=2)
            beta_cost = pm.Normal("beta_cost", mu=0, sigma=1)
            beta_savings = pm.Normal("beta_savings", mu=0, sigma=1)

            # Linear model (logit scale)
            logit_p = intercept + beta_cost * annual_cost + beta_savings * annual_savings

            # Likelihood
            y = pm.Bernoulli("y_open", logit_p=logit_p, observed=data['y_opened'])

        self.pymc_model = model
        return model

    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """
        Train the Bayesian model.

        Args:
            data: Prepared data from load_data()
            **kwargs: Additional training parameters
                - draws: Number of posterior samples (default: 2000)
                - tune: Number of tuning samples (default: 1000)
                - chains: Number of MCMC chains (default: 4)
                - target_accept: Target acceptance rate (default: 0.95)

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
        logger.info(f"Observations: {len(data['y_opened'])}")
        logger.info(f"Open rate: {data['y_opened'].mean():.2%}")
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

            # Add posterior predictive samples
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
        """Generate training results and diagnostics."""
        summary = az.summary(
            self.trace,
            var_names=["intercept", "beta_cost", "beta_savings"],
            hdi_prob=0.95
        )

        # Compute odds ratios
        odds_ratios = {}
        for var in ['beta_cost', 'beta_savings']:
            mean_coef = summary.loc[var, 'mean']
            lower_ci = summary.loc[var, 'hdi_2.5%']
            upper_ci = summary.loc[var, 'hdi_97.5%']

            odds_ratios[var] = {
                'coefficient': float(mean_coef),
                'odds_ratio': float(np.exp(mean_coef)),
                'or_lower': float(np.exp(lower_ci)),
                'or_upper': float(np.exp(upper_ci)),
                'effect_pct': float((np.exp(mean_coef) - 1) * 100),
                'credibly_nonzero': bool((lower_ci > 0 and upper_ci > 0) or
                                         (lower_ci < 0 and upper_ci < 0))
            }

        # Diagnostics
        diagnostics = {
            'r_hat_max': float(summary['r_hat'].max()),
            'ess_bulk_min': float(summary['ess_bulk'].min()),
            'ess_tail_min': float(summary['ess_tail'].min()),
            'divergences': int(self.trace.sample_stats['diverging'].sum().item())
        }

        return {
            'summary': summary.to_dict(),
            'odds_ratios': odds_ratios,
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

        # Save scaler params for inference
        scaler_path = self.checkpoints_dir / 'scaler_params.json'
        with open(scaler_path, 'w') as f:
            json.dump(self._scaler_params, f)

        # Save results summary
        results_path = self.reports_dir / f'results_{timestamp}.json'
        # Convert numpy types for JSON serialization
        serializable_results = self._make_serializable(results)
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2)

        # Generate and save plots
        self._generate_plots(timestamp)

        # Generate DAG
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
        """Generate diagnostic and posterior plots."""
        # Trace plot
        fig = az.plot_trace(
            self.trace,
            var_names=["intercept", "beta_cost", "beta_savings"]
        )
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'trace_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Posterior plot
        fig = az.plot_posterior(
            self.trace,
            var_names=["intercept", "beta_cost", "beta_savings"],
            hdi_prob=0.95,
            ref_val=0,
        )
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'posterior_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        # Forest plot for coefficients
        fig = az.plot_forest(
            self.trace,
            var_names=["beta_cost", "beta_savings"],
            combined=True,
            hdi_prob=0.95,
        )
        plt.tight_layout()
        plt.savefig(self.diagrams_dir / f'forest_{timestamp}.png', dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Plots saved to {self.diagrams_dir}")

    def _generate_dag(self) -> None:
        """Generate and save DAG visualization using matplotlib."""
        if self.pymc_model is None:
            logger.warning("Cannot generate DAG - model not built")
            return

        try:
            self._generate_matplotlib_dag()
            logger.info(f"DAG saved to {self.diagrams_dir / 'dag.png'}")
        except Exception as e:
            logger.warning(f"Could not generate DAG visualization: {e}")
            self._generate_text_dag()

    def _generate_matplotlib_dag(self) -> None:
        """Create a DAG visualization using matplotlib."""
        fig, ax = plt.subplots(1, 1, figsize=(10, 8))
        ax.set_xlim(-1, 11)
        ax.set_ylim(-1, 9)
        ax.set_aspect('equal')
        ax.axis('off')

        # Define node positions
        nodes = {
            # Priors (left column)
            'intercept': (1, 7),
            'beta_cost': (1, 5),
            'beta_savings': (1, 3),
            # Data (left column, lower)
            'annual_cost': (1, 1.5),
            'energy_burden': (1, 0),
            # Deterministic (middle)
            'logit_p': (5, 4),
            # Likelihood (right)
            'y_open': (9, 4),
        }

        # Node styles
        prior_style = dict(boxstyle='round,pad=0.3', facecolor='lightblue', edgecolor='blue', linewidth=2)
        data_style = dict(boxstyle='round,pad=0.3', facecolor='lightgray', edgecolor='gray', linewidth=2)
        det_style = dict(boxstyle='round,pad=0.3', facecolor='lightyellow', edgecolor='orange', linewidth=2)
        obs_style = dict(boxstyle='round,pad=0.3', facecolor='lightgreen', edgecolor='green', linewidth=2)

        # Draw nodes
        node_labels = {
            'intercept': 'intercept\n~ Normal(0, 2)',
            'beta_cost': 'β_cost\n~ Normal(0, 1)',
            'beta_savings': 'β_burden\n~ Normal(0, 1)',
            'annual_cost': 'annual_cost\n(data)',
            'energy_burden': 'energy_burden\n(data)',
            'logit_p': 'logit_p\n(deterministic)',
            'y_open': 'y_open\n~ Bernoulli',
        }

        styles = {
            'intercept': prior_style, 'beta_cost': prior_style, 'beta_savings': prior_style,
            'annual_cost': data_style, 'energy_burden': data_style,
            'logit_p': det_style, 'y_open': obs_style,
        }

        for name, (x, y) in nodes.items():
            ax.text(x, y, node_labels[name], ha='center', va='center',
                    fontsize=10, bbox=styles[name], fontweight='bold')

        # Draw arrows
        arrows = [
            ('intercept', 'logit_p'),
            ('beta_cost', 'logit_p'),
            ('beta_savings', 'logit_p'),
            ('annual_cost', 'logit_p'),
            ('energy_burden', 'logit_p'),
            ('logit_p', 'y_open'),
        ]

        for start, end in arrows:
            x1, y1 = nodes[start]
            x2, y2 = nodes[end]
            # Offset for node boxes
            dx = x2 - x1
            dy = y2 - y1
            length = (dx**2 + dy**2)**0.5
            # Shorten arrows to not overlap with boxes
            shrink = 0.8
            ax.annotate('', xy=(x2 - dx*0.15, y2 - dy*0.15),
                        xytext=(x1 + dx*0.15, y1 + dy*0.15),
                        arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

        # Title and legend
        ax.set_title('Baseline Email Open Model - DAG', fontsize=14, fontweight='bold', pad=20)

        # Legend
        legend_items = [
            ('Prior', 'lightblue', 'blue'),
            ('Data', 'lightgray', 'gray'),
            ('Deterministic', 'lightyellow', 'orange'),
            ('Observed', 'lightgreen', 'green'),
        ]
        for i, (label, fc, ec) in enumerate(legend_items):
            ax.add_patch(plt.Rectangle((7.5, 7.5 - i*0.6), 0.4, 0.4,
                                        facecolor=fc, edgecolor=ec, linewidth=2))
            ax.text(8.1, 7.7 - i*0.6, label, fontsize=9, va='center')

        # Model equation
        eq_text = "logit(p) = intercept + β_cost × cost + β_burden × burden"
        ax.text(5, -0.5, eq_text, ha='center', fontsize=10, style='italic',
                bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray'))

        plt.tight_layout()
        plt.savefig(self.diagrams_dir / 'dag.png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close()

    def _generate_text_dag(self) -> None:
        """Create a text-based DAG representation as fallback."""
        dag_text = """
Model DAG: Baseline Email Open Model
=====================================

Priors:
  intercept ~ Normal(0, 2)
  beta_cost ~ Normal(0, 1)
  beta_savings ~ Normal(0, 1)

Linear Model:
  logit_p = intercept + beta_cost * annual_cost + beta_savings * energy_burden

Likelihood:
  y_open ~ Bernoulli(logit_p)

Graph Structure:
  annual_cost ──┐
                ├──→ logit_p ──→ y_open
  energy_burden─┘         ↑
                          │
  intercept ──────────────┘
  beta_cost ──────────────┘
  beta_savings ───────────┘
"""
        with open(self.diagrams_dir / 'dag.txt', 'w') as f:
            f.write(dag_text)

    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run inference with the trained model.

        Args:
            inference_params: Dictionary with:
                - annual_cost: Energy cost in dollars
                - energy_burden: Energy burden percentage
                - num_samples: Number of posterior samples (optional)
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
                return {'error': 'Scaler parameters not found. Please retrain the model.'}

        # Standardize input
        annual_cost = float(inference_params['annual_cost'])
        energy_burden = float(inference_params['energy_burden'])

        cost_scaled = (annual_cost - self._scaler_params['cost_mean']) / self._scaler_params['cost_std']
        burden_scaled = (energy_burden - self._scaler_params['burden_mean']) / self._scaler_params['burden_std']

        # Extract posterior samples
        posterior = self.trace.posterior
        intercept = posterior['intercept'].values.flatten()
        beta_cost = posterior['beta_cost'].values.flatten()
        beta_savings = posterior['beta_savings'].values.flatten()

        # Compute predicted probabilities (beta_savings uses energy burden as proxy)
        logit_p = intercept + beta_cost * cost_scaled + beta_savings * burden_scaled
        prob = 1 / (1 + np.exp(-logit_p))

        # Summary statistics
        ci = float(inference_params.get('credible_interval', 0.95))
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
                'annual_cost': annual_cost,
                'energy_burden': energy_burden,
                'cost_scaled': float(cost_scaled),
                'burden_scaled': float(burden_scaled)
            },
            'interpretation': self._generate_interpretation(np.mean(prob))
        }

    def _load_latest_model(self) -> bool:
        """Load the most recent trained model."""
        latest_trace = self.get_latest_trace()
        if latest_trace is None:
            return False

        self.trace = az.from_netcdf(latest_trace)
        logger.info(f"Loaded trace from {latest_trace}")
        return True

    def _generate_interpretation(self, prob: float) -> str:
        """Generate human-readable interpretation of prediction."""
        if prob >= 0.7:
            return f"High likelihood ({prob:.1%}) of email open. This recipient profile shows strong engagement potential."
        elif prob >= 0.5:
            return f"Moderate likelihood ({prob:.1%}) of email open. Average engagement expected."
        elif prob >= 0.3:
            return f"Below average likelihood ({prob:.1%}) of email open. Consider enhanced subject line or timing."
        else:
            return f"Low likelihood ({prob:.1%}) of email open. This profile typically shows low engagement."

    def get_model_summary(self) -> Dict[str, Any]:
        """Get comprehensive model summary for UI display."""
        summary = {
            'metadata': self.get_metadata_dict(),
            'has_trained_model': self.has_trained_model(),
            'latest_trace': str(self.get_latest_trace()) if self.get_latest_trace() else None,
            'diagram_files': [],
            'report_files': []
        }

        # List available diagrams
        if self.diagrams_dir.exists():
            summary['diagram_files'] = [f.name for f in self.diagrams_dir.glob('*')]

        # List available reports
        if self.reports_dir.exists():
            summary['report_files'] = [f.name for f in self.reports_dir.glob('*')]

        return summary
