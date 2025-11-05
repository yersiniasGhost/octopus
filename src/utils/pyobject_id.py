"""
Custom PyObjectId class for Pydantic v2 compatibility with MongoDB ObjectId
"""
from bson.objectid import ObjectId
import json
from typing import Any
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """Custom ObjectId that works with Pydantic v2 models"""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler):
        """Pydantic v2 schema for validation"""
        return core_schema.union_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls.validate_str),
            ])
        ], serialization=core_schema.plain_serializer_function_ser_schema(str))

    @classmethod
    def validate_str(cls, v: str) -> ObjectId:
        """Validate string representation of ObjectId"""
        try:
            return ObjectId(v)
        except Exception as e:
            raise ValueError(f'Invalid ObjectId: {e}')

    # Legacy Pydantic v1 support (for backward compatibility)
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            return cls.validate_str(v)
        raise TypeError('ObjectId or string required')

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
