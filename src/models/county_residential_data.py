from typing import Optional

from config.pyobject_id import PyObjectId
from pydantic import BaseModel, Field as PydanticField


''' Format for ______CountyResidential collections.'''

class ResidentialData(BaseModel):
    id: PyObjectId = PydanticField(None, alias="_id")
    parcel_id: str
    parcel_zip: int = -1
    parcel_owner: str ='NA'
    parcel_city: str ='NA'
    address: str ='NA'
    story_height: float
    construction_quality: str ='NA'
    age: Optional[int] = -1
    heat_type: str ='NA'
    air_conditioning: str ='NA'
    rooms: float = -1
    bedrooms: float = -1
    bathrooms: float = -1
    half_baths: float = -1
    garage_size: float = -1
    living_area_total: float
    rcn: float = -1
    census_tract: Optional[str]

