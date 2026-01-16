"""
Pydantic models for comparable residence results

Defines the data structures for comparable search results, including
similarity scoring and feature matching details.
"""
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class ComparableScore(BaseModel):
    """Detailed similarity scoring breakdown"""
    overall_score: float = Field(..., description="Overall similarity score (0-1, higher = more similar)")

    # Feature-level scores (each 0-1)
    sqft_score: float = Field(0.0, description="Living area similarity score")
    story_score: float = Field(0.0, description="Story height similarity score")
    age_score: float = Field(0.0, description="Building age similarity score")
    bedrooms_score: float = Field(0.0, description="Bedroom count similarity score")
    bathrooms_score: float = Field(0.0, description="Bathroom count similarity score")
    household_score: float = Field(0.0, description="Household size similarity score")
    income_score: float = Field(0.0, description="Income level similarity score")

    # Distances (absolute differences)
    sqft_diff: float = Field(0.0, description="Absolute sqft difference")
    story_diff: float = Field(0.0, description="Absolute story height difference")
    age_diff: float = Field(0.0, description="Absolute age difference in years")

    class Config:
        json_schema_extra = {
            "example": {
                "overall_score": 0.85,
                "sqft_score": 0.92,
                "story_score": 1.0,
                "age_score": 0.75,
                "sqft_diff": 200,
                "story_diff": 0,
                "age_diff": 5
            }
        }


class ComparableResult(BaseModel):
    """A single comparable residence result"""
    parcel_id: str = Field(..., description="Parcel ID of comparable property")
    address: Optional[str] = Field(None, description="Property address")
    city: Optional[str] = Field(None, description="City")
    zip_code: Optional[int] = Field(None, description="ZIP code")

    # Property characteristics
    living_area_sqft: Optional[float] = Field(None, description="Living area in sqft")
    story_height: Optional[float] = Field(None, description="Number of stories")
    age: Optional[int] = Field(None, description="Building age in years")
    bedrooms: Optional[float] = Field(None, description="Number of bedrooms")
    bathrooms: Optional[float] = Field(None, description="Number of bathrooms")
    construction_quality: Optional[str] = Field(None, description="Construction quality rating")
    heat_type: Optional[str] = Field(None, description="Heating type")
    air_conditioning: Optional[str] = Field(None, description="AC type")

    # Demographic info (if available)
    household_size: Optional[int] = Field(None, description="Number of occupants")
    estimated_income: Optional[float] = Field(None, description="Estimated household income")

    # Energy metrics (if available)
    annual_kwh_cost: Optional[float] = Field(None, description="Annual electricity cost")
    annual_gas_cost: Optional[float] = Field(None, description="Annual gas cost")
    total_energy_burden: Optional[float] = Field(None, description="Energy burden ratio")

    # Thermal load metrics (if available)
    kwh_hl_slope: Optional[float] = Field(None, description="Heating load slope (kWh)")
    gas_hl_slope: Optional[float] = Field(None, description="Heating load slope (gas)")

    # Scoring
    score: ComparableScore = Field(..., description="Similarity scoring details")

    @classmethod
    def from_records(cls, residence: Dict, demographic: Optional[Dict] = None,
                     thermal: Optional[Dict] = None, score: ComparableScore = None) -> "ComparableResult":
        """Create ComparableResult from database records"""
        result = cls(
            parcel_id=residence.get('parcel_id', ''),
            address=residence.get('address'),
            city=residence.get('parcel_city'),
            zip_code=residence.get('parcel_zip'),
            living_area_sqft=residence.get('living_area_total'),
            story_height=residence.get('story_height'),
            age=residence.get('age'),
            bedrooms=residence.get('bedrooms'),
            bathrooms=residence.get('bathrooms'),
            construction_quality=residence.get('construction_quality'),
            heat_type=residence.get('heat_type'),
            air_conditioning=residence.get('air_conditioning'),
            score=score or ComparableScore(overall_score=0.0)
        )

        if demographic:
            result.household_size = demographic.get('household_size') or demographic.get('md_householdsize')
            result.estimated_income = demographic.get('estimated_income')
            result.annual_kwh_cost = demographic.get('annual_kwh_cost')
            result.annual_gas_cost = demographic.get('annual_gas_cost')
            result.total_energy_burden = demographic.get('total_energy_burden')

        if thermal:
            result.kwh_hl_slope = thermal.get('kwh_hl_slope')
            result.gas_hl_slope = thermal.get('gas_hl_slope')

        return result


class ComparableSearchResult(BaseModel):
    """Complete comparable search result set"""
    target_parcel_id: str = Field(..., description="Parcel ID of the target property")
    target_address: Optional[str] = Field(None, description="Target property address")
    county: str = Field(..., description="County name")

    # Target property characteristics (for reference)
    target_sqft: Optional[float] = Field(None, description="Target living area")
    target_stories: Optional[float] = Field(None, description="Target story height")
    target_age: Optional[int] = Field(None, description="Target building age")
    target_household_size: Optional[int] = Field(None, description="Target household size")

    # Results
    comparables: List[ComparableResult] = Field(default_factory=list, description="List of comparable properties")
    total_candidates: int = Field(0, description="Total candidates before filtering")
    search_filters_applied: Dict = Field(default_factory=dict, description="Filters that were applied")

    # Statistics
    avg_sqft_diff: Optional[float] = Field(None, description="Average sqft difference from target")
    avg_age_diff: Optional[float] = Field(None, description="Average age difference from target")
    avg_energy_cost: Optional[float] = Field(None, description="Average energy cost of comparables")
