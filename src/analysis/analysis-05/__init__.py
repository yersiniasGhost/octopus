"""
Analysis-05: Applicant-Centric Clustering with Message Classification Focus

Extends Analysis-05 with dedicated message classification analysis to understand
which message types (personalized, urgent, financial, etc.) drive applications.

Pipeline:
1. Extract Features - Participant+applicant data with message type exposure
2. Phase 1 - Demographics baseline clustering
3. Phase 2 - Demographics + Channel + Message type exposure clustering
4. Phase 2b - MESSAGE CLASSIFICATION EFFECTIVENESS ANALYSIS (NEW)
   - Which message types correlate with higher conversion?
   - Message type by channel interaction effects
   - Optimal message mix identification
5. Phase 3 - Bayesian GMM with message type emphasis for causal modeling
6. UMAP - Enhanced visualizations including message type patterns

Message Types Analyzed:
- informational: Educational content about program
- motivational_struggle: Empathy-based messaging
- personalized_qualified: Pre-qualification, personalized
- relief_reassurance: Anxiety-reducing messaging
- savings_financial: Financial benefit emphasis
- urgency_deadline: Time-limited offers

Key additions over Analysis-05:
- Dedicated message classification effectiveness report
- Message type x channel interaction analysis
- Per-message-type conversion rate analysis
- Message exposure optimization recommendations
"""
