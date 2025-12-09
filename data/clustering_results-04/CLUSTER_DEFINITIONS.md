# Cluster Definitions: Analysis-04

**Purpose**: Detailed profiles of each cluster for targeting and intervention planning.

---

## Phase 3 Probabilistic Clusters (Primary)

These clusters are recommended for Bayesian causal modeling due to soft assignment probabilities.

### Cluster 0: "Super Converters"
**Size**: 448 participants (6.0%)
**Application Rate**: 23.44% (7.3x lift)
**Confidence**: 99.5%

**Profile**:
- Channel: Predominantly letter-only responders (no digital campaign exposure tracked)
- Likely early responders to initial mailings before digital campaigns started
- May represent highly motivated segment that acts on first contact

**Characteristics**:
- Low digital touchpoints
- High response to traditional mail
- Quick decision makers

**Targeting Recommendation**: Priority segment for immediate follow-up. Consider phone outreach.

---

### Cluster 3: "High Propensity"
**Size**: 545 participants (7.3%)
**Application Rate**: 7.89% (2.5x lift)
**Confidence**: 100%

**Profile**:
- Multi-channel exposure with emphasis on text
- Moderate campaign count
- Engaged with messaging content

**Characteristics**:
- Responsive to text messaging
- Above-average household income
- Active digital engagement

**Targeting Recommendation**: Increase text campaign frequency. Test personalized messaging.

---

### Cluster 4: "Baseline Responders"
**Size**: 436 participants (5.8%)
**Application Rate**: 3.90% (1.21x lift)
**Confidence**: 100%

**Profile**:
- Mixed channel exposure (email + text)
- Average campaign exposure
- Near-baseline conversion behavior

**Characteristics**:
- Typical multi-channel participant
- Moderate engagement levels
- Responsive to sustained outreach

**Targeting Recommendation**: Maintain current cadence. Test message optimization.

---

### Cluster 8: "Engaged Neutrals"
**Size**: 462 participants (6.2%)
**Application Rate**: 3.25% (1.01x lift)
**Confidence**: 100%

**Profile**:
- Receives campaigns but converts at baseline rate
- No distinguishing channel preference
- Average demographics

**Characteristics**:
- Neither high nor low responders
- May need different value proposition
- Potential for uplift with right message

**Targeting Recommendation**: A/B test different message types. Survey for preferences.

---

### Cluster 6: "Passive Recipients"
**Size**: 415 participants (5.6%)
**Application Rate**: 2.17% (0.68x lift)
**Confidence**: 99.6%

**Profile**:
- Below-baseline conversion
- Receives campaigns but doesn't act
- May have barriers to participation

**Characteristics**:
- Lower engagement rates
- Potential eligibility concerns
- May need more information

**Targeting Recommendation**: Informational campaigns. Address common barriers.

---

### Cluster 5: "Low Engagement"
**Size**: 1,566 participants (21.0%)
**Application Rate**: 1.92% (0.60x lift)
**Confidence**: 100%

**Profile**:
- Large segment with below-average conversion
- Predominantly email recipients
- Lower overall engagement

**Characteristics**:
- Email-primary exposure
- Lower open/click rates
- May have email deliverability issues

**Targeting Recommendation**: Switch to text channel. Verify email validity.

---

### Cluster 2: "Email Fatigued"
**Size**: 1,345 participants (18.0%)
**Application Rate**: 0.82% (0.25x lift)
**Confidence**: 100%

**Profile**:
- High email exposure, very low conversion
- May be experiencing email fatigue
- Long exposure duration

**Characteristics**:
- 35+ email campaigns received
- Low click rates
- Not responding to email

**Targeting Recommendation**: Pause email, try text or direct mail.

---

### Cluster 1: "Non-Responders"
**Size**: 1,068 participants (14.3%)
**Application Rate**: 0.75% (0.23x lift)
**Confidence**: 100%

**Profile**:
- Very low conversion despite exposure
- Predominantly email-only
- May not be target audience

**Characteristics**:
- Minimal engagement
- Possible wrong contact info
- May be ineligible

**Targeting Recommendation**: Reduce frequency. Verify eligibility before further outreach.

---

### Cluster 7: "Dormant"
**Size**: 868 participants (11.6%)
**Application Rate**: 0.23% (0.07x lift)
**Confidence**: 100%

**Profile**:
- Near-zero conversion
- Likely not the target audience
- May have data quality issues

**Characteristics**:
- No engagement signals
- Possible invalid contacts
- Resource drain

**Targeting Recommendation**: Remove from active campaigns. Data quality review.

---

### Cluster 9: "Inactive"
**Size**: 320 participants (4.3%)
**Application Rate**: 0.00% (0x lift)
**Confidence**: 100%

**Profile**:
- Zero conversions
- Smallest cluster
- Complete non-responders

**Characteristics**:
- No engagement
- No applications
- Potential bad data

**Targeting Recommendation**: Exclude from campaigns. Clean from database.

---

## Phase 2 Channel-Based Clusters (Operational)

For day-to-day campaign decisions, these channel-based clusters are more actionable.

### Channel Cluster 5: "Text-Only Responders"
**Size**: 373 participants
**Application Rate**: 4.29% (1.34x lift)
**Channel Mix**: 100% Letter+Text

**Key Insight**: Highest conversion among digital channels. Text messaging is highly effective for this group.

---

### Channel Cluster 0: "Multi-Channel Moderate"
**Size**: 3,289 participants
**Application Rate**: 3.92% (1.22x lift)
**Channel Mix**: 100% Letter+Email+Text

**Key Insight**: Multi-channel exposure with moderate campaign count. Good baseline segment.

---

### Channel Cluster 3: "Multi-Channel Heavy"
**Size**: 435 participants
**Application Rate**: 3.91% (1.22x lift)
**Channel Mix**: 100% Letter+Email+Text
**Avg Campaigns**: 59.8

**Key Insight**: High campaign exposure doesn't improve conversion. Diminishing returns evident.

---

### Channel Cluster 2: "Email-Dominant"
**Size**: 476 participants
**Application Rate**: 3.15% (0.98x lift)
**Channel Mix**: 71% Letter+Email, 29% Letter+Email+Text

**Key Insight**: Email-heavy mix performs at baseline. Adding text could help.

---

### Channel Cluster 1: "Email-Only"
**Size**: 2,878 participants
**Application Rate**: 1.42% (0.44x lift)
**Channel Mix**: 98% Letter+Email only

**Key Insight**: Email-only is the worst performing channel. Strong candidate for text addition.

---

## Cluster Priority Matrix

| Priority | Cluster | Size | Action |
|----------|---------|------|--------|
| 1 | Cluster 0 (Super) | 448 | Immediate follow-up |
| 2 | Cluster 3 (High Prop) | 545 | Increase text frequency |
| 3 | Ch-Cluster 1 (Email-Only) | 2,878 | Add text channel |
| 4 | Cluster 5 (Low Engage) | 1,566 | Switch to text |
| 5 | Cluster 7, 9 (Inactive) | 1,188 | Data quality review |

---

*Generated from Analysis-04 Pipeline*
