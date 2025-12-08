"""
Pydantic models for the campaign_data database schema.

This module defines the data models for:
- Participant: Unique person with demographics, residence, and engagement summary
- Campaign: Campaign metadata with aggregate statistics
- CampaignExposure: Individual participant × campaign engagement event
"""
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum

from pydantic import BaseModel, Field

from src.utils.pyobject_id import PyObjectId


class Channel(str, Enum):
    """Campaign delivery channels"""
    EMAIL = "email"
    TEXT = "text"
    TEXT_MORNING = "text_morning"  # Deprecated: use TEXT
    TEXT_EVENING = "text_evening"  # Deprecated: use TEXT
    MAILER = "mailer"
    LETTER = "letter"


class UnifiedEngagement(str, Enum):
    """Unified engagement status across all channels"""
    NO_ENGAGEMENT = "no_engagement"
    RECEIVED = "received"
    ENGAGED = "engaged"


class Address(BaseModel):
    """Normalized address"""
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    county: Optional[str] = None
    raw: Optional[str] = None


class Linkage(BaseModel):
    """County data linkage information"""
    parcel_id: Optional[str] = None
    county_key: Optional[str] = None
    method: Optional[str] = None
    confidence: float = 0.0
    matched_at: Optional[datetime] = None


class Demographics(BaseModel):
    """Demographics from county data (denormalized)"""
    customer_name: Optional[str] = None
    estimated_income: Optional[float] = None
    income_level: Optional[int] = None
    household_size: Optional[float] = None
    annual_kwh_cost: Optional[float] = None
    annual_gas_cost: Optional[float] = None
    total_energy_burden: Optional[float] = None
    energy_burden_kwh: Optional[float] = None
    energy_burden_gas: Optional[float] = None
    age_bracket: Optional[str] = None
    home_owner: Optional[bool] = None
    dwelling_type: Optional[str] = None
    marital_status: Optional[str] = None
    presence_of_children: Optional[bool] = None
    number_of_adults: Optional[float] = None

    @classmethod
    def from_county_record(cls, record: dict) -> "Demographics":
        """Create from county demographic record"""
        import math

        def safe_float(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            if val == -1:
                return None
            return float(val)

        def safe_int(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            if val == -1:
                return None
            return int(val)

        def safe_str(val):
            if val is None or val == 'NA' or val == -1:
                return None
            if isinstance(val, float) and math.isnan(val):
                return None
            return str(val)

        # Parse age bracket from "age in two-year increments - 1st individual"
        age_val = record.get('age in two-year increments - 1st individual')
        age_bracket = None
        if age_val and not (isinstance(age_val, float) and math.isnan(age_val)):
            age_int = int(age_val)
            age_bracket = f"{age_int}-{age_int + 1}"

        # Parse home_owner from "home owner / renter"
        home_owner_val = record.get('home owner / renter')
        home_owner = None
        if home_owner_val == 'O':
            home_owner = True
        elif home_owner_val == 'R':
            home_owner = False

        # Parse presence of children
        children_val = record.get('presence of children')
        presence_of_children = None
        if children_val == 'Y':
            presence_of_children = True
        elif children_val == 'N':
            presence_of_children = False

        return cls(
            customer_name=safe_str(record.get('customer_name')),
            estimated_income=safe_float(record.get('estimated_income')),
            income_level=safe_int(record.get('income_level') or record.get('income level')),
            household_size=safe_float(record.get('md_householdsize')),
            annual_kwh_cost=safe_float(record.get('annual_kwh_cost')),
            annual_gas_cost=safe_float(record.get('annual_gas_cost')),
            total_energy_burden=safe_float(record.get('total_energy_burden')),
            energy_burden_kwh=safe_float(record.get('energy_burden_kwh')),
            energy_burden_gas=safe_float(record.get('energy_burden_gas')),
            age_bracket=age_bracket,
            home_owner=home_owner,
            dwelling_type=safe_str(record.get('dwelling type')),
            marital_status=safe_str(record.get('marital status')),
            presence_of_children=presence_of_children,
            number_of_adults=safe_float(record.get('number of adults'))
        )


class Residence(BaseModel):
    """Residence info from county data (denormalized)"""
    living_area_sqft: Optional[float] = None
    story_height: Optional[float] = None
    year_built: Optional[int] = None
    house_age: Optional[int] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    half_baths: Optional[float] = None
    rooms_total: Optional[float] = None
    heat_type: Optional[str] = None
    air_conditioning: Optional[str] = None
    construction_quality: Optional[str] = None
    garage_size: Optional[float] = None
    parcel_owner: Optional[str] = None
    census_tract: Optional[str] = None
    rcn: Optional[float] = None

    @classmethod
    def from_county_record(cls, record: dict) -> "Residence":
        """Create from county residential record"""
        import math

        def safe_float(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            if val == -1:
                return None
            return float(val)

        def safe_int(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            if val == -1:
                return None
            return int(val)

        def safe_str(val):
            if val is None or val == 'NA' or val == -1:
                return None
            if isinstance(val, float) and math.isnan(val):
                return None
            return str(val)

        # Compute house_age from 'age' field (which is year_built in some counties)
        # or from current year - age if age represents actual age
        age_val = record.get('age')
        year_built = None
        house_age = None
        if age_val and age_val != -1:
            if age_val > 1800:  # Looks like year_built
                year_built = int(age_val)
                house_age = datetime.now().year - year_built
            else:  # Looks like age in years
                house_age = int(age_val)
                year_built = datetime.now().year - house_age

        return cls(
            living_area_sqft=safe_float(record.get('living_area_total')),
            story_height=safe_float(record.get('story_height')),
            year_built=year_built,
            house_age=house_age,
            bedrooms=safe_float(record.get('bedrooms')),
            bathrooms=safe_float(record.get('bathrooms')),
            half_baths=safe_float(record.get('half_baths')),
            rooms_total=safe_float(record.get('rooms')),
            heat_type=safe_str(record.get('heat_type')),
            air_conditioning=safe_str(record.get('air_conditioning')),
            construction_quality=safe_str(record.get('construction_quality')),
            garage_size=safe_float(record.get('garage_size')),
            parcel_owner=safe_str(record.get('parcel_owner')),
            census_tract=safe_str(record.get('census_tract')),
            rcn=safe_float(record.get('rcn'))
        )


class EnergySnapshot(BaseModel):
    """Energy data snapshot from campaign CSV"""
    kwh_annual: Optional[float] = None
    annual_cost: Optional[float] = None
    annual_savings: Optional[float] = None
    monthly_cost: Optional[float] = None
    monthly_saving: Optional[float] = None
    daily_cost: Optional[float] = None
    snapshot_date: Optional[datetime] = None


class ChannelEngagement(BaseModel):
    """Engagement stats for a single channel"""
    exposures: int = 0
    received: int = 0
    engaged: int = 0


class EngagementSummary(BaseModel):
    """Pre-computed engagement aggregations"""
    total_campaigns: int = 0
    total_exposures: int = 0
    by_channel: Dict[str, ChannelEngagement] = Field(default_factory=lambda: {
        "email": ChannelEngagement(),
        "text": ChannelEngagement(),
        "mailer": ChannelEngagement(),
        "letter": ChannelEngagement()
    })
    unified_status: str = UnifiedEngagement.NO_ENGAGEMENT.value
    ever_received: bool = False
    ever_engaged: bool = False
    first_campaign_date: Optional[datetime] = None
    last_campaign_date: Optional[datetime] = None
    overall_receive_rate: float = 0.0
    overall_engage_rate: float = 0.0


class DataQuality(BaseModel):
    """Data quality flags for filtering"""
    has_demographics: bool = False
    has_residence: bool = False
    has_energy_snapshot: bool = False
    has_engagement: bool = False
    completeness_score: float = 0.0
    analysis_ready: bool = False


class Participant(BaseModel):
    """
    Master participant entity - one document per unique person.

    Identified by canonical participant_id (email if available, else phone).
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")
    participant_id: str = Field(..., description="Canonical ID: email or phone")

    # Contact methods
    email: Optional[str] = None
    phone: Optional[str] = None

    # Address
    address: Address = Field(default_factory=Address)

    # County linkage
    linkage: Linkage = Field(default_factory=Linkage)

    # Denormalized county data
    demographics: Demographics = Field(default_factory=Demographics)
    residence: Residence = Field(default_factory=Residence)

    # Energy snapshot from CSV
    energy_snapshot: EnergySnapshot = Field(default_factory=EnergySnapshot)

    # Pre-computed engagement
    engagement_summary: EngagementSummary = Field(default_factory=EngagementSummary)

    # Quality flags
    data_quality: DataQuality = Field(default_factory=DataQuality)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    source_campaigns: List[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}


class CampaignStatistics(BaseModel):
    """Campaign aggregate statistics"""
    total_sent: int = 0
    opened: int = 0
    clicked: int = 0
    bounced: int = 0
    unsubscribed: int = 0
    complained: int = 0
    received: int = 0
    engaged: int = 0
    receive_rate: float = 0.0
    engage_rate: float = 0.0


class Campaign(BaseModel):
    """Campaign metadata"""
    id: Optional[PyObjectId] = Field(None, alias="_id")
    campaign_id: str = Field(..., description="UUID from source system")

    # Identity
    name: str
    agency: Optional[str] = None
    channel: str = Channel.EMAIL.value

    # Content
    subject: Optional[str] = None
    message_type: Optional[str] = None

    # Timing
    sent_at: Optional[datetime] = None

    # Source
    source_system: str = "emailoctopus"
    source_file: Optional[str] = None

    # Statistics
    statistics: CampaignStatistics = Field(default_factory=CampaignStatistics)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    synced_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}


class ContactSnapshot(BaseModel):
    """Contact info at time of campaign send"""
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None


class EnergyAtSend(BaseModel):
    """Energy data at time of campaign send"""
    kwh: Optional[float] = None
    annual_cost: Optional[float] = None
    annual_savings: Optional[float] = None
    monthly_cost: Optional[float] = None
    daily_cost: Optional[float] = None


class CampaignExposure(BaseModel):
    """
    Individual participant × campaign engagement event.

    One document per (participant_id, campaign_id) pair.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")

    # Foreign keys
    participant_id: str
    campaign_id: str

    # Denormalized for convenience
    agency: Optional[str] = None
    channel: str = Channel.EMAIL.value
    sent_at: Optional[datetime] = None

    # Email engagement
    email_opened: bool = False
    email_opened_at: Optional[datetime] = None
    email_clicked: bool = False
    email_clicked_at: Optional[datetime] = None
    email_bounced: bool = False
    email_complained: bool = False
    email_unsubscribed: bool = False

    # Text engagement (nullable for email)
    text_delivered: Optional[bool] = None
    text_read: Optional[bool] = None
    text_replied: Optional[bool] = None

    # Postal engagement (nullable for digital)
    postal_delivered: Optional[bool] = None
    postal_response: Optional[bool] = None

    # Unified status
    unified_status: str = UnifiedEngagement.NO_ENGAGEMENT.value

    # Snapshots
    contact_snapshot: ContactSnapshot = Field(default_factory=ContactSnapshot)
    energy_at_send: EnergyAtSend = Field(default_factory=EnergyAtSend)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}

    def compute_unified_status(self) -> str:
        """Compute unified engagement status based on channel-specific engagement"""
        if self.channel == Channel.EMAIL.value:
            if self.email_clicked:
                return UnifiedEngagement.ENGAGED.value
            elif self.email_opened:
                return UnifiedEngagement.RECEIVED.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        elif self.channel in (Channel.TEXT.value, Channel.TEXT_MORNING.value, Channel.TEXT_EVENING.value):
            if self.text_replied:
                return UnifiedEngagement.ENGAGED.value
            elif self.text_read or self.text_delivered:
                return UnifiedEngagement.RECEIVED.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        elif self.channel in (Channel.MAILER.value, Channel.LETTER.value):
            if self.postal_response:
                return UnifiedEngagement.ENGAGED.value
            elif self.postal_delivered:
                return UnifiedEngagement.RECEIVED.value
            else:
                return UnifiedEngagement.NO_ENGAGEMENT.value

        return UnifiedEngagement.NO_ENGAGEMENT.value
