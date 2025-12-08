"""
Pydantic models for Multi-Channel Campaign data
Supports: Email, Text/SMS, Mailer, and Letter campaigns
"""
from typing import Optional, List, Dict, Union, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from src.utils.pyobject_id import PyObjectId


class CampaignStatCount(BaseModel):
    """Statistics count with unique and total"""
    unique: int = 0
    total: int = 0


# Type-specific statistics classes
class EmailStatistics(BaseModel):
    """Campaign statistics for Email campaigns"""
    sent: CampaignStatCount = Field(default_factory=CampaignStatCount)
    opened: CampaignStatCount = Field(default_factory=CampaignStatCount)
    clicked: CampaignStatCount = Field(default_factory=CampaignStatCount)
    bounced: CampaignStatCount = Field(default_factory=CampaignStatCount)
    complained: CampaignStatCount = Field(default_factory=CampaignStatCount)
    unsubscribed: CampaignStatCount = Field(default_factory=CampaignStatCount)


class TextStatistics(BaseModel):
    """Campaign statistics for Text/SMS campaigns"""
    sent: CampaignStatCount = Field(default_factory=CampaignStatCount, description="Messages sent")
    delivered: CampaignStatCount = Field(default_factory=CampaignStatCount, description="Messages delivered")
    clicked: CampaignStatCount = Field(default_factory=CampaignStatCount, description="Links clicked")
    failed: CampaignStatCount = Field(default_factory=CampaignStatCount, description="Delivery failures")
    opt_outs: CampaignStatCount = Field(default_factory=CampaignStatCount, description="STOP/Unsubscribe requests")


class MailerStatistics(BaseModel):
    """Campaign statistics for Physical Mailer campaigns"""
    printed: int = Field(default=0, description="Pieces printed")
    mailed: int = Field(default=0, description="Pieces mailed")
    delivered: int = Field(default=0, description="Confirmed deliveries (if tracked)")
    returned: int = Field(default=0, description="Return to sender")
    estimated_delivery_rate: Optional[float] = Field(None, description="Estimated delivery percentage")


class LetterStatistics(BaseModel):
    """Campaign statistics for Letter campaigns"""
    printed: int = Field(default=0, description="Letters printed")
    mailed: int = Field(default=0, description="Letters mailed")
    delivered: int = Field(default=0, description="Confirmed deliveries (if tracked)")
    returned: int = Field(default=0, description="Return to sender")
    certified_mail: int = Field(default=0, description="Certified mail count")


# Legacy alias for backward compatibility
CampaignStatistics = EmailStatistics


class Campaign(BaseModel):
    """
    Multi-Channel Campaign model for MongoDB storage

    Supports Email, Text/SMS, Mailer, and Letter campaigns.
    Maps to 'campaigns' collection.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")
    campaign_id: str = Field(..., description="Campaign UUID (EmailOctopus or generated)")
    name: str = Field(..., description="Campaign name")
    campaign_type: Literal["email", "text", "mailer", "letter"] = Field(
        default="email",
        description="Campaign channel type"
    )
    status: str = Field(..., description="Campaign status (DRAFT, SENT, etc.)")
    created_at: Optional[datetime] = Field(None, description="Campaign creation timestamp")
    sent_at: Optional[datetime] = Field(None, description="Campaign sent timestamp")

    # Email-specific fields
    subject: Optional[str] = Field(None, description="Email subject line (email campaigns)")
    from_name: Optional[str] = Field(None, description="Sender name (email campaigns)")
    from_email: Optional[str] = Field(None, description="Sender email address", alias="from_email_address")
    to_lists: Optional[List[str]] = Field(None, description="List IDs (email campaigns)")

    # Text/SMS-specific fields
    message_body: Optional[str] = Field(None, description="SMS message text (text campaigns)")
    sender_phone: Optional[str] = Field(None, description="Sender phone number (text campaigns)")
    sms_provider: Optional[str] = Field(None, description="SMS provider (Twilio, MessageBird, etc.)")

    # Mailer/Letter-specific fields
    template_id: Optional[str] = Field(None, description="Template ID (mailer/letter campaigns)")
    print_vendor: Optional[str] = Field(None, description="Print vendor (Lob, PostGrid, etc.)")
    postage_class: Optional[str] = Field(None, description="Postage class (First Class, Standard)")
    envelope_type: Optional[str] = Field(None, description="Envelope type (#10, 6x9, etc.)")
    color_printing: Optional[bool] = Field(None, description="Color vs B&W printing")
    double_sided: Optional[bool] = Field(None, description="Double-sided printing")

    # Common metadata
    target_audience: Optional[str] = Field(None, description="Target audience/organization (OHCAC, IMPACT, etc.)")
    cost_per_send: Optional[float] = Field(None, description="Cost per contact")
    total_cost: Optional[float] = Field(None, description="Total campaign cost")

    # Message classification (multi-tag)
    message_types: Optional[List[str]] = Field(
        default=None,
        description="Message classification tags: urgency_deadline, savings_financial, relief_reassurance, informational, personalized_qualified, motivational_struggle"
    )

    # Statistics (type-aware)
    statistics: Union[EmailStatistics, TextStatistics, MailerStatistics, LetterStatistics] = Field(
        default_factory=EmailStatistics,
        description="Campaign statistics (type varies by campaign_type)"
    )

    synced_at: datetime = Field(default_factory=datetime.now, description="Last sync timestamp")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            PyObjectId: str,
            datetime: lambda v: v.isoformat() if v else None
        }

    @field_validator('statistics')
    @classmethod
    def validate_statistics_type(cls, v, info):
        """Ensure statistics type matches campaign_type"""
        campaign_type = info.data.get('campaign_type', 'email')

        expected_types = {
            'email': EmailStatistics,
            'text': TextStatistics,
            'mailer': MailerStatistics,
            'letter': LetterStatistics
        }

        expected_type = expected_types.get(campaign_type, EmailStatistics)

        # If statistics is a dict, convert to appropriate type
        if isinstance(v, dict):
            return expected_type(**v)

        # Validate type matches
        if not isinstance(v, expected_type):
            # Allow conversion for backward compatibility
            if isinstance(v, EmailStatistics) and campaign_type == 'email':
                return v
            # Try to convert
            try:
                return expected_type(**v.dict() if hasattr(v, 'dict') else v.model_dump())
            except:
                pass

        return v

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
        stats = EmailStatistics()
        if statistics:
            for key in ['sent', 'opened', 'clicked', 'bounced', 'complained', 'unsubscribed']:
                if key in statistics:
                    stat_data = statistics[key]
                    if isinstance(stat_data, dict):
                        setattr(stats, key, CampaignStatCount(**stat_data))

        return cls(
            campaign_id=campaign_data.get('id'),
            campaign_type='email',  # EmailOctopus campaigns are always email
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
