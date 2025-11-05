from src.utils.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField
from pydantic import BaseModel, Field


''' Format for ______CountyDemographic collections.'''

class DemographicData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    address: str
    energy_burden_gas: float = -1
    energy_burden_kwh: float
    annual_kwh_cost: float
    annual_gas_cost: float = -1
    total_energy_burden: float = -1     # decimal value, (annual_kwh_cost+annual_gas_cost)/ estimated_income
    customer_name: str
    estimated_income: float = -1    # middle of the given range
    income_level: float = -1         # 0-9 income rating
    md_householdsize: float
    email: float = -1
    mobile: int = Field(-1, description="Mobile number, -1 if not available")
    parcel_zip: int
    service_city: str








'''______CountyDemographic reqs:
Random document from OttawaResidential collection:
{'_id': ObjectId('66676252403ac9048ba814bc'),
 'address': '1050 STONEWOOD CT', str
 *'age in two-year increments - 1st individual': 60.0, float
 'annual_gas_cost': 0.0, float
 'annual_kwh_cost': 2887.28, float
 'customer_name': 'SEAN D CONWAY', str
 *'dwelling type': 'S', str
 'energy_burden_gas': 0.0, float
 'energy_burden_kwh': 0.0641617777777777, float
 'estimated_income': 45000.0, float
 *'gender - input individual': 'M', str
 *'home length of residence': 6.0, float
 *'home owner / renter': 'O', float
 'income level': 5.0, float
 *'marital status': 'S', str
 'md_householdsize': 2.0, float
 'mobile': '2162253312.0', float
 *'number of adults': 2.0, float
 'parcel_id': '21425802C', str
 'parcel_zip': '44145', int
 *'presence of children': 'N', str
 'service_city': 'WESTLAKE', str
 'total_energy_burden': 0.0641617777777777 int}

'''