"""
Analysis-04: Applicant-Centric Cluster Analysis

Goal: Understand what drives applications (conversions) for Bayesian causal modeling.

Key differences from Analysis-03:
- Outcome variable: is_applicant (binary) vs engagement metrics
- Scope: All 7,451 participants (not just engaged ones)
- Features: Self-reported demographics + multi-channel exposure
- Purpose: Identify causal drivers of conversion for intervention modeling

Phases:
1. Demographics-only clustering → baseline applicant rate per cluster
2. Demographics + channel/message exposure → incremental predictive power
3. Probabilistic clustering → soft assignments for PyMC causal models

Channel exposure logic:
- Baseline: Everyone received letters/mailers
- Variable: Email campaigns (68), Text campaigns (74)
- Attribution: UTM tracking identifies conversion channel
"""
