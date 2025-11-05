from typing import Dict, List
from datetime import datetime
from src.utils.pyobject_id import PyObjectId
from bson import ObjectId
from pydantic import BaseModel, Field as PydanticField


class MeterData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    # residential_data_id: PyObjectId
    meter_id: str
    meter_data: Dict[str, float]

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }