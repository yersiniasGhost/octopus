"""
Pydantic models for EmailOctopus Campaign data
"""
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field

from src.utils.pyobject_id import PyObjectId


class CampaignStatCount(BaseModel):
    """Statistics count with unique and total"""
    unique: int = 0
    total: int = 0


class CampaignStatistics(BaseModel):
    """Campaign statistics from EmailOctopus reports"""
    sent: CampaignStatCount = Field(default_factory=CampaignStatCount)
    opened: CampaignStatCount = Field(default_factory=CampaignStatCount)
    clicked: CampaignStatCount = Field(default_factory=CampaignStatCount)
    bounced: CampaignStatCount = Field(default_factory=CampaignStatCount)
    complained: CampaignStatCount = Field(default_factory=CampaignStatCount)
    unsubscribed: CampaignStatCount = Field(default_factory=CampaignStatCount)


class Campaign(BaseModel):
    """
    EmailOctopus Campaign model for MongoDB storage

    Represents a complete campaign with metadata and statistics.
    Maps to 'campaigns' collection.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")
    campaign_id: str = Field(..., description="EmailOctopus campaign UUID")
    name: str = Field(..., description="Campaign name")
    subject: str = Field(default="", description="Email subject line")
    from_name: str = Field(default="", description="Sender name")
    from_email: str = Field(default="", description="Sender email address", alias="from_email_address")
    created_at: Optional[datetime] = Field(None, description="Campaign creation timestamp")
    sent_at: Optional[datetime] = Field(None, description="Campaign sent timestamp")
    status: str = Field(..., description="Campaign status (DRAFT, SENT, etc.)")
    to_lists: List[str] = Field(default_factory=list, description="List IDs campaign was sent to")
    statistics: CampaignStatistics = Field(default_factory=CampaignStatistics, description="Campaign statistics")
    synced_at: datetime = Field(default_factory=datetime.now, description="Last sync timestamp")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            PyObjectId: str,
            datetime: lambda v: v.isoformat() if v else None
        }

    @classmethod
    def from_emailoctopus(cls, campaign_data: Dict, statistics: Optional[Dict] = None) -> "Campaign":
        """
        Create Campaign instance from EmailOctopus API response

        Args:
            campaign_data: Campaign data from EmailOctopus API
            statistics: Optional statistics data from reports/summary endpoint

        Returns:
            Campaign instance ready for MongoDB insertion
        """
        # Parse statistics if provided
        stats = CampaignStatistics()
        if statistics:
            for key in ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']:
                if key in statistics:
                    stat_data = statistics[key]
                    if isinstance(stat_data, dict):
                        setattr(stats, key, CampaignStatCount(**stat_data))

        return cls(
            campaign_id=campaign_data.get('id'),
            name=campaign_data.get('name', ''),
            subject=campaign_data.get('subject', ''),
            from_name=campaign_data.get('from', {}).get('name', ''),
            from_email_address=campaign_data.get('from', {}).get('email_address', ''),
            created_at=cls._parse_datetime(campaign_data.get('created_at')),
            sent_at=cls._parse_datetime(campaign_data.get('sent_at')),
            status=campaign_data.get('status', 'UNKNOWN'),
            to_lists=campaign_data.get('to', []),
            statistics=stats,
            synced_at=datetime.now()
        )

    @staticmethod
    def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from EmailOctopus API"""
        if not dt_str:
            return None
        try:
            # EmailOctopus uses ISO 8601 format
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    def to_mongo_dict(self) -> Dict:
        """Convert to dictionary for MongoDB insertion"""
        # Use dict() for Pydantic v1/v2 compatibility
        data = self.dict(by_alias=True, exclude={'id'}) if hasattr(self, 'dict') else self.model_dump(by_alias=True, exclude={'id'})
        return data
