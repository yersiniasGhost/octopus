"""
CSV export writer for campaign data
"""
import csv
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from src.models.participant import Participant

logger = logging.getLogger(__name__)


class CSVWriter:
    """
    Writes campaign data to CSV files

    Creates one CSV file per campaign in data/exports directory.
    """

    def __init__(self, export_dir: str = "data/exports"):
        """
        Initialize CSV writer

        Args:
            export_dir: Directory path for CSV exports
        """
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_campaign(self, campaign_id: str, campaign_name: str,
                       campaign_sent_at: str, participants: List[Participant]) -> str:
        """
        Export campaign participants to CSV file

        Args:
            campaign_id: EmailOctopus campaign UUID
            campaign_name: Campaign name for CSV content
            campaign_sent_at: Campaign sent date for CSV content
            participants: List of Participant model instances

        Returns:
            Path to created CSV file
        """
        # Sanitize campaign name for filename
        safe_name = self._sanitize_filename(campaign_name)
        filename = f"campaign_{campaign_id}_{safe_name}.csv"
        filepath = self.export_dir / filename

        logger.info(f"Exporting {len(participants)} participants to {filepath}")

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                # Define CSV headers
                fieldnames = [
                    'campaign_name', 'campaign_sent_at',
                    'email', 'first_name', 'last_name', 'city', 'zip',
                    'kwh', 'cell', 'address',
                    'annual_cost', 'annual_savings', 'monthly_cost',
                    'monthly_saving', 'daily_cost',
                    'opened', 'clicked', 'bounced', 'complained', 'unsubscribed',
                    'status'
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                # Write participant rows
                for participant in participants:
                    row = participant.to_csv_row(
                        campaign_name=campaign_name,
                        campaign_sent_at=campaign_sent_at
                    )
                    writer.writerow(row)

            logger.info(f"Successfully exported to {filepath}")
            return str(filepath)

        except IOError as e:
            logger.error(f"Error writing CSV file {filepath}: {e}")
            raise

    def export_campaign_from_dicts(self, campaign: Dict, participants: List[Dict]) -> str:
        """
        Export campaign participants from dictionary data (for MongoDB documents)

        Args:
            campaign: Campaign document from MongoDB
            participants: List of participant documents from MongoDB

        Returns:
            Path to created CSV file
        """
        campaign_id = campaign.get('campaign_id', 'unknown')
        campaign_name = campaign.get('name', 'Untitled Campaign')
        sent_at = campaign.get('sent_at')

        # Format sent_at date
        if sent_at:
            if isinstance(sent_at, datetime):
                campaign_sent_at = sent_at.strftime('%Y-%m-%d')
            else:
                campaign_sent_at = str(sent_at)
        else:
            campaign_sent_at = ''

        # Convert participant dicts to CSV rows directly (avoid Pydantic model issues)
        from src.models.participant import ParticipantFields, ParticipantEngagement

        # Sanitize campaign name for filename
        safe_name = self._sanitize_filename(campaign_name)
        filename = f"campaign_{campaign_id}_{safe_name}.csv"
        filepath = self.export_dir / filename

        logger.info(f"Exporting {len(participants)} participants to {filepath}")

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'campaign_name', 'campaign_sent_at',
                    'email', 'first_name', 'last_name', 'city', 'zip',
                    'kwh', 'cell', 'address',
                    'annual_cost', 'annual_savings', 'monthly_cost',
                    'monthly_saving', 'daily_cost',
                    'opened', 'clicked', 'bounced', 'complained', 'unsubscribed',
                    'status'
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                # Write participant rows directly from dict data
                for p in participants:
                    fields = p.get('fields', {})
                    engagement = p.get('engagement', {})

                    row = {
                        'campaign_name': campaign_name,
                        'campaign_sent_at': campaign_sent_at,
                        'email': p.get('email_address', ''),
                        'first_name': fields.get('FirstName') or '',
                        'last_name': fields.get('LastName') or '',
                        'city': fields.get('City') or '',
                        'zip': fields.get('ZIP') or '',
                        'kwh': fields.get('kWh') or '',
                        'cell': fields.get('Cell') or '',
                        'address': fields.get('Address') or '',
                        'annual_cost': fields.get('annualcost') or '',
                        'annual_savings': fields.get('AnnualSavings') or '',
                        'monthly_cost': fields.get('MonthlyCost') or '',
                        'monthly_saving': fields.get('MonthlySaving') or '',
                        'daily_cost': fields.get('DailyCost') or '',
                        'opened': 'Yes' if engagement.get('opened') else 'No',
                        'clicked': 'Yes' if engagement.get('clicked') else 'No',
                        'bounced': 'Yes' if engagement.get('bounced') else 'No',
                        'complained': 'Yes' if engagement.get('complained') else 'No',
                        'unsubscribed': 'Yes' if engagement.get('unsubscribed') else 'No',
                        'status': p.get('status', 'SUBSCRIBED')
                    }
                    writer.writerow(row)

            logger.info(f"Successfully exported to {filepath}")
            return str(filepath)

        except IOError as e:
            logger.error(f"Error writing CSV file {filepath}: {e}")
            raise

    def _sanitize_filename(self, name: str, max_length: int = 50) -> str:
        """
        Sanitize string for use in filename

        Args:
            name: Original string
            max_length: Maximum length for sanitized name

        Returns:
            Sanitized filename-safe string
        """
        # Remove or replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')

        # Remove leading/trailing spaces and dots
        name = name.strip('. ')

        # Truncate to max length
        if len(name) > max_length:
            name = name[:max_length]

        # Replace spaces with underscores
        name = name.replace(' ', '_')

        return name or 'untitled'

    def get_export_path(self, campaign_id: str, campaign_name: str) -> Path:
        """
        Get the expected export path for a campaign without creating the file

        Args:
            campaign_id: EmailOctopus campaign UUID
            campaign_name: Campaign name

        Returns:
            Path object for expected CSV file
        """
        safe_name = self._sanitize_filename(campaign_name)
        filename = f"campaign_{campaign_id}_{safe_name}.csv"
        return self.export_dir / filename

    def list_exports(self) -> List[str]:
        """
        List all CSV export files

        Returns:
            List of CSV file paths
        """
        csv_files = list(self.export_dir.glob('campaign_*.csv'))
        return [str(f) for f in sorted(csv_files)]
