# Cluster Definitions: Analysis-05

**Purpose**: Detailed profiles of each cluster with message classification insights for targeting and intervention planning.

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

**Message Exposure**:
- Zero or minimal digital message exposure
- Responded to letter/mailer alone
- No message type differentiation possible

**Targeting Recommendation**: Priority segment for immediate follow-up. Consider phone outreach for similar profiles (early responders to mail).

---

### Cluster 3: "High Propensity"
**Size**: 545 participants (7.3%)
**Application Rate**: 7.89% (2.5x lift)
**Confidence**: 100%

**Profile**:
- Multi-channel exposure with emphasis on text
- Moderate campaign count
- Engaged with messaging content

**Message Exposure**:
- Higher than average exposure to all message types
- Responsive to motivational and personalized messaging
- Text channel engagement strong

**Targeting Recommendation**: Increase text campaign frequency. Emphasize informational and motivational content via text.

---

### Cluster 4: "Baseline Responders"
**Size**: 436 participants (5.8%)
**Application Rate**: 3.90% (1.21x lift)
**Confidence**: 100%

**Profile**:
- Mixed channel exposure (email + text)
- Average campaign exposure
- Near-baseline conversion behavior

**Message Exposure**:
- Balanced exposure across message types
- Moderate engagement with savings/financial messages
- Typical multi-channel recipient

**Targeting Recommendation**: Maintain current cadence. Test shifting more content to text channel.

---

### Cluster 8: "Engaged Neutrals"
**Size**: 462 participants (6.2%)
**Application Rate**: 3.25% (1.01x lift)
**Confidence**: 100%

**Profile**:
- Receives campaigns but converts at baseline rate
- No distinguishing channel preference
- Average demographics

**Message Exposure**:
- High message volume received
- No clear message type preference
- May be experiencing message fatigue

**Targeting Recommendation**: A/B test message type reduction. Try focused informational-only via text.

---

### Cluster 6: "Passive Recipients"
**Size**: 415 participants (5.6%)
**Application Rate**: 2.17% (0.68x lift)
**Confidence**: 99.6%

**Profile**:
- Below-baseline conversion
- Receives campaigns but doesn't act
- May have barriers to participation

**Message Exposure**:
- Receiving all message types
- Low engagement signals
- Message mix may not resonate

**Targeting Recommendation**: Test relief/reassurance messaging to address barriers. Simplify message content.

---

### Cluster 5: "Low Engagement"
**Size**: 1,566 participants (21.0%)
**Application Rate**: 1.92% (0.60x lift)
**Confidence**: 100%

**Profile**:
- Large segment with below-average conversion
- Predominantly email recipients
- Lower overall engagement

**Message Exposure**:
- Heavy email exposure, light text
- Savings/financial messages dominant
- May be tuning out repetitive content

**Targeting Recommendation**: Switch to text channel. Reduce savings-focused messaging, increase informational content.

---

### Cluster 2: "Email Fatigued"
**Size**: 1,345 participants (18.0%)
**Application Rate**: 0.82% (0.25x lift)
**Confidence**: 100%

**Profile**:
- High email exposure, very low conversion
- May be experiencing email fatigue
- Long exposure duration

**Message Exposure**:
- 35+ email campaigns received
- All message types sent repeatedly
- No response to any message type via email

**Targeting Recommendation**: Pause email completely. Try single informational text message as re-engagement.

---

### Cluster 1: "Non-Responders"
**Size**: 1,068 participants (14.3%)
**Application Rate**: 0.75% (0.23x lift)
**Confidence**: 100%

**Profile**:
- Very low conversion despite exposure
- Predominantly email-only
- May not be target audience

**Message Exposure**:
- Received multiple message types
- No engagement with any type
- Possible wrong contact info or ineligibility

**Targeting Recommendation**: Reduce frequency. Verify eligibility before further outreach. Consider removal from active campaigns.

---

### Cluster 7: "Dormant"
**Size**: 868 participants (11.6%)
**Application Rate**: 0.23% (0.07x lift)
**Confidence**: 100%

**Profile**:
- Near-zero conversion
- Likely not the target audience
- May have data quality issues

**Message Exposure**:
- Messages delivered but no signal of receipt
- All message types equally ineffective
- Possible deliverability issues

**Targeting Recommendation**: Remove from active campaigns. Data quality review. Check email/phone validity.

---

### Cluster 9: "Inactive"
**Size**: 320 participants (4.3%)
**Application Rate**: 0.00% (0x lift)
**Confidence**: 100%

**Profile**:
- Zero conversions
- Smallest cluster
- Complete non-responders

**Message Exposure**:
- May not be receiving messages at all
- No engagement signals
- Potential bad data

**Targeting Recommendation**: Exclude from campaigns. Clean from database. Do not include in future campaigns.

---

## Phase 2b Message Profile Clusters

These clusters are based on message type exposure patterns, useful for message optimization.

### Message Cluster 1: "High Intensity All Types"
**Size**: 427 participants
**Application Rate**: 3.98% (1.24x lift)
**Dominant Type**: savings_financial (35.3 avg)

**Profile**:
- Received highest volume of all message types
- 60 campaigns on average
- Above-baseline conversion despite high volume

**Message Mix**: Heavy on all types, especially savings/financial and motivational

**Optimization**: This segment responds despite high volume. Continue current approach but test message reduction.

---

### Message Cluster 3: "Moderate Balanced"
**Size**: 2,105 participants
**Application Rate**: 3.47% (1.08x lift)
**Dominant Type**: savings_financial (13.0 avg)

**Profile**:
- Moderate exposure (20 campaigns avg)
- Balanced message type mix
- Slightly above baseline

**Message Mix**: Proportional exposure to all types

**Optimization**: Test increasing informational messages via text channel.

---

### Message Cluster 2: "Medium Exposure"
**Size**: 1,995 participants
**Application Rate**: 3.41% (1.06x lift)
**Dominant Type**: savings_financial (20.5 avg)

**Profile**:
- Medium campaign exposure (33 avg)
- Slightly higher savings messaging
- Near-baseline conversion

**Message Mix**: Moderate savings emphasis

**Optimization**: Shift some savings messages to informational via text.

---

### Message Cluster 4: "Low Exposure"
**Size**: 1,830 participants
**Application Rate**: 3.17% (0.99x lift)
**Dominant Type**: savings_financial (6.7 avg)

**Profile**:
- Low overall exposure (10 campaigns avg)
- Light touch across all types
- Baseline conversion

**Message Mix**: Low volume across all types

**Optimization**: Increase text-based informational outreach. This segment may be under-contacted.

---

### Message Cluster 0: "Imbalanced Mix"
**Size**: 1,116 participants
**Application Rate**: 2.15% (0.67x lift)
**Dominant Type**: savings_financial (12.4 avg)

**Profile**:
- Below-baseline conversion
- Message mix may not resonate
- Lower relief/reassurance exposure

**Message Mix**: Imbalanced with gaps in certain types

**Optimization**: Rebalance message mix. Add relief/reassurance and informational content.

---

## Channel-Message Interaction Matrix

Best message types by channel:

| Channel | Best Message Type | Conversion Lift |
|---------|------------------|-----------------|
| letter+text | Informational | +5.89pp |
| letter+text | Motivational/Struggle | +4.62pp |
| letter+text | Relief/Reassurance | +4.38pp |
| letter+email+text | All types | +0.6pp avg |
| letter+email | All types | Baseline |

---

## Cluster Priority Matrix

| Priority | Cluster | Size | Action |
|----------|---------|------|--------|
| 1 | Cluster 0 (Super) | 448 | Immediate phone follow-up |
| 2 | Cluster 3 (High Prop) | 545 | Increase text + informational |
| 3 | Cluster 5 (Low Engage) | 1,566 | Switch email to text |
| 4 | Cluster 2 (Fatigued) | 1,345 | Pause email, single text |
| 5 | Clusters 7, 9 (Inactive) | 1,188 | Data quality review |

---

## Message Type Recommendations by Cluster

| Cluster | Recommended Message Types | Channel |
|---------|--------------------------|---------|
| Super Converters | N/A (letter-only) | Phone |
| High Propensity | Informational, Motivational | Text |
| Baseline | Informational, Personalized | Text |
| Low Engagement | Informational only | Text |
| Email Fatigued | Single informational | Text |
| Non-Responders | None (reduce contact) | N/A |

---

*Generated from Analysis-05 Pipeline*
