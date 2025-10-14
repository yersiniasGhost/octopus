from config.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField


''' Format for ______CountyElectrical collections.'''

class ElectricalData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    time_series_elec: dict
    monthly_averages: dict
    monthly_minimums: dict
    monthly_maximums: dict







