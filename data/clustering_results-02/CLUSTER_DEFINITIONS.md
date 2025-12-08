# Cluster Definitions (v2 - With Message Types)

Participant segments identified by BayesianGaussianMixture clustering on demographics + campaign exposure + **message type features**.

**Analysis Date**: 2025-12-07
**Total Participants**: 7,078
**Overall Engagement Rate**: 2.18%
**Statistical Significance**: Chi-square p=0.0000 (highly significant)

---

## Key Improvement Over v1

This analysis adds **6 message type features** capturing the types of campaign messaging each participant received:
- `informational` - General information campaigns
- `motivational_struggle` - Messaging emphasizing overcoming challenges
- `personalized_qualified` - Personalized qualification messaging
- `relief_reassurance` - Relief and reassurance focused
- `savings_financial` - Financial savings emphasis
- `urgency_deadline` - Time-sensitive urgency messaging

**Result**: Engagement rate spread increased from 7.3% (v1) to **11.9%** (v2)

---

## Cluster Summary Table

| ID | Name | N | % | Engage % | Income | Energy Burden | Campaigns | Key Message Types |
|----|------|---|---|----------|--------|---------------|-----------|-------------------|
| 0 | **Top Performers** | 84 | 1.2% | **11.9%** | $29K | 11% | 16 | Balanced mix |
| 1 | Baseline Low Exposure | 2,162 | 30.5% | 2.0% | $20K | 16% | 12 | Low personalized |
| 2 | High Exposure Affluent | 890 | 12.6% | 3.1% | $38K | 8% | **36** | Max all types |
| 3 | Standard Participants | 1,680 | 23.7% | 2.6% | $23K | 12% | 20 | Mid-range |
| 4 | **Minimal Exposure** | 284 | 4.0% | **0.4%** | $26K | 14% | **2** | Almost none |
| 5 | Extreme Energy Burden | 93 | 1.3% | 1.1% | **$7.5K** | **60%** | 14 | Low personalized |
| 6 | High Burden, Engaged | 150 | 2.1% | 2.7% | $8K | 43% | 20 | Higher personalized |
| 7 | Affluent, Standard Msg | 1,001 | 14.1% | 1.9% | $35K | 8% | 20 | Balanced |
| 8 | Data Anomaly | 2 | 0.0% | 0.0% | $13K | 19% | 6 | N/A (outliers) |
| 9 | Affluent, Lower Msg | 732 | 10.3% | 1.8% | $34K | 12% | 16 | Higher motivational |

---

## Detailed Cluster Profiles

### Cluster 0: "Top Performers" ⭐⭐⭐
**Size**: 84 participants (1.2%)
**Engagement Rate**: **11.9%** (446% above average!)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $28,899 | +10% |
| Household Size | 4.3 | +3% |
| Energy Burden | 11.3% | -18% |
| House Age | 69 years | -7% |
| Campaigns | 16 | -11% |
| Exposure Days | 120 | -24% |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| informational | 1.9 | -21% |
| motivational | 8.9 | -10% |
| personalized | **9.7** | +7% |
| savings | 10.4 | -10% |
| urgency | 4.2 | 0% |
| relief | 0.3 | -72% |

**Profile**: Middle-income participants with lower energy burden, moderate exposure, but **shorter exposure duration** (120 vs 159 days). The **highest engagement rate by far**.

**Key Insight**: This cluster converts quickly with shorter exposure windows. Their balanced message type exposure and lower energy burden suggests they're "ready to engage" participants who don't need extensive nurturing.

**Recommendation**: STUDY THIS GROUP! What drives their quick conversion? Consider accelerated conversion paths for similar profiles.

---

### Cluster 1: "Baseline Low Exposure"
**Size**: 2,162 participants (30.5%)
**Engagement Rate**: 2.0% (near average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $20,017 | -24% |
| Energy Burden | 16.2% | +18% |
| House Age | 74 years | 0% |
| Campaigns | 12 | -33% |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| personalized | **4.0** | **-56%** |
| motivational | 7.0 | -29% |
| savings | 8.0 | -31% |
| urgency | 2.0 | -52% |

**Profile**: The largest segment with below-average income and higher energy burden. Received fewer campaigns overall, especially **low personalized messaging exposure**.

**Recommendation**: Test increased personalized messaging. This segment may respond to more targeted outreach.

---

### Cluster 2: "High Exposure Affluent" ⭐
**Size**: 890 participants (12.6%)
**Engagement Rate**: 3.1% (42% above average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $38,157 | **+45%** |
| Energy Burden | 7.9% | **-42%** |
| House Age | 68 years | -8% |
| Campaigns | **36** | **+100%** |

**Message Type Profile (ALL HIGH):**
| Type | Count | vs Average |
|------|-------|------------|
| informational | **5.0** | +108% |
| motivational | **21.0** | +113% |
| personalized | **19.0** | +109% |
| savings | **20.0** | +72% |
| urgency | **11.0** | +162% |
| relief | **2.0** | +82% |

**Profile**: Affluent households with the **highest campaign exposure** across all message types. Low energy burden indicates financial stability.

**Recommendation**: Continue high-touch engagement. Consider premium content or referral programs.

---

### Cluster 3: "Standard Participants"
**Size**: 1,680 participants (23.7%)
**Engagement Rate**: 2.6% (19% above average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $23,391 | -11% |
| Energy Burden | 11.9% | -13% |
| Campaigns | 20 | +11% |

**Message Type Profile:**

- Moderate across all types
- Slightly elevated personalized (11.0)
- Standard savings (15.0)

**Profile**: The "typical" participant with moderate demographics and engagement. Good baseline comparison group.

**Recommendation**: Use as control group for A/B testing new strategies.

---

### Cluster 4: "Minimal Exposure" ⚠️
**Size**: 284 participants (4.0%)
**Engagement Rate**: **0.4%** (82% below average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $26,162 | 0% |
| Energy Burden | 13.5% | -2% |
| Campaigns | **2** | **-89%** |
| Exposure Days | **9** | **-94%** |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| informational | **0.0** | -100% |
| motivational | **0.0** | -100% |
| personalized | 1.5 | -84% |
| savings | 1.6 | -86% |
| urgency | **0.0** | -100% |

**Profile**: Average demographics but **received almost no campaigns** (only ~2 over ~9 days). Likely new additions or early unsubscribes.

**Recommendation**: INVESTIGATE DATA QUALITY. Why did these participants receive so few campaigns? May represent untapped potential.

---

### Cluster 5: "Extreme Energy Burden"
**Size**: 93 participants (1.3%)
**Engagement Rate**: 1.1% (49% below average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | **$7,500** | **-71%** |
| Energy Burden | **60.1%** | **+338%** |
| House Age | 89 years | +20% |
| Campaigns | 14 | -22% |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| personalized | **6.2** | **-32%** |

**Profile**: Extremely low income with **highest energy burden** (60% of income on energy!). Older homes. Despite urgent financial need, engagement is low.

**Recommendation**: Priority for assistance programs, but may need different outreach approach (phone calls, community events). Financial messaging may feel overwhelming.

---

### Cluster 6: "High Burden, Engaged"
**Size**: 150 participants (2.1%)
**Engagement Rate**: 2.7% (24% above average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $7,633 | -71% |
| Energy Burden | **43.4%** | +216% |
| Campaigns | 20 | +11% |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| personalized | **11.0** | +21% |
| savings | 14.2 | +22% |

**Profile**: Similar to Cluster 5 (low income, high burden) but **engages above average**. Key difference: **more personalized messaging**.

**Key Insight**: Low-income participants CAN engage when given personalized, savings-focused messaging.

**Recommendation**: Model for reaching financially stressed populations. Compare messaging strategy to Cluster 5.

---

### Cluster 7: "Affluent, Standard Messaging"
**Size**: 1,001 participants (14.1%)
**Engagement Rate**: 1.9% (13% below average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | **$34,513** | +31% |
| Energy Burden | 8.2% | -40% |
| Campaigns | 20 | +11% |

**Message Type Profile:**
- Balanced across all types
- Moderate urgency (5.0)

**Profile**: Affluent households with standard exposure but **below-average engagement** despite favorable demographics.

**Recommendation**: Investigate why engagement is low. May need different value proposition (comfort/environmental vs. savings).

---

### Cluster 8: "Data Anomaly" ⚠️
**Size**: 2 participants (0.0%)
**Engagement Rate**: 0.0%

**Profile**: Only 2 records with **1,798 year old houses** (data error). Exclude from analysis.

---

### Cluster 9: "Affluent, Lower Messaging"
**Size**: 732 participants (10.3%)
**Engagement Rate**: 1.8% (17% below average)

| Metric | Value | vs Average |
|--------|-------|------------|
| Estimated Income | $34,044 | +30% |
| Energy Burden | 11.5% | -16% |
| Campaigns | 16 | -11% |

**Message Type Profile:**

| Type | Count | vs Average |
|------|-------|------------|
| motivational | 11.0 | +11% |
| personalized | **8.0** | -12% |
| savings | **8.0** | -31% |

**Profile**: Affluent but **lower savings-focused messaging**. Higher motivational content.

**Recommendation**: Test increased savings and personalized messaging. May be under-served by current campaign mix.

---

## Key Insights for Reporting

### Top Performers (engagement > 3%)
1. **Cluster 0** (11.9%): Quick converters with shorter exposure windows
2. **Cluster 2** (3.1%): Affluent with maximum campaign exposure
3. **Cluster 6** (2.7%): Low income but personalized messaging works
4. **Cluster 3** (2.6%): Standard participants, baseline success

### Underperformers (engagement < 2%)
1. **Cluster 4** (0.4%): Minimal exposure - DATA INVESTIGATION NEEDED
2. **Cluster 5** (1.1%): Extreme energy burden - needs different approach
3. **Cluster 9** (1.8%): Affluent but under-messaged
4. **Cluster 7** (1.9%): Affluent but disengaged - wrong messaging?

### Message Type Impact

| Message Type | Impact on Engagement |
|--------------|---------------------|
| **personalized_qualified** | **+171%** in high-engagement clusters |
| savings_financial | +105% |
| urgency_deadline | +96% |
| campaign_count | +96% |
| motivational_struggle | +64% |
| informational | +63% |
| relief_reassurance | +33% |

### Strategic Implications

| Finding | Action |
|---------|--------|
| Personalized messaging strongest predictor | Increase personalized content for all segments |
| Cluster 0 converts in 120 days vs 159 | Test accelerated conversion paths |
| Cluster 4 barely contacted | Audit campaign distribution pipeline |
| Income NOT the primary driver | Don't exclude low-income from campaigns |
| Energy burden segments CAN engage | Financial stress motivates IF messaging is right |

---

## Technical Notes

- **Algorithm**: BayesianGaussianMixture with Dirichlet process prior
- **Features Used**: 14 total
  - Demographics: estimated_income, household_size, total_energy_burden, living_area_sqft, house_age
  - Exposure: campaign_count, email_count, exposure_days
  - Message Types: 6 types (informational, motivational_struggle, personalized_qualified, relief_reassurance, savings_financial, urgency_deadline)
- **Effective Clusters**: 9 (excluding data anomaly cluster 8)
- **Cluster Confidence**: Mean max probability = 0.996 (very high confidence)
- **Stability**: Bootstrap ARI = 0.878 (highly stable)
- **Chi-square**: p=0.0000 (highly significant)
