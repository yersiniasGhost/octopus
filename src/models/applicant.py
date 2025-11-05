"""
Pydantic model for Applicant data from CSV sign-up forms

This model stores applicant information and their matching results to
county demographic and residential databases.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from src.utils.pyobject_id import PyObjectId


class MatchInfo(BaseModel):
    """Information about how the applicant was matched to database records"""
    match_quality: str = Field(..., description="Match quality: exact, good, fuzzy, demographic, no_match")
    match_method: Optional[str] = Field(None, description="Method used: email, name, phone, address_normalized, state_route, fuzzy_address")
    match_details: Optional[str] = Field(None, description="Additional details about the match")
    matched_at: datetime = Field(default_factory=datetime.now, description="When the match was performed")


class ResidenceReference(BaseModel):
    """Reference to matched residence record"""
    county: str = Field(..., description="County name (e.g., 'Harrison', 'Marion')")
    parcel_id: str = Field(..., description="Parcel ID from residential data")
    address: Optional[str] = Field(None, description="Matched address from database")
    parcel_city: Optional[str] = Field(None, description="City from parcel data")
    parcel_zip: Optional[int] = Field(None, description="ZIP code from parcel data")

    @classmethod
    def from_record(cls, county: str, record: dict) -> "ResidenceReference":
        """Create from database record, handling NaN values"""
        import math
        parcel_city = record.get('parcel_city')
        # Handle NaN values
        if parcel_city is not None and (isinstance(parcel_city, float) and math.isnan(parcel_city)):
            parcel_city = None

        return cls(
            county=county,
            parcel_id=record.get('parcel_id', ''),
            address=record.get('address'),
            parcel_city=str(parcel_city) if parcel_city else None,
            parcel_zip=record.get('parcel_zip')
        )


class DemographicReference(BaseModel):
    """Reference to matched demographic record"""
    county: str = Field(..., description="County name (e.g., 'Harrison', 'Marion')")
    parcel_id: str = Field(..., description="Parcel ID linking to residential data")
    customer_name: Optional[str] = Field(None, description="Customer name from demographic data")
    email: Optional[str] = Field(None, description="Email from demographic data")
    mobile: Optional[str] = Field(None, description="Mobile phone from demographic data")
    annual_kwh_cost: Optional[float] = Field(None, description="Annual electricity cost")
    total_energy_burden: Optional[float] = Field(None, description="Total energy burden ratio")

    @classmethod
    def from_record(cls, county: str, record: dict) -> "DemographicReference":
        """Create from database record, handling NaN values"""
        import math

        # Handle email field which might be -1.0 or NaN
        email = record.get('email')
        if email is not None and isinstance(email, (int, float)) and (email == -1 or math.isnan(email)):
            email = None

        # Handle mobile field
        mobile = record.get('mobile')
        if mobile is not None:
            if isinstance(mobile, (int, float)) and (mobile == -1 or math.isnan(mobile)):
                mobile = None
            else:
                mobile = str(mobile)

        return cls(
            county=county,
            parcel_id=record.get('parcel_id', ''),
            customer_name=record.get('customer_name'),
            email=str(email) if email and not isinstance(email, (int, float)) else None,
            mobile=mobile,
            annual_kwh_cost=record.get('annual_kwh_cost'),
            total_energy_burden=record.get('total_energy_burden')
        )


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
    match_info: MatchInfo = Field(..., description="Information about database matching")
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
        match_info = MatchInfo(
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
