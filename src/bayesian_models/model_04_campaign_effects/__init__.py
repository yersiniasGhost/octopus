"""
Model 04: Campaign Treatment Effects Model

Hierarchical Bayesian model estimating causal effects of campaign
message types on click behavior with confounding control.
"""

from .model import CampaignTreatmentEffectsModel

__all__ = ['CampaignTreatmentEffectsModel']
