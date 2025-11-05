"""
Pydantic models for Campaign Participant (Contact) data

Supports both Email and Text/SMS campaign participants with engagement tracking.
"""
from typing import Optional, Dict, List, Union
from datetime import datetime
from pydantic import BaseModel, Field

from src.utils.pyobject_id import PyObjectId
from src.models.common import ResidenceReference, DemographicReference


class ParticipantFields(BaseModel):
    """Custom fields for participant contact data"""
    FirstName: Optional[str] = None
    LastName: Optional[str] = None
    City: Optional[str] = None
    ZIP: Optional[str] = None
    kWh: Optional[str] = None
    Cell: Optional[str] = None
    Address: Optional[str] = None
    annualcost: Optional[str] = None
    AnnualSavings: Optional[str] = None
    MonthlyCost: Optional[str] = None
    MonthlySaving: Optional[str] = None
    DailyCost: Optional[str] = None

    class Config:
        extra = 'allow'  # Allow additional fields not defined in model


class ParticipantEngagement(BaseModel):
    """Email campaign engagement tracking"""
    campaign_id: str = Field(..., description="Campaign ID this engagement belongs to")
    opened: bool = False
    clicked: bool = False
    bounced: bool = False
    complained: bool = False
    unsubscribed: bool = False
    engaged_at: datetime = Field(default_factory=datetime.now, description="When engagement was recorded")


class TextEngagement(BaseModel):
    """Text/SMS campaign engagement tracking"""
    campaign_id: str = Field(..., description="Campaign ID this engagement belongs to")

    # Message counts
    messages_sent: int = Field(default=0, description="Number of messages sent to this contact")
    messages_delivered: int = Field(default=0, description="Number of messages delivered")
    messages_read: int = Field(default=0, description="Number of messages read")
    messages_failed: int = Field(default=0, description="Number of messages that failed")

    # Engagement flags
    replied: bool = Field(default=False, description="Whether contact replied to messages")
    opted_out: bool = Field(default=False, description="Whether contact opted out (STOP)")

    # Timestamps
    first_message_sent: Optional[datetime] = Field(None, description="When first message was sent")
    last_message_sent: Optional[datetime] = Field(None, description="When last message was sent")
    first_read_time: Optional[datetime] = Field(None, description="When first message was read")
    last_read_time: Optional[datetime] = Field(None, description="When last message was read")

    # Metadata
    engaged_at: datetime = Field(default_factory=datetime.now, description="When engagement was recorded")


class Participant(BaseModel):
    """
    Campaign Participant (Contact) model for MongoDB storage

    Represents a participant across multiple campaigns (email and text/SMS).
    Can track engagement across multiple overlapping campaigns.
    Maps to 'participants' collection.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")

    # Primary identifier (email or phone)
    contact_id: str = Field(..., description="Unique contact identifier (email or phone number)")

    # Contact information
    email_address: Optional[str] = Field(None, description="Participant email address (for email campaigns)")
    phone_number: Optional[str] = Field(None, description="Participant phone number (for text campaigns)")

    # Contact status
    status: Optional[str] = Field(default="SUBSCRIBED", description="Contact status")

    # Custom fields (primarily for email campaigns)
    fields: ParticipantFields = Field(default_factory=ParticipantFields, description="Custom contact fields")

    # Multi-campaign engagement tracking
    engagements: List[Union[ParticipantEngagement, TextEngagement]] = Field(
        default_factory=list,
        description="List of engagements across campaigns (supports multiple overlapping campaigns)"
    )

    # References to demographic and residence data
    residence_ref: Optional[ResidenceReference] = Field(None, description="Reference to matched residence record")
    demographic_ref: Optional[DemographicReference] = Field(None, description="Reference to matched demographic record")

    # Metadata
    synced_at: datetime = Field(default_factory=datetime.now, description="Last sync timestamp")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            PyObjectId: str,
            datetime: lambda v: v.isoformat() if v else None
        }

    @classmethod
    def from_emailoctopus(cls, contact_data: Dict, campaign_id: str,
                         report_type: Optional[str] = None) -> "Participant":
        """
        Create Participant instance from EmailOctopus API response

        Args:
            contact_data: Contact data from EmailOctopus API
            campaign_id: Campaign ID this participant belongs to
            report_type: Optional report type (opened, clicked, etc.) for engagement tracking

        Returns:
            Participant instance ready for MongoDB insertion
        """
        # Handle wrapped contact data from reports
        if 'contact' in contact_data:
            contact_data = contact_data['contact']

        # Parse custom fields
        fields_data = contact_data.get('fields', {})
        fields = ParticipantFields(**fields_data)

        # Determine engagement based on report type
        engagement = ParticipantEngagement(campaign_id=campaign_id)
        if report_type:
            if report_type == 'opened':
                engagement.opened = True
            elif report_type == 'clicked':
                engagement.clicked = True
                engagement.opened = True  # Implies opened
            elif report_type == 'bounced':
                engagement.bounced = True
            elif report_type == 'complained':
                engagement.complained = True
            elif report_type == 'unsubscribed':
                engagement.unsubscribed = True

        email = contact_data.get('email_address', '')

        return cls(
            contact_id=email,  # Use email as contact_id for email campaigns
            email_address=email,
            phone_number=None,
            status=contact_data.get('status') or 'SUBSCRIBED',
            fields=fields,
            engagements=[engagement],  # Now a list
            synced_at=datetime.now()
        )

    @classmethod
    def from_text_conversation(cls, phone: str, campaign_id: str,
                               conversation_data: List[Dict],
                               residence_ref: Optional[ResidenceReference] = None,
                               demographic_ref: Optional[DemographicReference] = None) -> "Participant":
        """
        Create Participant instance from text conversation data

        Args:
            phone: Phone number (contact identifier)
            campaign_id: Campaign ID for this text campaign
            conversation_data: List of message records for this phone number
            residence_ref: Optional residence reference from matching
            demographic_ref: Optional demographic reference from matching

        Returns:
            Participant instance ready for MongoDB insertion
        """
        # Analyze conversation messages
        messages_sent = 0
        messages_delivered = 0
        messages_read = 0
        messages_failed = 0
        replied = False
        opted_out = False

        first_sent = None
        last_sent = None
        first_read = None
        last_read = None

        for msg in conversation_data:
            msg_type = msg.get('type', '')
            status = msg.get('status', '')
            msg_time_str = msg.get('Msg Time')
            read_time_str = msg.get('Read Time')
            tags = msg.get('Tags', '')

            # Parse timestamps
            msg_time = cls._parse_timestamp(msg_time_str) if msg_time_str else None
            read_time = cls._parse_timestamp(read_time_str) if read_time_str else None

            # Count outbound messages
            if msg_type == 'out':
                messages_sent += 1
                if status == 'ok':
                    messages_delivered += 1
                else:
                    messages_failed += 1

                if msg_time:
                    if not first_sent or msg_time < first_sent:
                        first_sent = msg_time
                    if not last_sent or msg_time > last_sent:
                        last_sent = msg_time

                if read_time:
                    messages_read += 1
                    if not first_read or read_time < first_read:
                        first_read = read_time
                    if not last_read or read_time > last_read:
                        last_read = read_time

            # Check for replies (inbound messages)
            elif msg_type == 'in':
                replied = True

            # Check for opt-out
            if tags and 'dnd' in tags.lower():
                opted_out = True

        # Create text engagement
        engagement = TextEngagement(
            campaign_id=campaign_id,
            messages_sent=messages_sent,
            messages_delivered=messages_delivered,
            messages_read=messages_read,
            messages_failed=messages_failed,
            replied=replied,
            opted_out=opted_out,
            first_message_sent=first_sent,
            last_message_sent=last_sent,
            first_read_time=first_read,
            last_read_time=last_read
        )

        return cls(
            contact_id=str(phone),  # Use phone as contact_id for text campaigns
            email_address=None,
            phone_number=str(phone),
            status="ACTIVE" if not opted_out else "OPTED_OUT",
            fields=ParticipantFields(),
            engagements=[engagement],
            residence_ref=residence_ref,
            demographic_ref=demographic_ref,
            synced_at=datetime.now()
        )

    @staticmethod
    def _parse_timestamp(ts_str: str) -> Optional[datetime]:
        """Parse timestamp from conversation data"""
        if not ts_str:
            return None
        try:
            # Format: "2025-05-02 17:15:43 GMT-0000"
            # Remove timezone suffix
            clean_str = ts_str.replace(' GMT-0000', '').strip()
            return datetime.strptime(clean_str, '%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError):
            return None

    def to_mongo_dict(self) -> Dict:
        """Convert to dictionary for MongoDB insertion"""
        # Use dict() for Pydantic v1/v2 compatibility
        data = self.dict(by_alias=True, exclude={'id'}) if hasattr(self, 'dict') else self.model_dump(by_alias=True, exclude={'id'})
        return data

    def to_csv_row(self, campaign_name: str = "", campaign_sent_at: str = "") -> Dict:
        """
        Convert to flat dictionary for CSV export

        Args:
            campaign_name: Campaign name to include in row
            campaign_sent_at: Campaign sent date to include in row

        Returns:
            Flattened dictionary suitable for CSV writing
        """
        return {
            'campaign_name': campaign_name,
            'campaign_sent_at': campaign_sent_at,
            'email': self.email_address,
            'first_name': self.fields.FirstName or '',
            'last_name': self.fields.LastName or '',
            'city': self.fields.City or '',
            'zip': self.fields.ZIP or '',
            'kwh': self.fields.kWh or '',
            'cell': self.fields.Cell or '',
            'address': self.fields.Address or '',
            'annual_cost': self.fields.annualcost or '',
            'annual_savings': self.fields.AnnualSavings or '',
            'monthly_cost': self.fields.MonthlyCost or '',
            'monthly_saving': self.fields.MonthlySaving or '',
            'daily_cost': self.fields.DailyCost or '',
            'opened': 'Yes' if self.engagement.opened else 'No',
            'clicked': 'Yes' if self.engagement.clicked else 'No',
            'bounced': 'Yes' if self.engagement.bounced else 'No',
            'complained': 'Yes' if self.engagement.complained else 'No',
            'unsubscribed': 'Yes' if self.engagement.unsubscribed else 'No',
            'status': self.status
        }
