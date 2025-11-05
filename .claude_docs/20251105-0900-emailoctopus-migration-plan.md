Detailed Migration Plan: EmailOctopus DB → EmpowerSave Development DB

  Executive Summary

  This plan outlines migrating 129,483 participant records from emailoctopus_db to empowersave_development database, implementing the
  new schema with Reference classes, and updating the Flask UI.

  Current State Analysis

  Database Status

  - Source: emailoctopus_db.participants (129,483 documents)
  - Target: empowersave_development (currently empty)
  - Schema Evolution: Old flat structure → New reference-based schema

  Current Schema (emailoctopus_db)

  {
    "_id": ObjectId,
    "campaign_id": str,
    "contact_id": str,
    "email_address": str,
    "engagement": {
      "opened": bool,
      "clicked": bool,
      "bounced": bool,
      "complained": bool,
      "unsubscribed": bool
    },
    "fields": {
      "FirstName": str,
      "LastName": str,
      "City": str,
      "ZIP": str,
      "Address": str,
      "kWh": str,
      "annualcost": str,
      "AnnualSavings": str,
      # ... other custom fields
    },
    "status": str,
    "synced_at": datetime
  }

  Target Schema (empowersave_development)

  {
    "_id": ObjectId,
    "contact_id": str,  # email or phone
    "email_address": Optional[str],
    "phone_number": Optional[str],
    "status": str,
    "fields": ParticipantFields,
    "engagements": [  # List of engagements (multi-campaign)
      {
        "campaign_id": str,
        "opened": bool,
        "clicked": bool,
        "bounced": bool,
        "complained": bool,
        "unsubscribed": bool,
        "engaged_at": datetime
      }
    ],
    "residence_ref": {  # NEW
      "county": str,
      "parcel_id": str,
      "address": Optional[str],
      "parcel_city": Optional[str],
      "parcel_zip": Optional[int]
    },
    "demographic_ref": {  # NEW
      "county": str,
      "parcel_id": str,
      "customer_name": Optional[str],
      "email": Optional[str],
      "mobile": Optional[str],
      "annual_kwh_cost": Optional[float],
      "total_energy_burden": Optional[float]
    },
    "synced_at": datetime
  }

  UI Dependencies

  Files Using Participants:
  - app/routes/main.py:107-225 - Dashboard charts (zipcode engagement, campaign stats)
  - app/routes/campaigns.py:119-151 - Campaign participant listings
  - app/templates/campaigns/detail.html - Participant display
  - app/templates/macros/participant_table.html - Participant table rendering

  ---
  Migration Plan

  Phase 1: Data Migration (a - Move Participants)

  Step 1.1: Create Migration Script

  File: scripts/migrate_participants_to_empowersave_db.py

  Tasks:
  1. Connect to both databases
  2. Read participants from emailoctopus_db
  3. Transform schema:
    - Wrap engagement into engagements list
    - Initialize empty residence_ref and demographic_ref
    - Preserve all existing fields
  4. Bulk insert into empowersave_development.participants
  5. Validation and reporting

  Complexity: Medium (3-4 hours)
  Risk: Low - read-only source, new target

  Step 1.2: Add Matching Logic for References

  Dependencies:
  - empower_analytics/src/mongo_models/county_* collections
  - Matching algorithms from scripts/match_csv_to_residence.py

  Tasks:
  1. For each participant:
    - Extract address from fields.Address, fields.City, fields.ZIP
    - Run residence matching against county residential data
    - Run demographic matching against county demographic data
    - Populate residence_ref and demographic_ref if matched
  2. Track match statistics (exact, fuzzy, no_match)

  Complexity: High (6-8 hours)
  Risk: Medium - matching quality varies

  Step 1.3: Create Rollback Strategy

  Tasks:
  1. Export emailoctopus_db.participants to JSON backup
  2. Create indexes on empowersave_development.participants
  3. Document rollback procedure

  Complexity: Low (1-2 hours)
  Risk: Critical safety measure

  ---
  Phase 2: Schema Implementation (a - Use New Schema with References)

  Step 2.1: Update Data Models

  Files to Modify:
  - src/models/participant.py ✅ (Already updated with Reference support)
  - src/models/common.py ✅ (Already has ResidenceReference, DemographicReference)

  Status: Already implemented, no changes needed

  Step 2.2: Create Database Configuration

  File: src/config/database.py (new)

  Tasks:
  1. Create connection manager for empowersave_development
  2. Add environment variable EMPOWERSAVE_DB_NAME
  3. Support both databases during migration period

  Complexity: Low (1-2 hours)

  Step 2.3: Update Database Access Layer

  Files to Create:
  - src/db/participants.py - Participant repository pattern
  - src/db/campaigns.py - Campaign repository pattern

  Tasks:
  1. Abstract database operations
  2. Support querying with Reference filters
  3. Handle multi-campaign engagements

  Complexity: Medium (4-6 hours)

  ---
  Phase 3: UI Updates (b - Update UI to Use New Schema)

  Step 3.1: Update Dashboard Route

  File: app/routes/main.py

  Current Issues:
  - Line 112: Uses emailoctopus_db directly
  - Line 137: Aggregates db.participants for campaign stats
  - Line 196-220: Zipcode engagement aggregation

  Changes Required:
  # BEFORE
  db = client['emailoctopus_db']
  participants = db.participants.aggregate(...)

  # AFTER
  db = client['empowersave_development']
  participants = db.participants.aggregate([
    {'$unwind': '$engagements'},  # Unwind engagements array
    {'$match': {'engagements.campaign_id': campaign_id}},
    # Rest of pipeline...
  ])

  Complexity: Medium (3-4 hours)
  Lines to Update: 112, 115-138, 196-220

  Step 3.2: Update Campaign Routes

  File: app/routes/campaigns.py

  No direct participant queries - Uses EmailOctopus API only
  Status: No changes needed ✅

  Step 3.3: Update Templates

  Files:
  - app/templates/campaigns/detail.html
  - app/templates/macros/participant_table.html

  Changes Required:
  {# BEFORE #}
  {{ participant.engagement.opened }}

  {# AFTER - find engagement for this campaign #}
  {% set campaign_engagement = participant.engagements | selectattr('campaign_id', 'equalto', campaign.id) | first %}
  {{ campaign_engagement.opened if campaign_engagement else false }}

  Complexity: Low (2-3 hours)

  Step 3.4: Add Reference Display

  New Features:
  1. Show residence info when available:
    - Matched address
    - County, parcel ID
  2. Show demographic info when available:
    - Annual kWh cost
    - Energy burden

  Files:
  - app/templates/macros/participant_table.html - Add reference columns
  - app/templates/campaigns/detail.html - Reference detail view

  Complexity: Medium (4-5 hours)

  ---
  Detailed Task Breakdown

  A) Move Participants to empowersave_development

  Task A.1: Create Migration Script (3-4 hours)
  # scripts/migrate_emailoctopus_to_empowersave.py
  - Connect to both databases
  - Batch read participants (1000 at a time)
  - Transform schema:
    * engagement → engagements array
    * Add empty residence_ref, demographic_ref
  - Bulk insert with error handling
  - Progress reporting every 10,000 records
  - Final validation report

  Task A.2: Add Reference Matching (6-8 hours)
  # Extend migration script
  - Import matching logic from match_csv_to_residence.py
  - For each participant:
    * Extract address components
    * Determine county from ZIP
    * Match against county_residential_data
    * Match against county_demographic_data
    * Populate references
  - Track match statistics
  - Generate match quality report

  Task A.3: Create Indexes (1 hour)
  # Create indexes for performance
  db.participants.create_index("contact_id")
  db.participants.create_index("email_address")
  db.participants.create_index("phone_number")
  db.participants.create_index("engagements.campaign_id")
  db.participants.create_index("residence_ref.county")
  db.participants.create_index("residence_ref.parcel_id")

  Total: 10-13 hours

  ---
  B) Update UI to Use New Schema

  Task B.1: Update Database Configuration (1-2 hours)
  # app/__init__.py
  - Add EMPOWERSAVE_DB_NAME config
  - Update mongo connection logic

  Task B.2: Update Dashboard Queries (3-4 hours)
  # app/routes/main.py:137-138
  # OLD
  pipeline = [
    {'$match': {'campaign_id': {'$in': list(campaign_id_to_name.keys())}}},
    {'$group': {'_id': '$campaign_id', 'total_sent': {'$sum': 1}}}
  ]

  # NEW  
  pipeline = [
    {'$unwind': '$engagements'},
    {'$match': {'engagements.campaign_id': {'$in': list(campaign_id_to_name.keys())}}},
    {'$group': {'_id': '$engagements.campaign_id', 'total_sent': {'$sum': 1}}}
  ]

  # app/routes/main.py:196-220
  # OLD
  zipcode_pipeline = [
    {'$match': {'fields.ZIP': {'$exists': True}}},
    {'$group': {
      '_id': '$fields.ZIP',
      'opened_count': {'$sum': {'$cond': ['$engagement.opened', 1, 0]}}
    }}
  ]

  # NEW
  zipcode_pipeline = [
    {'$unwind': '$engagements'},
    {'$match': {'fields.ZIP': {'$exists': True}}},
    {'$group': {
      '_id': '$fields.ZIP',
      'opened_count': {'$sum': {'$cond': ['$engagements.opened', 1, 0]}}
    }}
  ]

  Task B.3: Update Templates (2-3 hours)
  {# app/templates/macros/participant_table.html #}
  {# Add campaign_id parameter #}
  {% macro render_participant_table(participants, campaign_id) %}
    {% for participant in participants %}
      {% set eng = participant.engagements | selectattr('campaign_id', 'equalto', campaign_id) | first %}
      <td>{{ eng.opened if eng else 'No' }}</td>
      <td>{{ eng.clicked if eng else 'No' }}</td>
      
      {# NEW: Show references #}
      {% if participant.residence_ref %}
        <td>{{ participant.residence_ref.address }}</td>
        <td>{{ participant.residence_ref.county }}</td>
      {% endif %}
    {% endfor %}
  {% endmacro %}

  Task B.4: Add Reference Display Features (4-5 hours)
  # New features:
  - Residence info panel in participant detail
  - Demographic info panel (cost, burden)
  - Match quality indicator badge
  - Filter participants by match quality
  - County/parcel linking to external data

  Total: 10-14 hours

  ---
  Implementation Timeline

  Week 1: Data Migration

  - Day 1-2: Create migration script (Task A.1)
  - Day 3-4: Add reference matching logic (Task A.2)
  - Day 5: Testing, validation, backup (Task A.3)

  Week 2: UI Updates

  - Day 1: Update database configuration (Task B.1)
  - Day 2-3: Update dashboard queries (Task B.2)
  - Day 4: Update templates (Task B.3)
  - Day 5: Add reference display features (Task B.4)

  Week 3: Testing & Deployment

  - Day 1-2: Integration testing
  - Day 3: User acceptance testing
  - Day 4: Documentation
  - Day 5: Production deployment

  Total Estimated Time: 20-27 hours of development + 1 week testing

  ---
  Risk Assessment

  | Risk                           | Impact | Probability | Mitigation                           |
  |--------------------------------|--------|-------------|--------------------------------------|
  | Data loss during migration     | High   | Low         | Full backup, dry-run, validation     |
  | Poor match quality             | Medium | Medium      | Manual review of no-match cases      |
  | Performance degradation        | Medium | Low         | Proper indexing, query optimization  |
  | UI breaking changes            | High   | Low         | Comprehensive testing, rollback plan |
  | Multi-campaign engagement bugs | Medium | Medium      | Unit tests for engagement filtering  |

  ---
  Success Criteria

  1. ✅ All 129,483 participants migrated successfully
  2. ✅ >70% of participants have residence matches
  3. ✅ >50% of participants have demographic matches
  4. ✅ Dashboard loads in <2 seconds
  5. ✅ All UI features functional with new schema
  6. ✅ Zero data loss
  7. ✅ Backward compatibility with EmailOctopus API sync

  ---
  Rollback Plan

  If migration fails:
  1. Stop Flask app
  2. Drop empowersave_development.participants collection
  3. Restore from emailoctopus_db (unchanged)
  4. Revert code changes to app/routes/main.py
  5. Restart Flask app
  6. Investigate issue and retry

  ---
  Next Steps

  1. Review this plan - Confirm approach and timeline
  2. Create Task A.1 script - Basic migration without references
  3. Test with 100 records - Validate transformation logic
  4. Add Task A.2 matching - Integrate reference population
  5. Full migration - Run on all 129,483 records
  6. Begin UI updates - Start with Task B.1
