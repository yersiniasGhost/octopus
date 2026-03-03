# Octopus Codebase Update: campaign_data → empower_development

**Date**: 2026-03-02
**Goal**: Update all Octopus code to align with the unified database schema after the campaign_data → empower_development migration.

---

## Background

A database unification project merged all `campaign_data` collections into `empower_development`:

| What Changed | Old | New |
|---|---|---|
| Database name | `campaign_data` | `empower_development` (campaign_data kept as read-only archive) |
| Exposures collection | `campaign_exposures` | `exposures` |
| Participants collection | Per-campaign contact rows (133K) | Enriched deduplicated profiles (14,360) |
| Campaigns collection | 75 text-only | 149 unified (email + text + mailer + letter) |

The unified schema spec is at: `~/.openclaw/workspace-empower-db/.claude_docs/20260228_1430_db_unification_plan.md`

Campaign sync (`sync_campaigns.py`, `mongodb_writer.py`) is **no longer running** — mark as deprecated.

`app/services/campaign_data_service.py` uses `emailoctopus_db` and `empower` databases (NOT campaign_data) — **leave unchanged**, separate cleanup scope.

---

## Phase 1: Environment & Database Config

### 1.1 `.env` (lines 24-25)

```diff
- MONGODB_OCTOPUS=campaign_data
- MONGODB_CAMPAIGN=campaign_data
+ MONGODB_OCTOPUS=empower_development
+ MONGODB_CAMPAIGN=empower_development
```

### 1.2 `src/tools/mongo.py`

**Docstring** (line 14):
```diff
-     MONGODB_CAMPAIGN: Campaign data database (campaign_data)
+     MONGODB_CAMPAIGN: Campaign data database (empower_development)
```

**Class docstring example** (line 39):
```diff
-         campaign_db = Mongo().get_database('campaign_data')
+         campaign_db = Mongo().get_database('empower_development')
```

**`get_campaign_db()`** (lines 161-172):
```diff
  def get_campaign_db() -> Database:
      """
-     Get the campaign_data database.
+     Get the campaign database (empower_development).

-     Uses MONGODB_CAMPAIGN env var, defaults to 'campaign_data'.
+     Uses MONGODB_CAMPAIGN env var, defaults to 'empower_development'.
      """
      mongo = Mongo()
-     db_name = mongo._env.get_env('MONGODB_CAMPAIGN', 'campaign_data')
+     db_name = mongo._env.get_env('MONGODB_CAMPAIGN', 'empower_development')
      return mongo.get_database(db_name)
```

**`get_collection()`** (lines 187-198):
```diff
- def get_collection(collection_name: str, database: str = 'campaign_data'):
+ def get_collection(collection_name: str, database: str = 'empower_development'):
```

**`ensure_indexes()`** (lines 133-149) — replace old per-campaign participant index with unified schema indexes:
```python
def ensure_indexes(self):
    """Create required indexes for campaign collections."""
    logger.info("Creating database indexes...")

    # Campaigns indexes
    self.database.campaigns.create_index("campaign_id", unique=True)
    self.database.campaigns.create_index("channel")
    self.database.campaigns.create_index("agency")
    self.database.campaigns.create_index("sent_at")
    self.database.campaigns.create_index("status")

    # Participants indexes
    self.database.participants.create_index("participant_id", unique=True)
    self.database.participants.create_index("email")
    self.database.participants.create_index("address.county")
    self.database.participants.create_index("linkage.parcel_id")

    # Exposures indexes
    self.database.exposures.create_index(
        [("participant_id", 1), ("campaign_id", 1)]
    )
    self.database.exposures.create_index("campaign_id")
    self.database.exposures.create_index("unified_status")
    self.database.exposures.create_index("channel")

    logger.info("Indexes created successfully")
```

### 1.3 `client/config.py` (line 30-31)

```diff
-     # MongoDB - Campaign Data (participant tracking)
-     MONGODB_CAMPAIGN_DB = env.get_env('MONGODB_CAMPAIGN', 'campaign_data')
+     # MongoDB - Campaign & Participant Data (unified in empower_development)
+     MONGODB_CAMPAIGN_DB = env.get_env('MONGODB_CAMPAIGN', 'empower_development')
```

---

## Phase 2: Pydantic Models — Full Schema Alignment

**File**: `src/models/campaign_data.py`

This is the largest change. The existing models need to match the unified database schema.

### 2.1 Module docstring

```diff
- """
- Pydantic models for the campaign_data database schema.
+ """
+ Pydantic models for the empower_development unified database schema.

  This module defines the data models for:
  - Participant: Unique person with demographics, residence, and engagement summary
  - Campaign: Campaign metadata with aggregate statistics
- - CampaignExposure: Individual participant × campaign engagement event
+ - Exposure: Individual participant × campaign engagement event
  """
```

### 2.2 UnifiedEngagement enum — add statuses from unified schema

```python
class UnifiedEngagement(str, Enum):
    """Unified engagement status across all channels"""
    NO_ENGAGEMENT = "no_engagement"
    RECEIVED = "received"
    CLICKED = "clicked"
    ENGAGED = "engaged"
    CONVERTED = "converted"
    OPTED_OUT = "opted_out"
    UNDELIVERABLE = "undeliverable"
```

### 2.3 Address — add state field

```python
class Address(BaseModel):
    """Normalized address"""
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    county: Optional[str] = None
    raw: Optional[str] = None
```

### 2.4 New models to add (after Address, before EnergySnapshot)

```python
class SourceIds(BaseModel):
    """Original IDs from source systems for traceability"""
    campaign_data_id: Optional[str] = None
    empower_dev_id: Optional[str] = None


class MigrationMetadata(BaseModel):
    """Migration provenance tracking"""
    source_db: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    migrated_at: Optional[datetime] = None
    reconciled: Optional[bool] = None
    empower_dev_contact_ids: Optional[List[str]] = None


class EmailEngagement(BaseModel):
    """Email channel engagement data"""
    opened: Optional[bool] = None
    opened_at: Optional[datetime] = None
    clicked: Optional[bool] = None
    clicked_at: Optional[datetime] = None
    bounced: Optional[bool] = None
    complained: Optional[bool] = None
    unsubscribed: Optional[bool] = None


class TextEngagement(BaseModel):
    """Text/SMS channel engagement data"""
    delivered: Optional[bool] = None
    read: Optional[bool] = None
    replied: Optional[bool] = None
    opted_out: Optional[bool] = None
    failed: Optional[bool] = None


class PostalEngagement(BaseModel):
    """Postal/mail channel engagement data"""
    delivered: Optional[bool] = None
    response: Optional[str] = None


class ThermalProfile(BaseModel):
    """Thermal load analysis data from county ThermalLoads collection"""
    county: Optional[str] = None
    kwh_cl_intercept: Optional[float] = None
    kwh_cl_r2: Optional[float] = None
    kwh_cl_slope: Optional[float] = None
    kwh_hl_intercept: Optional[float] = None
    kwh_hl_r2: Optional[float] = None
    kwh_hl_slope: Optional[float] = None
    source_collection: Optional[str] = None
    enriched_at: Optional[datetime] = None
```

### 2.5 CampaignStatistics — add missing fields

```python
class CampaignStatistics(BaseModel):
    """Campaign aggregate statistics"""
    total_sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    bounced: int = 0
    failed: int = 0
    unsubscribed: int = 0
    opted_out: int = 0
    complained: int = 0
    received: int = 0
    engaged: int = 0
    receive_rate: float = 0.0
    engage_rate: float = 0.0
```

### 2.6 Campaign model — add unified schema fields

Replace the current Campaign class with:

```python
class Campaign(BaseModel):
    """Campaign metadata — unified across all channels and sources."""
    id: Optional[PyObjectId] = Field(None, alias="_id")
    campaign_id: str = Field(..., description="Canonical UUID")

    # Source traceability
    source_ids: SourceIds = Field(default_factory=SourceIds)

    # Identity
    name: str
    name_variants: List[str] = Field(default_factory=list)
    agency: Optional[str] = None
    channel: str = Channel.EMAIL.value
    campaign_type: Optional[str] = None
    message_type: Optional[str] = None
    message_types: Optional[List[str]] = None
    message_body: Optional[str] = None
    target_audience: Optional[str] = None
    status: Optional[str] = None

    # Delivery — email
    subject: Optional[str] = None
    from_name: Optional[str] = None
    from_email_address: Optional[str] = None
    template_id: Optional[str] = None

    # Delivery — text/SMS
    sender_phone: Optional[str] = None
    sms_provider: Optional[str] = None

    # Delivery — print/postal
    print_vendor: Optional[str] = None
    postage_class: Optional[str] = None
    envelope_type: Optional[str] = None
    color_printing: Optional[bool] = None
    double_sided: Optional[bool] = None

    # Cost tracking
    cost_per_send: Optional[float] = None
    total_cost: Optional[float] = None

    # Statistics
    statistics: CampaignStatistics = Field(default_factory=CampaignStatistics)

    # Source
    source_system: str = "emailoctopus"
    source_file: Optional[str] = None

    # Timestamps
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    synced_at: Optional[datetime] = None

    # Migration metadata
    migration: Optional[MigrationMetadata] = Field(None, alias="_migration")

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}
```

### 2.7 CampaignExposure → Exposure (full replacement)

Replace the entire `CampaignExposure` class with:

```python
class Exposure(BaseModel):
    """
    Individual participant × campaign engagement event.

    One document per (participant_id, campaign_id) pair.
    Replaces the old CampaignExposure model.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")

    # Foreign keys
    participant_id: str
    campaign_id: str

    # Denormalized for convenience
    agency: Optional[str] = None
    channel: str = Channel.EMAIL.value
    sent_at: Optional[datetime] = None

    # Channel-specific engagement (nested)
    email_engagement: EmailEngagement = Field(default_factory=EmailEngagement)
    text_engagement: TextEngagement = Field(default_factory=TextEngagement)
    postal_engagement: PostalEngagement = Field(default_factory=PostalEngagement)

    # Unified status
    unified_status: str = UnifiedEngagement.NO_ENGAGEMENT.value

    # Snapshots
    contact_snapshot: ContactSnapshot = Field(default_factory=ContactSnapshot)
    energy_at_send: EnergyAtSend = Field(default_factory=EnergyAtSend)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    migration: Optional[MigrationMetadata] = Field(None, alias="_migration")

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}

    def compute_unified_status(self) -> str:
        """Compute unified engagement status based on channel-specific engagement."""
        if self.channel == Channel.EMAIL.value:
            if self.email_engagement.clicked:
                return UnifiedEngagement.ENGAGED.value
            elif self.email_engagement.opened:
                return UnifiedEngagement.RECEIVED.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        elif self.channel in (Channel.TEXT.value, Channel.TEXT_MORNING.value, Channel.TEXT_EVENING.value):
            if self.text_engagement.replied:
                return UnifiedEngagement.ENGAGED.value
            elif self.text_engagement.read or self.text_engagement.delivered:
                return UnifiedEngagement.RECEIVED.value
            elif self.text_engagement.opted_out:
                return UnifiedEngagement.OPTED_OUT.value
            elif self.text_engagement.failed:
                return UnifiedEngagement.UNDELIVERABLE.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        elif self.channel in (Channel.MAILER.value, Channel.LETTER.value):
            if self.postal_engagement.response:
                return UnifiedEngagement.ENGAGED.value
            elif self.postal_engagement.delivered:
                return UnifiedEngagement.RECEIVED.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        return UnifiedEngagement.NO_ENGAGEMENT.value
```

### 2.8 Participant model — add thermal + migration

Add these fields to the Participant class:

```python
    # Thermal analysis
    thermal: Optional[ThermalProfile] = Field(None)

    # Migration metadata
    migration: Optional[MigrationMetadata] = Field(None, alias="_migration")
```

### 2.9 Keep backward compat alias

At the bottom of the file, add:
```python
# Backward compatibility alias
CampaignExposure = Exposure
```

---

## Phase 3: App Services

### 3.1 `app/services/explore_service.py`

**SYSTEM_PROMPT** (lines 22-47) — Update database descriptions:
```diff
  ## Available Databases
- - **campaign_data**: Campaign and participant engagement data
- - **empower_development**: County-specific demographic, residential, and energy data
+ - **campaign_data**: Read-only archive of raw campaign data (deprecated — use empower_development)
+ - **empower_development**: Primary database with all unified campaign, participant, and county data

  ## Key Patterns
  - County collections are named: {County}CountyDemographic, {County}CountyResidential, {County}ElectricalDB, {County}ThermalLoads
+ - Campaign collections: campaigns (149), participants (14,360), exposures (320,011), applications (409)
```

**Collection names in prompt** (line 44):
```diff
- - Campaign collections: campaigns, participants, campaign_exposures, applications
+ - Campaign collections: campaigns, participants, exposures, applications
```

**`get_collection_stats()`** (lines 669-686) — change from campaign_data to empower_development:
```diff
-         for coll_name in ['campaigns', 'participants', 'applicants']:
+         for coll_name in ['campaigns', 'participants', 'exposures', 'applications', 'applicants']:
              try:
-                 count = self.databases['campaign_data'][coll_name].estimated_document_count()
-                 stats["campaign_data"][coll_name] = count
+                 count = self.databases['empower_development'][coll_name].estimated_document_count()
+                 stats["empower_development"][coll_name] = count
              except Exception:
-                 stats["campaign_data"][coll_name] = 0
+                 stats["empower_development"][coll_name] = 0
```

### 3.2 `app/services/claude_service.py`

**SYSTEM_PROMPT** (lines 29-70) — Update database descriptions:
```diff
  ## Available Databases (pre-connected as `db_campaign` and `db_empower`)
- - **db_campaign**: Campaign and participant engagement data (campaign_data database)
- - **db_empower**: County-specific demographic, residential, and energy data (empower_development database)
+ - **db_campaign**: Campaign, participant, and exposure data (empower_development database)
+ - **db_empower**: Same database — county-specific demographic, residential, and energy data (empower_development database)
+ - Note: Both point to empower_development after database unification.
```

**Collection patterns** (line 44):
```diff
- - Campaign collections: campaigns, participants, campaign_exposures, applications
+ - Campaign collections: campaigns, participants, exposures, applications
```

**`_create_safe_globals()`** (line 217) — update db_campaign binding:
```diff
-             'db_campaign': self.databases['campaign_data'],
+             'db_campaign': self.databases['empower_development'],
```

Also update the databases dict in `__init__` (line 146):
```diff
          self.databases = {
-             'campaign_data': self.client['campaign_data'],
+             'campaign_data': self.client['campaign_data'],  # Archive (read-only)
              'empower_development': self.client['empower_development']
          }
```

### 3.3 `client/services/mongo_service.py`

**Default db name** (line 32):
```diff
-         self.campaign_db_name = env.get_env('MONGODB_CAMPAIGN', 'campaign_data')
+         self.campaign_db_name = env.get_env('MONGODB_CAMPAIGN', 'empower_development')
```

**Participant queries** — the unified schema nests parcel_id inside `linkage`:

Line 102:
```diff
-             participant_cursor = self.db_campaign["participants"].find({}, {"parcel_id": 1})
-             participant_ids = {p.get("parcel_id") for p in participant_cursor if p.get("parcel_id")}
+             participant_cursor = self.db_campaign["participants"].find({}, {"linkage.parcel_id": 1})
+             participant_ids = {p.get("linkage", {}).get("parcel_id") for p in participant_cursor if p.get("linkage", {}).get("parcel_id")}
```

Line 157:
```diff
-         participant_doc = self.db_campaign["participants"].find_one({"parcel_id": parcel_id})
+         participant_doc = self.db_campaign["participants"].find_one({"linkage.parcel_id": parcel_id})
```

Line 348:
```diff
-         doc = self.db_campaign["participants"].find_one({"parcel_id": parcel_id})
+         doc = self.db_campaign["participants"].find_one({"linkage.parcel_id": parcel_id})
```

---

## Phase 4: Analysis Scripts (5 files)

Apply the same two changes to each file:

1. Default `db_name` parameter: `"campaign_data"` → `"empower_development"`
2. Collection reference: `self.db.campaign_exposures` → `self.db.exposures`

### Files:

**`src/analysis/extract_participant_features.py`** (lines 26, 163):
```diff
-     def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "campaign_data"):
+     def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "empower_development"):
...
-         results = list(self.db.campaign_exposures.aggregate(pipeline))
+         results = list(self.db.exposures.aggregate(pipeline))
```

**`src/analysis/analysis-02/extract_participant_features.py`** (lines 26, 163):
Same changes as above.

**`src/analysis/analysis-03/extract_participant_features.py`** (lines 34, 182):
Same changes (different line numbers).

**`src/analysis/analysis-04/extract_applicant_features.py`** (lines 32, 166, 235, 310):
```diff
-     def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "campaign_data"):
+     def __init__(self, mongo_uri: str = "mongodb://localhost:27017", db_name: str = "empower_development"):
...
-     def extract_campaign_exposures(self) -> pd.DataFrame:
+     def extract_exposures(self) -> pd.DataFrame:
...
-         results = list(self.db.campaign_exposures.aggregate(pipeline))
+         results = list(self.db.exposures.aggregate(pipeline))
...
-         exposures_df = self.extract_campaign_exposures()
+         exposures_df = self.extract_exposures()
```

**`src/analysis/analysis-05/extract_applicant_features.py`** (lines 32, 166, 235, 310):
Same changes as analysis-04.

---

## Phase 5: Scripts (~20 files)

For each file, apply:
- `client['campaign_data']` → `client['empower_development']`
- `db.campaign_exposures` → `db.exposures`
- `db['campaign_exposures']` → `db['exposures']`
- Update docstrings/comments mentioning old names

### 5.1 `scripts/ingest_text_campaigns.py`
- Line 3: docstring `campaign_data database` → `empower_development database`
- Line 6: `campaign_data.campaigns` → `empower_development campaigns`
- Line 66: argparse desc `into campaign_data` → `into empower_development`
- Line 81: `db = client['campaign_data']` → `db = client['empower_development']`

### 5.2 `scripts/ingest_text_exposures.py`
- Line 3: docstring `campaign_data database` → `empower_development database`
- Line 12: `campaign_data.participants, campaign_data.campaign_exposures` → `empower_development participants, exposures`
- Line 226: argparse desc
- Line 237: `db = client['campaign_data']` → `client['empower_development']`
- Lines 419, 436: `db.campaign_exposures.insert_many` → `db.exposures.insert_many`
- Lines 507-508: `db.campaign_exposures.count_documents` → `db.exposures.count_documents`

### 5.3 `scripts/ingest_impact_20260110_campaign_tool.py`
- Line 17: docstring
- Line 292: `db = client['campaign_data']` → `client['empower_development']`
- Line 482: `db.campaign_exposures.insert_many` → `db.exposures.insert_many`
- Line 564: `db.campaign_exposures.count_documents` → `db.exposures.count_documents`

### 5.4 `scripts/ingest_impact_winter_campaign_tool.py`
- Same pattern as 5.3 (identical line numbers)

### 5.5 `scripts/ingest_green_applications_tool.py`
- Line 212: `db = client['campaign_data']` → `client['empower_development']`

### 5.6 `scripts/ingest_applications.py`
- Line 48: `db_name: str = "campaign_data"` → `"empower_development"`

### 5.7 `scripts/export_campaign_color_csvs_tool.py`
- Line 352: `db = client['campaign_data']` → `client['empower_development']`

### 5.8 `scripts/export_impact_20260110_csvs_tool.py`
- Line 352: `db = client['campaign_data']` → `client['empower_development']`

### 5.9 `scripts/match_new_participants_county_data.py`
- Line 125: `campaign_db = client['campaign_data']` → `client['empower_development']`

### 5.10 `scripts/attribute_applications_to_campaigns.py`
- Line 48: `db_name: str = "campaign_data"` → `"empower_development"`
- Line 53: `self.exposures = self.db.campaign_exposures` → `self.db.exposures`

### 5.11 `scripts/write_campaign_classifications.py`
- Line 64: `db = client['campaign_data']` → `client['empower_development']`

### 5.12 `scripts/dryrun_text_participant_matching.py`
- Line 54: `db = client['campaign_data']` → `client['empower_development']`

### 5.13 `scripts/generate_data_summary.py`
- Line 166: `db.campaign_exposures.aggregate` → `db.exposures.aggregate`
- Line 233: `'campaign_exposures'` → `'exposures'` in data_sources list

### 5.14 `scripts/visualize_campaign_classifications.py`
- Line 47: `db = client['campaign_data']` → `client['empower_development']`
- Lines 140, 280, 348: Comments/titles mentioning `campaign_data`

### 5.15 `scripts/rematch_campaign_data_tool.py`
- Line 75: `client['campaign_data']` → `client['empower_development']`

### 5.16 `scripts/migrate_to_campaign_data_tool.py`
- Line 141-147: Target database references
- This script was the original migration tool — add note that it's been superseded by the unified migration

### 5.17 `scripts/enrich_thermal_loads.py`
- Line 6: Docstring mentions `campaign_data.participants` → `empower_development participants`

### 5.18 Deprecated: `scripts/sync_campaigns.py`
- Add deprecation notice at top of file:
```python
"""
DEPRECATED: Campaign sync is no longer active.
EmailOctopus campaign data has been unified into empower_development.
This script is preserved for reference only.
"""
```

---

## Phase 6: Tests

### 6.1 `scripts/test_campaign_model.py`
- Update any imports of `CampaignExposure` → `Exposure` (or rely on backward compat alias)
- Verify model instantiation still works against actual documents

### 6.2 `tests/test_comparable_finder.py`
- Check for `campaign_data` references and update if found

---

## Verification Checklist

After all changes:

1. **Grep verification** — no remaining active references to old names:
   ```bash
   # Should only find comments/deprecation notices:
   grep -rn "campaign_data" src/ app/ client/ scripts/ --include="*.py" | grep -v "archive\|deprecated\|read-only\|source_db\|campaign_data_id\|campaign_data_service\|venv/"

   # Should return 0 results:
   grep -rn "campaign_exposures" src/ app/ client/ scripts/ --include="*.py" | grep -v "venv/"
   ```

2. **Model test**:
   ```bash
   cd ~/devel/octopus && venv/bin/python scripts/test_campaign_model.py
   ```

3. **Import test** — verify no import errors:
   ```bash
   cd ~/devel/octopus && venv/bin/python -c "from src.models.campaign_data import Campaign, Participant, Exposure, EmailEngagement, TextEngagement, PostalEngagement, SourceIds, MigrationMetadata, ThermalProfile; print('All models import OK')"
   ```

4. **Flask startup** — verify app starts without errors:
   ```bash
   cd ~/devel/octopus && venv/bin/python -c "from app.services.explore_service import ExploreService; print('ExploreService OK')"
   cd ~/devel/octopus && venv/bin/python -c "from client.services.mongo_service import MongoService; print('MongoService OK')"
   ```

---

## Execution Order

1. Phase 1 (env + DB config) — foundation
2. Phase 2 (models) — needed before services/scripts that import models
3. Phase 3 (app services) — can parallel with Phase 4
4. Phase 4 (analysis scripts) — can parallel with Phase 3
5. Phase 5 (scripts) — bulk changes
6. Phase 6 (tests + verification)

---

## Files Summary

| Phase | Files | Change Type |
|-------|-------|-------------|
| 1 | `.env`, `src/tools/mongo.py`, `client/config.py` | DB name defaults |
| 2 | `src/models/campaign_data.py` | Full model rewrite |
| 3 | `app/services/explore_service.py`, `claude_service.py`, `client/services/mongo_service.py` | DB refs, collection names, query fields |
| 4 | 5 files in `src/analysis/` | DB default + collection name |
| 5 | ~18 files in `scripts/` | DB name + collection name |
| 6 | 2 test files | Import updates |
| **Total** | ~30 files | |

## NOT Changed (Out of Scope)

- `app/services/campaign_data_service.py` — uses `emailoctopus_db` and `empower` databases, separate concern
- `src/sync/campaign_sync.py`, `src/sync/mongodb_writer.py` — sync is deprecated, no functional changes
- County collections ({County}CountyDemographic, etc.) — unchanged in unified schema
