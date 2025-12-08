"""
Bayesian Model Training Scripts

Each script in this directory trains a specific model:
    {model_name}_train.py  - Train the {model_name} model

Scripts handle:
    1. Data loading and preparation
    2. Model training (MCMC sampling)
    3. Convergence diagnostics
    4. Output saving to models/{model_name}/

Run scripts manually:
    python src/bayesian_scripts/{model_name}_train.py

Or with options:
    python src/bayesian_scripts/{model_name}_train.py --draws 2000 --chains 4
"""
