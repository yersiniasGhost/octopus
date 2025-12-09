# Presentation Slides Outline
## Campaign Effectiveness: Message Classification Analysis

**Recommended Duration**: 20-25 minutes
**Audience**: Program leadership, marketing team, stakeholders

---

## Slide 1: Title Slide

**Title**: What Messages Drive Applications?
**Subtitle**: Message Classification & Channel Effectiveness Analysis

- Date: December 2025
- Presented by: Data Science Team
- Analysis: Analysis-05 (Message Classification Focus)

---

## Slide 2: Executive Summary

**Key Takeaway**: Text channel + Informational messages = Best results

| Finding | Impact |
|---------|--------|
| Text outperforms email 3x | +2.62pp conversion |
| Informational via text | +5.89pp lift |
| Email-only segment undertreated | +70 potential apps |

**Call to Action**: Shift informational content to text channel

---

## Slide 3: The Analysis Framework

**Question**: Which message types drive applications, and through which channels?

**Approach**:
1. Analyze 7,473 campaign participants
2. Track 6 message types across 143 campaigns
3. Measure channel × message interactions
4. Identify optimal message delivery strategies

**Visual**: Funnel diagram showing messages → channels → applications

---

## Slide 4: Message Types Analyzed

**Six Message Classifications**:

| Type | Description | Avg per Person |
|------|-------------|----------------|
| Informational | Program details, education | 4.4 |
| Motivational/Struggle | Empathy, addressing challenges | 10.9 |
| Personalized/Qualified | Pre-qualification messaging | 10.5 |
| Relief/Reassurance | Anxiety reduction | 5.0 |
| Savings/Financial | Financial benefits emphasis | 14.6 |
| Urgency/Deadline | Time-limited offers | 7.5 |

**Visual**: Icon grid showing each message type

---

## Slide 5: Finding #1 - Channel Still Dominates

**Text Outperforms Email Regardless of Message Type**

| Channel Strategy | Conversion Rate | Lift |
|------------------|-----------------|------|
| Letter + Text | 4.29% | +34% |
| Letter + Both | 3.81% | +19% |
| Letter + Email | 1.42% | -56% |

**Visual**: Bar chart comparing channels

**Key Insight**: Channel choice matters more than message type

---

## Slide 6: Finding #2 - Message × Channel Interactions

**Best Performing Combinations**

| Message Type | Channel | Conversion Lift |
|--------------|---------|-----------------|
| Informational | Text | **+5.89pp** |
| Motivational | Text | +4.62pp |
| Relief/Reassurance | Text | +4.38pp |

**Visual**: Heatmap of message type × channel effectiveness

**Key Insight**: Informational content works best via text

---

## Slide 7: Finding #3 - Message Exposure Patterns

**Nearly Everyone Gets All Message Types**

| Message Type | % Exposed |
|--------------|-----------|
| Savings/Financial | 99.4% |
| Personalized | 99.0% |
| Motivational | 97.3% |
| Relief/Reassurance | 97.1% |

**Implication**: Can't differentiate by "who gets what" - must differentiate by **channel**

**Visual**: Horizontal bar chart of exposure rates

---

## Slide 8: Deep Dive - Informational via Text

**Why Informational + Text Works Best**

**Hypothesis**:
- Informational content is educational, factual
- Text creates immediacy and urgency
- Combination triggers action better than email

**Evidence**:
- 228 participants received informational via text-only
- 6.58% conversion (vs 0.69% unexposed)
- +5.89pp lift over other channels

**Visual**: UMAP plot highlighting informational text responders

---

## Slide 9: Message Clusters Overview

**5 Distinct Message Exposure Profiles**

| Cluster | Size | App Rate | Profile |
|---------|------|----------|---------|
| High Intensity | 427 | 3.98% | Heavy all types |
| Moderate | 2,105 | 3.47% | Balanced mix |
| Medium | 1,995 | 3.41% | Standard exposure |
| Low Exposure | 1,830 | 3.17% | Under-contacted |
| Imbalanced | 1,116 | 2.15% | Gaps in mix |

**Visual**: UMAP cluster visualization

---

## Slide 10: The Email-Only Problem (Revisited)

**2,878 Participants Get Only Email**

- Current conversion: 1.42%
- With text addition (projected): 3.8-4.3%
- **Estimated gain: +70 applications**

**Message Type Opportunity**:
- These participants get all message types via email
- Shifting even ONE type to text could improve results

**Visual**: Before/after projection with message type breakdown

---

## Slide 11: Message Mix Analysis

**Which Combinations Convert Best?**

| Message Mix | N | Conversion |
|-------------|---|------------|
| Letter only (no digital) | 22 | 100% |
| All 6 types | 7,048 | 2.95% |
| 5 types (missing 1) | varies | 3-5% |

**Insight**: More messages ≠ better conversion
The 22 letter-only responders converted without digital

**Visual**: Treemap of message combinations by conversion

---

## Slide 12: Visualization - Message Type Patterns

**Visual**: umap_message_types.png (6-panel grid)

1. Informational exposure intensity
2. Motivational/Struggle patterns
3. Personalized/Qualified distribution
4. Relief/Reassurance coverage
5. Savings/Financial saturation
6. Urgency/Deadline timing

**Note**: Blue circles = Applicants in each panel

---

## Slide 13: Visualization - Message Effectiveness

**Visual**: umap_message_effectiveness.png

- Left: Bar chart ranking message types by effectiveness
- Right: UMAP showing best message type (informational) exposure

**Key Insight**: Informational shows strongest channel-dependent effect

---

## Slide 14: Segment-Specific Recommendations

| Segment | Current State | Recommendation |
|---------|---------------|----------------|
| Email-only (2,878) | All types via email | Add text for informational |
| High propensity (545) | Mixed channels | Increase text frequency |
| Low engagement (1,566) | Email heavy | Switch to text-only |
| Fatigued (1,345) | 35+ emails | Pause all, single text |

**Visual**: Segment flow diagram

---

## Slide 15: Message Optimization Strategy

**Three-Tier Approach**:

**Tier 1: High Priority** (Informational)
- Shift to text channel
- Educational, factual content
- Expected lift: +5.89pp

**Tier 2: Supporting** (Motivational, Relief)
- Supplement via text
- Emotional connection
- Expected lift: +4.5pp

**Tier 3: Reduce** (Savings, Urgency)
- Over-saturated (99%+ exposure)
- Diminishing returns
- Consider reducing frequency

---

## Slide 16: Limitations & Cautions

**What This Analysis Shows**:
- Message type × channel correlations
- Exposure pattern differences
- Segment-level recommendations

**What It Doesn't Show (Yet)**:
- Causal effects of message types
- Optimal message sequence
- Individual-level predictions

**Next Step**: Bayesian causal modeling with message type treatments

---

## Slide 17: Recommendations Summary

| Priority | Action | Expected Impact |
|----------|--------|-----------------|
| 1 | Shift informational to text | +25 applications |
| 2 | Add text for email-only segment | +70 applications |
| 3 | Reduce savings/urgency frequency | Cost savings |
| 4 | Test message sequence optimization | +15 applications |

**Total Estimated Impact**: +110 applications (46% increase)

---

## Slide 18: Next Steps

**Immediate (This Week)**:
- Create text-based informational campaign
- Identify email-only contacts for text addition
- Pause campaigns to fatigued segment

**Short-term (This Month)**:
- Build Bayesian causal model with message effects
- A/B test message type × channel combinations
- Measure incremental lift

**Long-term**:
- Message sequence optimization
- Predictive model for message targeting
- Automated channel × message routing

---

## Slide 19: Appendix - Methodology

**Analysis Pipeline**:

1. **Feature Extraction**: Demographics + channel + message exposures
2. **Phase 1**: Demographics-only clustering (baseline)
3. **Phase 2**: Add channel and message exposure
4. **Phase 2b**: Message classification effectiveness (NEW)
5. **Phase 3**: Bayesian GMM for causal modeling
6. **UMAP**: Enhanced visualizations with message patterns

**Message Classification Source**: Campaign metadata tags

---

## Slide 20: Appendix - Data Sources

**Databases**:
- campaign_data MongoDB (7,473 participants)
- applications collection (296 applications)

**Campaigns**:
- 68 email campaigns
- 74 text campaigns
- 6 message type classifications
- Letters/mailers (baseline to all)

**Matching**:
- 81% of applications matched to participants
- UTM attribution for 71%

---

## Slide 21: Appendix - Message Type Definitions

| Type | Definition | Example |
|------|------------|---------|
| Informational | Facts about program | "The program covers..." |
| Motivational/Struggle | Empathy, challenges | "We understand..." |
| Personalized/Qualified | Pre-qualification | "You may qualify..." |
| Relief/Reassurance | Anxiety reduction | "No cost to you..." |
| Savings/Financial | Financial benefits | "Save $X per year..." |
| Urgency/Deadline | Time limits | "Apply by..." |

---

## Slide 22: Q&A

**Contact**: Data Science Team

**Files Available**:
- Full analysis report
- Message classification report
- Cluster definitions
- UMAP visualizations (including new message panels)
- Raw data exports

---

## Speaker Notes

### For Slide 6 (Message × Channel Interactions):
"This is the new finding from Analysis-05. When we look at which message types work best, we see that informational content delivered via text shows a nearly 6 percentage point lift. This suggests that educational content about the program works best when delivered with the immediacy of text messaging."

### For Slide 11 (Message Mix):
"Here's something interesting - the 22 people who only received letters converted at 100%. They didn't need any digital messaging. Meanwhile, people who received all 6 message types converted at only 3%. More messages doesn't mean better conversion. It's about the right message through the right channel."

### For Slide 16 (Limitations):
"I want to be clear about what we can and can't conclude. We've identified that informational messages work better via text, but we haven't proven causation yet. It's possible that people who receive informational texts are different in ways we haven't measured. That's why our next step is Bayesian causal modeling."

---

*Presentation outline generated from Analysis-05*
