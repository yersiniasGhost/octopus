# Presentation Slides Outline
## Campaign Effectiveness Analysis: What Drives Applications?

**Recommended Duration**: 15-20 minutes
**Audience**: Program leadership, marketing team, stakeholders

---

## Slide 1: Title Slide

**Title**: What Drives Program Applications?
**Subtitle**: Multi-Channel Campaign Effectiveness Analysis

- Date: December 2025
- Presented by: Data Science Team
- Analysis: Applicant-Centric Clustering (Analysis-04)

---

## Slide 2: Executive Summary

**Key Takeaway**: Text messaging converts 3x better than email

| Channel | App Rate |
|---------|----------|
| Text Only | 4.29% |
| Email Only | 1.42% |

**Call to Action**: Add text to email-only contacts

---

## Slide 3: The Analysis Framework

**Question**: What drives someone to apply?

**Approach**:
1. Analyze 7,473 campaign participants
2. Track 240 conversions (applications)
3. Compare demographics, channels, and message types
4. Identify high-value segments

**Visual**: Funnel diagram showing participants → applicants

---

## Slide 4: Data Overview

**What We Analyzed**:
- 7,473 participants across all campaigns
- 143 campaigns (68 email, 74 text)
- Letters/mailers sent to everyone (baseline)
- 240 program applications (3.21% conversion)

**Visual**: Pie chart of channel distribution

---

## Slide 5: Finding #1 - Channel Impact

**Text Outperforms Email**

| Channel Strategy | Conversion Rate | Lift |
|------------------|-----------------|------|
| Letter + Text | 4.29% | +34% |
| Letter + Both | 3.81% | +19% |
| Letter + Email | 1.42% | -56% |

**Visual**: Bar chart comparing channel performance

**Key Insight**: Text recipients convert at 3x the rate of email-only

---

## Slide 6: Finding #2 - Where Conversions Come From

**Conversion Channel Attribution (UTM)**

- Text: 46% of applications
- Letter: 25% of applications
- Unknown: 29%

**Visual**: Pie chart of conversion sources

**Key Insight**: Nearly half of all conversions came through text

---

## Slide 7: Finding #3 - Segment Identification

**We Identified 10 Distinct Segments**

| Segment | Size | App Rate | Action |
|---------|------|----------|--------|
| Super Converters | 448 | 23.4% | Priority follow-up |
| High Propensity | 545 | 7.9% | Increase text |
| Email Fatigued | 1,345 | 0.8% | Pause email |
| Non-Responders | 1,188 | 0.1% | Data cleanup |

**Visual**: Scatter plot from UMAP colored by segment

---

## Slide 8: Deep Dive - Super Converters (Cluster 0)

**Profile**:
- 448 participants (6% of total)
- 23.4% conversion rate (7.3x lift!)
- Predominantly letter-only responders
- Quick decision makers

**Recommendation**: Immediate phone follow-up for similar profiles

**Visual**: Highlight cluster in UMAP plot

---

## Slide 9: Deep Dive - Email-Only Problem

**The Problem**:
- 2,878 participants receive email only
- Only 1.42% conversion (worst performing)
- High email volume (15+ campaigns avg)

**The Opportunity**:
- Adding text could increase to 3.8-4.3%
- Estimated: +70 additional applications

**Visual**: Before/after projection chart

---

## Slide 10: Deep Dive - Email Fatigue

**The Problem**:
- 1,345 participants in "fatigue" segment
- 35+ email campaigns received
- Only 0.82% conversion
- Continuing email wastes resources

**Recommendation**:
- Pause email campaigns
- Try text or direct mail
- Consider re-engagement strategy

**Visual**: Campaign count vs conversion rate scatter

---

## Slide 11: Message Type Analysis

**Which Messages Work?**

| Message Type | Avg Exposure | App Rate |
|--------------|--------------|----------|
| Savings/Financial | 14.6 | 2.92% |
| Motivational | 10.9 | 2.98% |
| Personalized | 10.5 | 2.92% |
| Urgency/Deadline | 7.5 | 2.92% |
| Informational | 4.4 | 3.03% |

**Key Insight**: Message type matters less than channel

---

## Slide 12: Visualization - UMAP Dashboard

**Visual**: umap_summary_dashboard.png (4-panel)

1. Applicant distribution (red dots)
2. Cluster structure (10 colors)
3. Channel patterns
4. Text campaign intensity

---

## Slide 13: Limitations & Cautions

**What This Analysis Shows**:
- Observational correlations
- Segment identification
- Channel performance differences

**What It Doesn't Show (Yet)**:
- Causal effects (selection bias possible)
- Why text works better
- Individual-level predictions

**Next Step**: Bayesian causal modeling to confirm effects

---

## Slide 14: Recommendations Summary

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| 1 | Add text to email-only segment | +70 applications |
| 2 | Phone follow-up for high-propensity | +50 applications |
| 3 | Pause email for fatigued segment | Cost savings |
| 4 | Clean non-responder data | Improve metrics |

**Total Estimated Impact**: +120 applications (50% increase)

---

## Slide 15: Next Steps

**Immediate (This Week)**:
- Identify email-only contacts for text addition
- Create high-propensity phone list
- Pause campaigns to fatigued segment

**Short-term (This Month)**:
- Build Bayesian causal model
- Estimate true treatment effects
- Design A/B test for text expansion

**Long-term**:
- Predictive model for targeting
- Automated channel optimization
- Real-time segment updates

---

## Slide 16: Appendix - Methodology

**Three-Phase Analysis**:

1. **Phase 1**: Demographics-only clustering
   - FAMD + K-Means
   - Modest predictive power

2. **Phase 2**: Add channel exposure
   - Dramatic improvement
   - Channel combo most predictive

3. **Phase 3**: Probabilistic clustering
   - Bayesian GMM
   - Soft assignments for causal modeling

---

## Slide 17: Appendix - Data Sources

**Databases**:
- campaign_data MongoDB (7,473 participants)
- applications collection (296 applications)

**Campaigns**:
- 68 email campaigns (EmailOctopus)
- 74 text campaigns (RumbleUp)
- Letters/mailers (baseline to all)

**Matching**:
- 81% of applications matched to participants
- UTM attribution for 71%

---

## Slide 18: Appendix - Technical Details

**Algorithms Used**:
- FAMD (Factor Analysis of Mixed Data)
- K-Means clustering
- Bayesian Gaussian Mixture
- UMAP visualization

**Output Files**:
- `phase3_bayesian_integration.parquet`
- `phase3_cluster_probs.npy`
- `CLUSTER_DEFINITIONS.md`

---

## Slide 19: Q&A

**Contact**: Data Science Team

**Files Available**:
- Full analysis report
- Cluster definitions
- Visualization dashboard
- Raw data exports

---

## Speaker Notes

### For Slide 5 (Channel Impact):
"This is the key finding. When we compare participants who received text messages versus those who only received email, we see a dramatic difference. Text recipients convert at 4.29% compared to just 1.42% for email-only. That's a 3x difference."

### For Slide 9 (Email-Only Problem):
"Here's the opportunity. We have nearly 3,000 people who only receive email campaigns. If we add text messaging to this group and they perform like our text recipients, we could see 70 additional applications."

### For Slide 13 (Limitations):
"I want to be upfront about what this analysis can and cannot tell us. We've identified correlations, but we haven't proven causation yet. It's possible that people who receive text are different in ways we haven't measured. That's why our next step is Bayesian causal modeling."

---

*Presentation outline generated from Analysis-04*
