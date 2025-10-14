"""
Custom PyObjectId class for Pydantic compatibility with MongoDB ObjectId
"""
from bson.objectid import ObjectId
import json


class PyObjectId(ObjectId):
    """Custom ObjectId that works with Pydantic models"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, ObjectId):
            raise TypeError('ObjectId required')
        return v

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

    @classmethod
    def __get_pydantic_json_schema__(cls, **kwargs):
        return {"type": "string"}


class CustomJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles ObjectId and PyObjectId"""

    def default(self, obj):
        if isinstance(obj, (ObjectId, PyObjectId)):
            return str(obj)
        return super().default(obj)
