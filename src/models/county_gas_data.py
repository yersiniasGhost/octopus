from config.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField

''' Format for ______CountyGas collections.'''


class GasData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    time_series_gas: dict






