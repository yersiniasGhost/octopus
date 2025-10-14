"""
Pydantic models for EmailOctopus Participant (Contact) data
"""
from typing import Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field

from src.utils.pyobject_id import PyObjectId


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
    """Participant engagement tracking"""
    opened: bool = False
    clicked: bool = False
    bounced: bool = False
    complained: bool = False
    unsubscribed: bool = False


class Participant(BaseModel):
    """
    EmailOctopus Participant (Contact) model for MongoDB storage

    Represents a participant in a campaign with their contact info and engagement.
    Maps to 'participants' collection.
    """
    id: Optional[PyObjectId] = Field(None, alias="_id")
    contact_id: str = Field(..., description="EmailOctopus contact UUID")
    campaign_id: str = Field(..., description="Campaign this participant belongs to")
    email_address: str = Field(..., description="Participant email address")
    status: Optional[str] = Field(default="SUBSCRIBED", description="Contact status")
    fields: ParticipantFields = Field(default_factory=ParticipantFields, description="Custom contact fields")
    engagement: ParticipantEngagement = Field(default_factory=ParticipantEngagement, description="Engagement tracking")
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
        engagement = ParticipantEngagement()
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

        return cls(
            contact_id=contact_data.get('id', ''),
            campaign_id=campaign_id,
            email_address=contact_data.get('email_address', ''),
            status=contact_data.get('status') or 'SUBSCRIBED',  # Handle None values
            fields=fields,
            engagement=engagement,
            synced_at=datetime.now()
        )

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
