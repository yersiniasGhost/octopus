"""
Pydantic model for Applicant data from CSV sign-up forms

This model stores applicant information and their matching results to
county demographic and residential databases.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from src.utils.pyobject_id import PyObjectId
from src.models.common import ResidenceReference, DemographicReference, MatchInfo


class ApplicantMatchInfo(MatchInfo):
    """Applicant-specific match information with timestamp"""
    matched_at: datetime = Field(default_factory=datetime.now, description="When the match was performed")


class Applicant(BaseModel):
    """
    Applicant model for MongoDB storage

    Represents a person who signed up via the web form, with their contact
    information and linkage to county demographic/residential databases.
    Maps to 'applicants' collection.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")

    # Original form data
    entry_id: str = Field(..., description="Unique entry ID from form submission")
    first_name: str = Field(..., description="First name from form")
    last_name: str = Field(..., description="Last name from form")
    email: EmailStr = Field(..., description="Email address from form")
    phone: Optional[str] = Field(None, description="Phone number from form")

    # Address information from form
    address: str = Field(..., description="Street address from form")
    city: str = Field(..., description="City from form")
    zip_code: str = Field(..., description="ZIP code from form")
    county: Optional[str] = Field(None, description="County determined from ZIP code")

    # Matching information
    match_info: ApplicantMatchInfo = Field(..., description="Information about database matching")
    residence_ref: Optional[ResidenceReference] = Field(None, description="Reference to matched residence record")
    demographic_ref: Optional[DemographicReference] = Field(None, description="Reference to matched demographic record")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="When record was created")
    updated_at: datetime = Field(default_factory=datetime.now, description="When record was last updated")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            PyObjectId: str,
            datetime: lambda v: v.isoformat() if v else None
        }

    def to_mongo_dict(self) -> dict:
        """Convert to dictionary for MongoDB insertion"""
        # Use dict() for Pydantic v1/v2 compatibility
        data = self.dict(by_alias=True, exclude={'id'}) if hasattr(self, 'dict') else self.model_dump(by_alias=True, exclude={'id'})
        return data

    @classmethod
    def from_csv_and_match(cls, csv_row: dict, match_result: dict) -> "Applicant":
        """
        Create Applicant instance from CSV row and matching result

        Args:
            csv_row: Dictionary from CSV DictReader
            match_result: Matching result with residence/demographic data

        Returns:
            Applicant instance ready for MongoDB insertion
        """
        # Extract basic info from CSV
        entry_id = csv_row.get('Entry Id', '')
        first_name = csv_row.get('Name (First)', '')
        last_name = csv_row.get('Name (Last)', '')
        email = csv_row.get('Email', '')
        phone = csv_row.get('Phone', '')

        # Address fields might be in different columns
        address = (csv_row.get('Address (Street Address)', '') or
                  csv_row.get('City (Street Address)', '') or
                  csv_row.get('State (Street Address)', '') or
                  csv_row.get('Zip (Street Address)', ''))

        city = (csv_row.get('Address (City)', '') or
               csv_row.get('City (City)', '') or
               csv_row.get('State (City)', '') or
               csv_row.get('Zip (City)', ''))

        zip_code = (csv_row.get('Address (ZIP / Postal Code)', '') or
                   csv_row.get('City (ZIP / Postal Code)', '') or
                   csv_row.get('State (ZIP / Postal Code)', '') or
                   csv_row.get('Zip (ZIP / Postal Code)', ''))

        county = match_result.get('county')

        # Build match info
        match_info = ApplicantMatchInfo(
            match_quality=match_result.get('match_quality', 'no_match'),
            match_method=match_result.get('match_method'),
            match_details=match_result.get('match_details', '')
        )

        # Build residence reference if matched
        residence_ref = None
        if match_result.get('residence_record'):
            residence_ref = ResidenceReference.from_record(county, match_result['residence_record'])

        # Build demographic reference if matched
        demographic_ref = None
        if match_result.get('demographic_record'):
            demographic_ref = DemographicReference.from_record(county, match_result['demographic_record'])

        return cls(
            entry_id=entry_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address=address,
            city=city,
            zip_code=zip_code,
            county=county,
            match_info=match_info,
            residence_ref=residence_ref,
            demographic_ref=demographic_ref
        )
