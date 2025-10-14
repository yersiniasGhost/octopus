from config.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField
from typing import List

''' Format for ______CountyThermalLoads collections.'''

class ThermalLoadData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    gas_hl_cl_loads: list = PydanticField(default_factory=list)
    kwh_hl_cl_loads:list
    gas_hl_slope:float = -1
    gas_hl_intercept:float =-1
    gas_hl_r2: float =-1
    kwh_hl_slope:float
    kwh_hl_intercept:float
    kwh_hl_r2:float
    gas_cl_slope:float =-1
    gas_cl_intercept:float =-1
    gas_cl_r2:float =-1
    kwh_cl_slope:float
    kwh_cl_intercept:float
    kwh_cl_r2:float
