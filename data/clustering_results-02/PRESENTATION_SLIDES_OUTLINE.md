# Clustering Analysis Presentation
## Slide Deck Outline for Team Meeting

---

## Slide 1: Title

**Participant Clustering Analysis**
*What Drives Engagement with Our Energy Campaigns?*

December 7, 2025
Analysis of 7,078 Participants

---

## Slide 2: The Challenge

- Overall engagement rate: **2.18%**
- 154 engaged out of 7,078 participants
- Question: Who engages, and why?

*"Can we identify patterns to improve our outreach?"*

---

## Slide 3: What We Analyzed

**14 Features Across 3 Categories:**

| Demographics | Campaign Exposure | Message Types (NEW) |
|--------------|-------------------|---------------------|
| Income | # Campaigns | Informational |
| Household Size | # Emails | Motivational |
| Energy Burden | Days of Exposure | Personalized |
| House Size | | Savings |
| House Age | | Urgency |
| | | Relief |

---

## Slide 4: The Big Finding

# Message Type > Demographics

**Personalized messaging is the #1 predictor**
- +171% engagement impact
- More important than income
- More important than energy burden

---

## Slide 5: The 9 Segments

**Visual: Engagement Rate by Cluster**

[Insert bar chart from cluster_validation_report.png - middle top panel]

- Highest: 11.9% (Cluster 0)
- Lowest: 0.4% (Cluster 4)
- Range: **30x difference** between best and worst

---

## Slide 6: Spotlight - Top Performers (Cluster 0)

**84 participants | 11.9% engagement**

| What's Different? | |
|-------------------|---|
| Engagement | 6x average |
| Time to Convert | 120 days (not 159) |
| Campaigns Needed | Fewer than average |

**Key Insight:** They're "ready to engage"—don't need extensive nurturing

---

## Slide 7: Spotlight - The Untapped Opportunity (Cluster 4)

**284 participants | 0.4% engagement**

| The Problem | |
|-------------|---|
| Demographics | Average |
| Campaigns Received | Only 2 |
| Exposure Duration | 9 days |

**Question:** Why weren't they contacted?
- New to database?
- Early unsubscribes?
- Technical issues?

**Action:** Investigate immediately

---

## Slide 8: The Income Paradox

| Cluster | Income | Engagement |
|---------|--------|------------|
| 5 (Low engagement) | $7,500 | 1.1% |
| 6 (Good engagement) | $7,633 | **2.7%** |
| 7 (Low engagement) | $34,513 | 1.9% |
| 2 (Good engagement) | $38,157 | **3.1%** |

**Conclusion:** Income doesn't determine engagement—messaging does

---

## Slide 9: What Predicts Engagement?

**Feature Impact Ranking:**

| Feature | Impact |
|---------|--------|
| Personalized Messaging | **+171%** |
| Savings Focus | +105% |
| Campaign Count | +96% |
| Urgency Messaging | +96% |
| Motivational Content | +64% |
| Informational Content | +63% |

---

## Slide 10: Cluster 5 vs 6 - A Natural Experiment

**Same Income, Different Results**

| | Cluster 5 | Cluster 6 |
|---|-----------|-----------|
| Income | $7,500 | $7,633 |
| Energy Burden | 60% | 43% |
| **Engagement** | **1.1%** | **2.7%** |
| Personalized Messages | 6.2 | **11.0** |

**The difference: 77% more personalized messaging**

---

## Slide 11: Recommendations - Immediate

| Action | Target | Owner |
|--------|--------|-------|
| 🔴 Investigate minimal exposure | 284 in Cluster 4 | Data Team |
| 🔴 Increase personalization | 2,162 in Cluster 1 | Campaign Team |
| 🟡 Compare C5 vs C6 messaging | Learn what works | Analytics |

---

## Slide 12: Recommendations - Strategic

1. **Fast-Track Model**: Identify "Top Performer" profiles early
2. **Personalization Push**: Increase personalized content across all segments
3. **Affluent Reframe**: Test environmental/comfort messaging for Clusters 7 & 9
4. **Multi-Channel Pilot**: Phone/community outreach for extreme-burden (Cluster 5)

---

## Slide 13: A/B Testing Roadmap

| Test | What We'll Learn |
|------|------------------|
| +50% Personalization | Does it improve all segments? |
| 90-Day Accelerated | Can we convert faster? |
| Affluent Messaging | What resonates with high-income? |
| Phone + Email | Does multi-channel help Cluster 5? |

---

## Slide 14: Technical Validation

| Metric | Value | Meaning |
|--------|-------|---------|
| Statistical Significance | p < 0.0001 | Real differences, not chance |
| Cluster Stability | 0.878 ARI | Reproducible results |
| Assignment Confidence | 99.6% | High certainty |

**Method:** Bayesian Gaussian Mixture Model with 14 features

---

## Slide 15: Summary

**Three Key Takeaways:**

1. **Personalization wins** (+171% impact on engagement)
2. **Income isn't destiny** (messaging matters more)
3. **284 participants untapped** (investigate Cluster 4)

**Next Step:** Review recommendations and assign owners

---

## Appendix Slides

### A1: Full Cluster Table

| ID | Name | N | Engagement |
|----|------|---|------------|
| 0 | Top Performers | 84 | 11.9% |
| 1 | Baseline Low Exposure | 2,162 | 2.0% |
| 2 | High Exposure Affluent | 890 | 3.1% |
| 3 | Standard Participants | 1,680 | 2.6% |
| 4 | Minimal Exposure | 284 | 0.4% |
| 5 | Extreme Energy Burden | 93 | 1.1% |
| 6 | High Burden, Engaged | 150 | 2.7% |
| 7 | Affluent, Standard Msg | 1,001 | 1.9% |
| 9 | Affluent, Lower Msg | 732 | 1.8% |

### A2: Methodology Overview

**Three-Phase Progressive Clustering:**

1. **Phase 1**: Demographics only → NOT significant (p=0.85)
2. **Phase 2**: + Exposure + Message Types → SIGNIFICANT (p=0.008)
3. **Phase 3**: BayesianGMM → HIGHLY SIGNIFICANT (p<0.0001)

### A3: Data Files

All outputs in `data/clustering_results-02/`:
- `CLUSTERING_ANALYSIS_REPORT.md` - Full report
- `EXECUTIVE_SUMMARY_ONE_PAGER.md` - Quick reference
- `CLUSTER_DEFINITIONS.md` - Technical definitions
- `*.png` - Visualizations
- `*.parquet` - Data files

---

## Speaker Notes

**Slide 4 (Big Finding):** This is the headline. Emphasize that we've been thinking about this wrong—it's not about WHO we're reaching, it's about HOW we're messaging them.

**Slide 6 (Top Performers):** Point out the counterintuitive finding that they receive FEWER campaigns and convert FASTER. They don't need nurturing.

**Slide 7 (Cluster 4):** This should generate discussion. We need to understand why these 284 people fell through the cracks.

**Slide 8 (Income Paradox):** This is important for stakeholders who might assume we should only target low-income. The data says messaging matters more.

**Slide 10 (C5 vs C6):** This is the most actionable insight. Same demographics, different messaging, very different outcomes.

---

*Deck designed for 20-30 minute presentation with Q&A*
