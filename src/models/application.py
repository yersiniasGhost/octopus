"""
Pydantic models for program applications (conversions).

Applications represent the ultimate outcome in the campaign funnel -
people who completed the sign-up form. This data is used to:
1. Validate clustering effectiveness (which clusters convert?)
2. Attribution analysis (which campaigns drove conversions?)
3. Compare self-reported vs modeled demographics
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from src.utils.pyobject_id import PyObjectId


class ApplicantIdentity(BaseModel):
    """Applicant identity information for matching"""
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None  # Normalized to digits only
    phone_raw: Optional[str] = None  # Original format


class ApplicantAddress(BaseModel):
    """Applicant address for matching and analysis"""
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    county: Optional[str] = None  # Critical for campaign matching


class SelfReportedDemographics(BaseModel):
    """Self-reported demographics from application form.

    These can be compared against county-modeled demographics to:
    - Validate our demographic models
    - Identify discrepancies between modeled vs actual
    """
    age: Optional[int] = None  # Normalized to integer
    age_raw: Optional[str] = None  # Original value
    household_income: Optional[float] = None  # Normalized to annual
    household_income_raw: Optional[str] = None  # Original value
    household_members: Optional[int] = None
    housing_status: Optional[str] = None  # "rent" | "own" | null
    needs_housing_help: Optional[bool] = None
    has_dependent_children: Optional[bool] = None
    pre_1978_home: Optional[bool] = None


class UTMAttribution(BaseModel):
    """UTM parameters parsed from source URL"""
    utm_source: Optional[str] = None  # e.g., "Majority"
    utm_medium: Optional[str] = None  # e.g., "Letter", "SMS", "Text"
    utm_campaign: Optional[str] = None  # e.g., "Letter", "Fight+Costs"
    utm_id: Optional[str] = None
    utm_content: Optional[str] = None  # e.g., "COAD+Wednesday", "MVCAP+Friday"
    source_url: Optional[str] = None


class CampaignLink(BaseModel):
    """Link to a likely influential campaign"""
    campaign_id: str
    confidence: float = 0.0  # 0.0-1.0
    method: str  # "utm_direct" | "date_window" | "county_exposure"


class Attribution(BaseModel):
    """Full attribution data for an application"""
    utm: Optional[UTMAttribution] = None
    likely_campaigns: List[CampaignLink] = Field(default_factory=list)


class ParticipantMatch(BaseModel):
    """Link to existing participant record"""
    participant_id: Optional[str] = None
    match_method: Optional[str] = None  # "email" | "phone" | "address"
    match_confidence: float = 0.0
    matched_at: Optional[datetime] = None


class ClusterAssignment(BaseModel):
    """Cluster assignments for outcome analysis"""
    phase1_cluster: Optional[int] = None  # Demographics clustering
    phase2_cluster: Optional[int] = None  # Campaign exposure clustering
    phase3_cluster: Optional[int] = None  # Probabilistic clustering
    assigned_at: Optional[datetime] = None


class Application(BaseModel):
    """Program application (conversion event).

    Represents a completed sign-up form submission. This is the ultimate
    outcome in the campaign funnel and is used to evaluate campaign and
    clustering effectiveness.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    application_id: str  # Entry ID from source system

    # Identity for matching
    applicant: ApplicantIdentity = Field(default_factory=ApplicantIdentity)
    address: ApplicantAddress = Field(default_factory=ApplicantAddress)

    # Self-reported demographics
    self_reported: SelfReportedDemographics = Field(default_factory=SelfReportedDemographics)

    # Campaign attribution
    attribution: Attribution = Field(default_factory=Attribution)

    # Linkage to participants
    participant_match: ParticipantMatch = Field(default_factory=ParticipantMatch)

    # Clustering outcome analysis
    cluster_assignment: ClusterAssignment = Field(default_factory=ClusterAssignment)

    # Metadata
    entry_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    import_batch: Optional[str] = None

    class Config:
        populate_by_name = True
        json_encoders = {PyObjectId: str}
