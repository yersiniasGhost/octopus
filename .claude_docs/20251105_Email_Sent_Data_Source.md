# Email Campaign "Sent" Data Source - 2025-11-05

## Question
Where does the "Sent" number come from for email campaigns in the dashboard?

## Answer

The "Sent" number comes from **TWO POSSIBLE SOURCES** with a fallback priority:

### Primary Source (Preferred)
**`participants` collection** - Count of participant documents per campaign

- **Location**: `emailoctopus_db.participants`
- **Method**: MongoDB aggregation counting documents by `campaign_id`
- **Code**: `app/routes/main.py:176-187`

```python
# Get participant counts per campaign
participant_counts = {}
if campaign_id_to_name:
    pipeline = [
        {'$match': {'campaign_id': {'$in': list(campaign_id_to_name.keys())}}},
        {'$group': {
            '_id': '$campaign_id',
            'total_sent': {'$sum': 1}  # Count participants
        }}
    ]
    for result in db.participants.aggregate(pipeline):
        participant_counts[result['_id']] = result['total_sent']
```

### Fallback Source (Secondary)
**`campaign.statistics.sent.unique`** field from campaigns collection

- **Location**: `emailoctopus_db.campaigns[].statistics.sent.unique`
- **Used When**: Participant count is 0
- **Code**: `app/routes/main.py:196-199`

```python
# Use participant count for sent, fall back to statistics
sent_count = participant_counts.get(campaign_id, 0)
if sent_count == 0:
    sent_count = stats_data.get('sent', {}).get('unique', 0)
```

## Data Flow Diagram

```
Email Dashboard Request
         ↓
1. Query campaigns collection
   - Filter: {'campaign_type': 'email'}
   - Get: campaign_id, name, statistics
         ↓
2. Query participants collection
   - Match: campaign_id in email campaign IDs
   - Count: participants per campaign_id
   - Result: participant_counts dictionary
         ↓
3. For each campaign, determine "Sent" value:

   If participant_count > 0:
      ✅ sent = participant_count
      (PRIMARY SOURCE - actual participants)

   Else if campaign.statistics.sent.unique > 0:
      ⚠️  sent = campaign.statistics.sent.unique
      (FALLBACK SOURCE - campaign stats)

   Else:
      sent = 0
         ↓
4. Display in charts
```

## Example: Actual Data

### Sample Campaign: OHCAC_FinalDays_20250929

**Campaign Statistics Field:**
```json
{
  "statistics": {
    "sent": {
      "unique": 0  // Not used - this is 0
    }
  }
}
```

**Participants Collection Count:**
```
db.participants.count_documents({'campaign_id': 'd1ebd096-9d5f-11f0-8c43-839344cab414'})
→ 1939 participants  // ✅ This is used
```

**Result Displayed:**
- **Sent: 1,939** (from participants count, not from statistics field)

## Why This Approach?

### Accuracy
- **Participants collection** is the source of truth for who actually received the email
- Each participant document represents a real person who was contacted
- More accurate than campaign-level aggregate statistics

### Data Integrity
- Campaign statistics may not be synced or updated
- Participant-level tracking provides granular, verifiable data
- Fallback ensures charts show *something* even if participants aren't populated

### Current State
- **Most email campaigns** have 0 in `campaign.statistics.sent.unique`
- **All actual sent counts** come from counting participants
- The fallback to `statistics.sent.unique` is rarely used

## Related Code Locations

### Query Campaign Data
**File**: `app/routes/main.py:163-167`
```python
campaigns = list(db.campaigns.find(
    {'campaign_type': 'email'},
    {'name': 1, 'campaign_id': 1, 'statistics': 1, '_id': 0}
).sort('sent_at', -1).limit(20))
```

### Count Participants
**File**: `app/routes/main.py:176-187`
```python
participant_counts = {}
if campaign_id_to_name:
    pipeline = [
        {'$match': {'campaign_id': {'$in': list(campaign_id_to_name.keys())}}},
        {'$group': {
            '_id': '$campaign_id',
            'total_sent': {'$sum': 1}
        }}
    ]
    for result in db.participants.aggregate(pipeline):
        participant_counts[result['_id']] = result['total_sent']
```

### Apply Fallback Logic
**File**: `app/routes/main.py:196-199`
```python
# Use participant count for sent, fall back to statistics
sent_count = participant_counts.get(campaign_id, 0)
if sent_count == 0:
    sent_count = stats_data.get('sent', {}).get('unique', 0)
```

### Build Chart Data
**File**: `app/routes/main.py:204-209`
```python
chart_data_items.append({
    'name': name,
    'sent': sent_count,      # This is the final "Sent" value
    'opened': opened_count,
    'clicked': clicked_count
})
```

## Database Collections Involved

### emailoctopus_db.campaigns
- **Purpose**: Campaign metadata and aggregate statistics
- **Count**: 69 email campaigns
- **Used For**: Campaign names, IDs, fallback statistics

### emailoctopus_db.participants
- **Purpose**: Individual recipient records for each campaign
- **Count**: 129,483 participant documents
- **Used For**: PRIMARY source for "Sent" counts via aggregation

## Summary

**Short Answer**: The "Sent" number primarily comes from **counting participant documents** in the `participants` collection, grouped by `campaign_id`. It only falls back to the `campaign.statistics.sent.unique` field when no participants exist for that campaign.

**In Practice**: Almost all email campaigns use the participant count because the campaigns collection statistics fields are typically 0.
