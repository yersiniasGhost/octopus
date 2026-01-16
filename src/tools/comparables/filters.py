"""
Filter configuration for comparable residence searches

All filters are optional - when not specified, that dimension is not constrained.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ComparableFilters(BaseModel):
    """
    Configuration for comparable residence search filters.

    All fields are optional. When a field is None, that filter is not applied.
    Tolerance values define the acceptable range (e.g., sqft_tolerance=500 means +/- 500 sqft).

    Example:
        filters = ComparableFilters(
            same_zip=True,
            sqft_tolerance=500,
            story_height_tolerance=0.5,
            age_tolerance=10
        )
    """

    # Geographic filters
    same_zip: Optional[bool] = Field(None, description="Require same ZIP code as target")
    same_city: Optional[bool] = Field(None, description="Require same city as target")
    zip_codes: Optional[List[int]] = Field(None, description="Specific ZIP codes to include")
    census_tract: Optional[str] = Field(None, description="Specific census tract to filter by")

    # Physical property filters (tolerances define +/- range)
    sqft_tolerance: Optional[float] = Field(None, description="Max sqft difference (+/-) from target")
    sqft_min: Optional[float] = Field(None, description="Minimum living area sqft")
    sqft_max: Optional[float] = Field(None, description="Maximum living area sqft")

    story_height_tolerance: Optional[float] = Field(None, description="Max story height difference (+/-)")
    story_height_exact: Optional[bool] = Field(None, description="Require exact story height match")

    age_tolerance: Optional[int] = Field(None, description="Max building age difference (+/-) in years")
    age_min: Optional[int] = Field(None, description="Minimum building age")
    age_max: Optional[int] = Field(None, description="Maximum building age")
    year_built_min: Optional[int] = Field(None, description="Minimum year built")
    year_built_max: Optional[int] = Field(None, description="Maximum year built")

    # Room configuration
    bedrooms_tolerance: Optional[int] = Field(None, description="Max bedroom count difference (+/-)")
    bedrooms_exact: Optional[bool] = Field(None, description="Require exact bedroom count match")
    bedrooms_min: Optional[int] = Field(None, description="Minimum bedrooms")
    bedrooms_max: Optional[int] = Field(None, description="Maximum bedrooms")

    bathrooms_tolerance: Optional[float] = Field(None, description="Max bathroom count difference (+/-)")
    bathrooms_min: Optional[float] = Field(None, description="Minimum bathrooms")
    bathrooms_max: Optional[float] = Field(None, description="Maximum bathrooms")

    # Construction characteristics
    construction_quality: Optional[List[str]] = Field(None, description="Allowed construction quality values")
    heat_type: Optional[List[str]] = Field(None, description="Allowed heating types")
    air_conditioning: Optional[List[str]] = Field(None, description="Allowed AC types")

    # Demographic filters
    household_size_tolerance: Optional[int] = Field(None, description="Max household size difference (+/-)")
    household_size_exact: Optional[bool] = Field(None, description="Require exact household size match")
    household_size_min: Optional[int] = Field(None, description="Minimum household size")
    household_size_max: Optional[int] = Field(None, description="Maximum household size")

    income_tolerance: Optional[float] = Field(None, description="Max income difference (+/-)")
    income_tolerance_pct: Optional[float] = Field(None, description="Max income difference as percentage (0-1)")
    income_min: Optional[float] = Field(None, description="Minimum estimated income")
    income_max: Optional[float] = Field(None, description="Maximum estimated income")

    # Energy filters
    energy_burden_max: Optional[float] = Field(None, description="Maximum energy burden ratio")
    annual_kwh_cost_max: Optional[float] = Field(None, description="Maximum annual kWh cost")

    # Exclusions
    exclude_parcel_ids: Optional[List[str]] = Field(None, description="Parcel IDs to exclude from results")

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ScoringWeights(BaseModel):
    """
    Weights for computing similarity scores between properties.

    Each weight determines the importance of that feature in the overall
    similarity calculation. Weights are normalized internally, so they
    can be relative values.

    Default weights prioritize physical property characteristics over
    demographic factors, as physical characteristics are more stable
    and directly comparable.
    """
    sqft_weight: float = Field(default=3.0, description="Weight for living area similarity")
    story_weight: float = Field(default=2.0, description="Weight for story height similarity")
    age_weight: float = Field(default=2.0, description="Weight for building age similarity")
    bedrooms_weight: float = Field(default=1.5, description="Weight for bedroom count similarity")
    bathrooms_weight: float = Field(default=1.0, description="Weight for bathroom count similarity")
    household_weight: float = Field(default=1.5, description="Weight for household size similarity")
    income_weight: float = Field(default=1.0, description="Weight for income similarity")

    # Reference ranges for normalization (used to convert absolute differences to 0-1 scores)
    sqft_reference_range: float = Field(default=2000.0, description="Reference sqft range for normalization")
    age_reference_range: float = Field(default=50.0, description="Reference age range for normalization")
    income_reference_range: float = Field(default=50000.0, description="Reference income range for normalization")

    def get_total_weight(self) -> float:
        """Get sum of all weights for normalization"""
        return (self.sqft_weight + self.story_weight + self.age_weight +
                self.bedrooms_weight + self.bathrooms_weight +
                self.household_weight + self.income_weight)
