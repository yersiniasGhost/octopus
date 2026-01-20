"""
Messaging Effectiveness Model

2-stage hierarchical Bayesian model for email campaign funnel:
- Stage 1: P(Open | features)
- Stage 2: P(Click | Open, features)
"""

from .model import MessagingEffectivenessModel

__all__ = ['MessagingEffectivenessModel']
