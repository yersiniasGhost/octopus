# Analysis-03: Email + Text Campaign Clustering Analysis Report
## Participant Engagement Optimization Study with Multi-Channel Data

**Analysis Date**: December 8, 2025
**Prepared for**: Team Review
**Version**: 3.0 (Email + Text Integration)

---

## Executive Summary

### The Big Picture

We analyzed **7,451 participants** across **143 campaigns** (68 email + 74 text) to understand what drives engagement with energy assistance programs. By integrating text campaign data with our existing email analysis, we identified **10 distinct participant segments** with dramatically different engagement rates.

### Key Findings at a Glance

| Finding | Impact |
|---------|--------|
| **Text campaigns are 5.3x more effective than email** | 11.54% text reply rate vs 2.18% email click rate |
| **Combined multi-channel approach works best** | Participants with both channels engage at higher rates |
| **"Super Performers" segment (Cluster 3)** | 292 participants with **41.1% engagement** (vs 8.5% average) |
| **Message type still #1 predictor** | Personalized + motivational messaging drives engagement across channels |
| **373 new text-only participants** | Previously unreached audience now included in analysis |

### Bottom Line

**Text messaging is a game-changer for engagement.** Adding text campaigns increased our measurable engagement from 2.18% to 8.54%. The most effective strategy combines high-frequency multi-channel outreach with personalized, savings-focused messaging.

---

## Comparison: Analysis-02 vs Analysis-03

| Metric | Analysis-02 (Email Only) | Analysis-03 (Email + Text) | Change |
|--------|--------------------------|----------------------------|--------|
| Total Participants | 7,078 | 7,451 | +5.3% |
| Total Exposures | 129,483 | 175,487 | +35.5% |
| Campaigns | 68 (email) | 143 (68 email + 74 text) | +110% |
| Engagement Rate | 2.18% | 8.54% | **+292%** |
| Top Cluster Engagement | 11.9% | 41.1% | **+245%** |
| Clusters Identified | 9 | 10 | +1 |

---

## What We Analyzed

### Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| Participants | 7,451 | Individuals in our campaign database |
| Campaigns | 143 | 68 email + 74 text campaigns |
| Campaign-Participant Links | 175,487 | Individual campaign exposures |

### Channel Breakdown

| Channel | Participants | Exposures | Engagement Rate |
|---------|-------------|-----------|-----------------|
| Email Only | 3,170 (42.5%) | 129,483 | 2.18% (clicks) |
| Text Only | 373 (5.0%) | 46,004 | 11.54% (replies) |
| Both Channels | 3,908 (52.4%) | - | Combined higher |

### Features Analyzed

**Demographics (5 features)**:
- Estimated household income
- Household size
- Total energy burden (% of income spent on energy)
- Living area (square feet)
- House age (years)

**Campaign Exposure (6 features)**:
- Total campaign count
- Email count
- Text count (NEW)
- Postal count
- Channel diversity
- Exposure duration (days)

**Message Types (6 features)**:
- Informational campaign count
- Motivational/struggle campaign count
- Personalized qualification campaign count
- Relief/reassurance campaign count
- Savings/financial campaign count
- Urgency/deadline campaign count

---

## How We Did It (Methodology)

### Progressive Clustering Approach

We used a three-phase progressive clustering methodology:

**Phase 1: Demographics Only** (Baseline)
- Algorithm: FAMD + K-Prototypes
- Result: 3 clusters, p=0.0001 (significant)
- Engagement range: 6.1% - 10.3%

**Phase 2: Demographics + Campaign Exposure + Message Types**
- Algorithm: FAMD + K-Means
- Result: 5 clusters, p=0.0000 (highly significant)
- Engagement range: 6.1% - 18.4%

**Phase 3: Bayesian Probabilistic Clustering**
- Algorithm: BayesianGaussianMixture
- Result: 10 clusters, p=0.0000 (extremely significant)
- Engagement range: 3.3% - 41.1%

---

## The 10 Participant Segments

### High Engagement Clusters

| Cluster | Name | Size | Engagement | Key Characteristics |
|---------|------|------|------------|---------------------|
| **3** | Super Performers | 292 (3.9%) | **41.1%** | Moderate exposure (26 campaigns), balanced channels, strong motivational + personalized messaging |
| **8** | High-Frequency Responders | 481 (6.5%) | **19.1%** | High email exposure (36 avg), high savings messaging (21 avg), affluent ($36K income) |
| **7** | High-Burden Engagers | 146 (2.0%) | **17.8%** | Very high energy burden (33%), older homes (100 yrs), responds to urgency |
| **6** | Moderate Responders | 519 (7.0%) | **11.9%** | Moderate exposure, email-focused, standard demographics |
| **0** | Multi-Channel Active | 404 (5.4%) | **9.7%** | Highest exposure (60 campaigns), all channels, all message types |

### Low Engagement Clusters

| Cluster | Name | Size | Engagement | Key Characteristics |
|---------|------|------|------------|---------------------|
| **4** | New/Minimal Exposure | 549 (7.4%) | 7.7% | Very low exposure (6 campaigns), text-heavy, short duration |
| **9** | Moderate Text Users | 883 (11.9%) | 7.1% | Balanced email/text, lower income ($21K), mixed messaging |
| **5** | Low-Exposure Email Only | 1,386 (18.6%) | 6.2% | Email-only, very low text, high energy burden (17.6%) |
| **2** | Standard Participants | 1,371 (18.4%) | 4.3% | Moderate exposure, balanced channels, average demographics |
| **1** | Email Baseline | 1,420 (19.1%) | 3.3% | Low exposure (20 campaigns), email-only, no text engagement |

---

## Key Insights & Patterns

### 1. Text Messaging is Dramatically More Effective

```
Text Reply Rate:    11.54%  ████████████
Email Click Rate:    2.18%  ██
Improvement:         5.3x higher engagement
```

**Why this matters**: Text messages achieve 5x better engagement with significantly lower effort. The "personal" nature of texting appears to break through communication barriers.

### 2. High Engagement Profiles

Participants most likely to engage share these characteristics:
- **Campaign Count**: 26-37 campaigns (not too few, not overwhelming)
- **Channel Mix**: Both email AND text (channel diversity = 2)
- **Message Types**: High personalized + motivational messaging
- **Income**: $30K-$40K range (middle of our distribution)
- **Energy Burden**: 7-10% (moderate, not extreme)

### 3. Message Type Impact

| Message Type | High Engagement Avg | Low Engagement Avg | Difference |
|--------------|--------------------|--------------------|------------|
| Motivational/Struggle | 17.4 | 8.8 | +99% |
| Personalized Qualified | 16.3 | 8.7 | +88% |
| Urgency/Deadline | 11.7 | 6.2 | +88% |
| Savings/Financial | 19.7 | 13.0 | +51% |
| Informational | 6.1 | 3.8 | +60% |
| Relief/Reassurance | 6.4 | 4.6 | +39% |

### 4. The "Super Performer" Profile (Cluster 3)

These 292 participants achieve **41.1% engagement** - nearly 5x the average:
- **Income**: $29,888 (slightly above median)
- **Energy Burden**: 10.1% (moderate)
- **Campaign Exposure**: 26.3 campaigns (balanced)
- **Channel Mix**: 18 email + 8 text (multi-channel)
- **Key Message Types**: Personalized (13), Motivational (11), Savings (17)

---

## Recommendations

### 1. Prioritize Text Campaigns

Text campaigns deliver 5.3x better engagement. Consider:
- Increasing text campaign frequency
- Converting low-performing email campaigns to text
- Using text for time-sensitive messages (urgency/deadline)

### 2. Target the "Sweet Spot"

Optimal engagement occurs with:
- 25-40 total campaign touches
- Mix of email AND text
- Heavy emphasis on personalized + motivational messaging

### 3. Re-engage Low-Exposure Participants

Cluster 4 (549 participants) has only 6 campaigns average but 7.7% engagement:
- These participants are responsive when reached
- Consider dedicated re-engagement campaign

### 4. Segment-Specific Strategies

| Cluster | Strategy |
|---------|----------|
| Super Performers (3) | Maintain current approach, use as template |
| High-Burden (7) | Focus on urgency/deadline messaging |
| New/Minimal (4) | Increase touch frequency across channels |
| Email Baseline (1) | Add text component to existing campaigns |

---

## Technical Appendix

### Model Performance

| Phase | Silhouette | Bootstrap ARI | Chi-square p-value |
|-------|------------|---------------|-------------------|
| Phase 1 | 0.239 | - | 0.0001 |
| Phase 2 | 0.323 | - | 0.0000 |
| Phase 3 | 0.183 | 0.666 | 0.0000 |

### Files Generated

| File | Description |
|------|-------------|
| participant_features.parquet | Full feature dataset (7,451 participants) |
| phase3_clustered_participants.parquet | Final cluster assignments |
| cluster_probabilities.npy | Soft cluster memberships for Bayesian integration |
| phase3_bayesian_integration.parquet | Ready for PyMC modeling |

### Bayesian Integration

Cluster probabilities are saved for downstream causal modeling:

```python
import pymc as pm

with pm.Model() as causal_model:
    # Cluster membership adjustment
    beta_cluster = pm.Normal('beta_cluster', mu=0, sigma=1, shape=n_clusters-1)

    # Treatment effect
    beta_treatment = pm.Normal('beta_treatment', mu=0, sigma=1)

    # Linear predictor with cluster adjustment
    logit_p = pm.math.dot(cluster_probs[:, :-1], beta_cluster) + ...
```

---

## Appendix: Data Integrity Checks

### Text Campaign Verification

| Check | Result |
|-------|--------|
| Text campaigns in database | 74 campaigns |
| Text exposures | 46,004 records |
| Text engagement tracking | `text_replied` field present |
| Consistency check | 100% aligned with `unified_status` |

### Cross-Channel Overlap

| Category | Count | Percentage |
|----------|-------|------------|
| Email only | 3,170 | 42.5% |
| Text only | 373 | 5.0% |
| Both channels | 3,908 | 52.4% |
| **Total** | **7,451** | 100% |

---

*Generated by Analysis-03 Pipeline*
*Source: /src/analysis/analysis-03/*
