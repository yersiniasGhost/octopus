"""
Common Pydantic models shared across multiple entity types

These reference classes are used by Applicant, Participant, and other models
to link to county demographic and residential data.
"""
from typing import Optional
from pydantic import BaseModel, Field


class ResidenceReference(BaseModel):
    """Reference to matched residence record in county residential data"""
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
    """Reference to matched demographic record in county demographic data"""
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


class MatchInfo(BaseModel):
    """Information about how an entity was matched to database records"""
    match_quality: str = Field(..., description="Match quality: exact, good, fuzzy, demographic, no_match")
    match_method: Optional[str] = Field(None, description="Method used: email, name, phone, address_normalized, state_route, fuzzy_address")
    match_details: Optional[str] = Field(None, description="Additional details about the match")
