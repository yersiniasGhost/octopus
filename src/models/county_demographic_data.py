from src.utils.pyobject_id import PyObjectId
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


''' Format for ______CountyDemographic collections.'''


class DemographicData(BaseModel):
    """
    County demographic data model.

    Core fields are from utility data, enrichment fields are from BOLT analysis files.
    """
    id: PyObjectId = Field(None, alias="_id")

    # Core identification fields
    parcel_id: str
    address: str
    customer_name: str
    service_city: str
    parcel_zip: int

    # Contact fields
    email: float = -1
    mobile: int = Field(-1, description="Mobile number, -1 if not available")

    # Energy burden fields (from utility data)
    energy_burden_gas: float = -1
    energy_burden_kwh: float
    annual_kwh_cost: float
    annual_gas_cost: float = -1
    total_energy_burden: float = -1  # (annual_kwh_cost+annual_gas_cost) / estimated_income

    # Income fields
    estimated_income: float = -1  # middle of the given range
    income_level: float = -1      # 0-9 income rating

    # Original household size (from utility data)
    md_householdsize: float

    # ========== BOLT Enrichment Fields ==========
    # Demographics - from BOLT analysis files (Melissa Data vendor)

    # Age and household composition
    owner_age: Optional[int] = Field(None, description="Age in two-year increments (e.g., 60)")
    number_of_adults: Optional[int] = Field(None, description="Number of adults in household")
    household_size: Optional[int] = Field(None, description="Total household size from MD enrichment")
    presence_of_children: Optional[str] = Field(None, description="'Yes' or 'No'")
    children_age_range: Optional[str] = Field(None, description="Age range of children if present")
    presence_of_senior: Optional[str] = Field(None, description="'Yes' or 'No' for senior presence")

    # Personal demographics
    gender: Optional[str] = Field(None, description="'Male' or 'Female'")
    marital_status: Optional[str] = Field(None, description="'Married' or 'Single'")
    date_of_birth: Optional[str] = Field(None, description="Date of birth if available")
    ethnic_group: Optional[str] = Field(None, description="Ethnic group classification")
    education: Optional[str] = Field(None, description="Education level")
    occupation: Optional[str] = Field(None, description="Occupation category")

    # Housing characteristics
    dwelling_type: Optional[str] = Field(None, description="'S' single family, etc.")
    home_owner: Optional[str] = Field(None, description="'Owner' or 'Renter'")
    length_of_residence: Optional[int] = Field(None, description="Years at current residence")
    estimated_home_value: Optional[float] = Field(None, description="Estimated home value from MD")

    # Enrichment metadata
    enriched_at: Optional[datetime] = Field(None, description="When BOLT enrichment was applied")
    enriched_from: Optional[str] = Field(None, description="Source BOLT analysis filename")



'''
Example enriched document from county demographic collection:

{
    '_id': ObjectId('...'),
    # Core identification
    'parcel_id': '21425802C',
    'address': '1050 STONEWOOD CT',
    'customer_name': 'SEAN D CONWAY',
    'service_city': 'WESTLAKE',
    'parcel_zip': '44145',

    # Contact
    'email': -1,
    'mobile': 2162253312,

    # Energy burden (from utility data)
    'energy_burden_gas': 0.0,
    'energy_burden_kwh': 0.064,
    'annual_kwh_cost': 2887.28,
    'annual_gas_cost': 0.0,
    'total_energy_burden': 0.064,

    # Income
    'estimated_income': 45000.0,
    'income_level': 5.0,
    'md_householdsize': 2.0,

    # ====== BOLT Enrichment Fields (from Melissa Data) ======
    # Age and household composition
    'owner_age': 60,
    'number_of_adults': 2,
    'household_size': 2,
    'presence_of_children': 'No',
    'children_age_range': None,
    'presence_of_senior': 'Yes',

    # Personal demographics
    'gender': 'Male',
    'marital_status': 'Single',
    'date_of_birth': None,
    'ethnic_group': 'Western European',
    'education': 'Completed College',
    'occupation': 'Professional',

    # Housing characteristics
    'dwelling_type': 'S',  # Single family
    'home_owner': 'Owner',
    'length_of_residence': 6,
    'estimated_home_value': 250000.0,

    # Enrichment metadata
    'enriched_at': datetime(2024, 12, 17, ...),
    'enriched_from': 'fayette_EmpowerSaves_BOLT Analysis_20250310.xlsx'
}

Field availability varies by county - not all BOLT files contain all fields.
Universal fields (available in all BOLT files):
  - owner_age, number_of_adults, marital_status, estimated_home_value
'''