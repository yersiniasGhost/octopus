# Messaging Effectiveness Model - Results Interpretation

**Model**: 2-Stage Hierarchical Bayesian Logistic Regression
**Version**: 1.0
**Training Date**: January 1, 2026
**Data**: 27,554 email records across 15 campaigns

---

## Executive Summary

This model analyzes email campaign effectiveness through a two-stage funnel:
1. **Stage 1**: Probability of opening the email
2. **Stage 2**: Probability of clicking (conditional on opening)

### Key Findings

| Metric | Population Mean | 89% Credible Interval |
|--------|-----------------|----------------------|
| **Open Rate** | 3.61% | [2.32%, 5.26%] |
| **Click Rate** (given open) | 5.24% | [3.34%, 7.68%] |
| **End-to-End Conversion** | ~0.19% | [0.08%, 0.29%] |

---

## Message Type Effects

### Impact on Open Rate

Message type effects on the probability of opening an email, ranked from most to least effective:

| Message Type | Effect on Odds | 89% HDI | Confidence |
|--------------|----------------|---------|------------|
| **Urgency** | +17.1% | [-28.6%, +89.7%] | 70% positive |
| Cost Framing | +5.5% | [-37.3%, +76.8%] | 57% positive |
| Event | +1.3% | [-39.9%, +64.6%] | 52% positive |
| Other | -2.0% | [-42.2%, +55.5%] | 46% positive |
| **Improvement** | -25.6% | [-55.7%, +24.2%] | 18% positive |

**Interpretation**:
- **Urgency messaging** shows the strongest positive signal for opens (+17%), though uncertainty remains high
- **Improvement-focused messaging** appears to reduce open rates by ~26%, with 82% probability of negative effect
- Other message types show inconclusive differences from baseline

### Impact on Click Rate (Given Open)

Once a recipient opens the email, different message types affect click behavior differently:

| Message Type | Effect on Odds | 89% HDI | Confidence |
|--------------|----------------|---------|------------|
| Other | +20.4% | [-29.3%, +103.5%] | 71% positive |
| Improvement | +18.4% | [-30.0%, +106.1%] | 69% positive |
| Cost Framing | +7.1% | [-36.9%, +83.4%] | 58% positive |
| Event | -6.0% | [-47.4%, +58.4%] | 43% positive |
| **Urgency** | **-38.0%** | [-65.2%, +8.0%] | **9% positive** |

**Interpretation**:
- **Urgency messaging paradox**: While urgency drives opens, it significantly *reduces* clicks among those who open (91% probability of negative effect)
- **Improvement messaging** shows the opposite pattern: lower opens but potentially higher engagement once opened
- This suggests urgency may create "curiosity opens" that don't convert to action

---

## Campaign Performance Rankings

### Top 5 Campaigns (Predicted Open Rate)

| Campaign | Open Rate | 89% HDI |
|----------|-----------|---------|
| MVCAP Summer Crisis Graphic (Aug 2025) | 6.79% | [3.30%, 10.21%] |
| IMPACT Your Home Selected (May 2025) | 5.98% | [3.03%, 8.92%] |
| MVCAP Improve (Aug 2025) | 4.44% | [2.30%, 6.48%] |
| MVCAP Webinar (Sep 2025) | 4.40% | [2.19%, 6.31%] |
| IMPACT Daily Cost | 4.24% | [2.02%, 6.14%] |

### Bottom 5 Campaigns

| Campaign | Open Rate | 89% HDI |
|----------|-----------|---------|
| COAD Final Days (Sep 2025) | 3.19% | [1.44%, 4.70%] |
| OHCAC Monthly Savings Change (May 2025) | 3.11% | [1.54%, 4.58%] |
| COAD Improve (Aug 2025) | 2.86% | [1.48%, 4.22%] |
| MVCAP Claude Content (Jun 2025) | 2.61% | [1.20%, 3.96%] |
| MVCAP Crisis (Jul 2025) | 2.55% | [1.23%, 3.81%] |

**Observations**:
- Performance varies ~2.7x between best and worst campaigns (6.79% vs 2.55%)
- The hierarchical structure provides "shrinkage" - extreme campaigns are pulled toward the population mean
- Campaign-level variation (σ = 0.40 on logit scale) indicates substantial heterogeneity

---

## Strategic Recommendations

### 1. Reconsider Pure Urgency Messaging
While urgency drives initial attention (opens), it may create "false engagement" that doesn't convert. Consider:
- Combining urgency with substantive value propositions
- Testing urgency in subject lines paired with detailed benefit content

### 2. Test Improvement Messaging for Engaged Audiences
Improvement messaging underperforms for opens but shows promise for clicks. Consider:
- Using improvement framing for re-engagement campaigns to already-interested recipients
- A/B testing improvement content with high-urgency subject lines

### 3. Learn from Top Performers
The "Summer Crisis" and "Your Home Selected" campaigns significantly outperformed. Analyze:
- Subject line patterns
- Send timing
- Audience segment characteristics
- Specific offer framing

### 4. Campaign Variation is Substantial
With campaigns varying by ~40% on the logit scale, factors beyond message type matter. Investigate:
- Seasonal effects
- Day-of-week patterns
- List segment quality
- Competitive email timing

---

## Model Diagnostics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| R-hat (all params) | 1.0000 | Excellent convergence |
| Effective Sample Size | 3,000-5,000 | Adequate for inference |
| Divergences | 0 | No sampling issues |
| Parameterization | Non-centered | Handles hierarchical structure well |

---

## Technical Notes

### Model Structure
```
Stage 1 (Open):
  logit(P_open) = μ_α + z_campaign × σ_α + β_msg_type + β_location + β_month + β_X

Stage 2 (Click|Open):
  logit(P_click|open) = μ_α_click + z_campaign × σ_α_click + β_msg_type + β_X
```

### Key Assumptions
1. **Partial Pooling**: Campaigns share information through hierarchical priors
2. **Conditional Independence**: Click probability conditioned on opening
3. **Linear Logit**: Effects combine additively on logit scale

### Limitations
1. **Observational Data**: Causal claims require careful interpretation
2. **Limited Message Types**: Only 5 categories may mask nuanced differences
3. **Temporal Confounding**: Campaign timing not fully controlled

---

## Using the Model for Predictions

Access via the Inference Models page:
1. Select "Messaging Effectiveness Model"
2. Choose a campaign or "All Campaigns (Population Average)"
3. Set credible interval (default 89%)
4. Run inference to get predicted open/click rates with uncertainty

The "All Campaigns" option uses population-level parameters to predict performance for a hypothetical average campaign.
