from typing import Dict, List
from src.utils.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField


class Parcel(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: int
    street_number: str
    street_name: str
    street_suffix: str
    city: str
    zip: str
    gas: bool

