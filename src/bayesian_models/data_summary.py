"""
Data Summary Utilities for Bayesian Models

Provides functions to capture and display data ingestion statistics
for transparency and model provenance tracking.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import json

from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)


@dataclass
class CountySummary:
    """Summary statistics for a single county."""
    name: str
    participant_count: int
    click_count: int = 0
    click_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CampaignSummary:
    """Summary statistics for a single campaign."""
    campaign_id: str
    name: Optional[str] = None
    exposure_count: int = 0
    click_count: int = 0
    click_rate: float = 0.0
    message_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissingDataSummary:
    """Summary of missing or excluded data."""
    # Participant-level
    participants_no_county: int = 0
    participants_no_demographics: int = 0
    participants_no_income: int = 0
    participants_no_energy_burden: int = 0

    # Exposure-level
    exposures_no_campaign_match: int = 0
    exposures_no_participant_match: int = 0

    # Campaign-level
    campaigns_no_message_types: int = 0

    # County filtering
    counties_excluded_low_count: int = 0
    excluded_county_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def has_significant_missing(self, threshold: float = 0.1) -> bool:
        """Check if missing data exceeds threshold proportion."""
        # This would need total counts to calculate proportion
        return False


@dataclass
class DataIngestionSummary:
    """Complete summary of data ingested for model training."""

    # Core statistics
    total_participants: int = 0
    total_observations: int = 0  # participant x campaign exposures
    total_campaigns: int = 0
    total_counties: int = 0

    # Outcome statistics
    click_count: int = 0
    overall_click_rate: float = 0.0

    # Detailed breakdowns
    counties: List[CountySummary] = field(default_factory=list)
    campaigns: List[CampaignSummary] = field(default_factory=list)

    # Missing data
    missing_data: MissingDataSummary = field(default_factory=MissingDataSummary)

    # Data quality
    min_campaigns_per_county: int = 0
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None

    # Metadata
    model_id: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_sources: List[str] = field(default_factory=list)

    # Feature-specific summaries (for models with treatments)
    treatment_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'total_participants': self.total_participants,
            'total_observations': self.total_observations,
            'total_campaigns': self.total_campaigns,
            'total_counties': self.total_counties,
            'click_count': self.click_count,
            'overall_click_rate': self.overall_click_rate,
            'counties': [c.to_dict() for c in self.counties],
            'campaigns': [c.to_dict() for c in self.campaigns],
            'missing_data': self.missing_data.to_dict(),
            'min_campaigns_per_county': self.min_campaigns_per_county,
            'date_range_start': self.date_range_start,
            'date_range_end': self.date_range_end,
            'model_id': self.model_id,
            'generated_at': self.generated_at,
            'data_sources': self.data_sources,
            'treatment_summary': self.treatment_summary
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataIngestionSummary':
        """Create from dictionary."""
        summary = cls()

        summary.total_participants = data.get('total_participants', 0)
        summary.total_observations = data.get('total_observations', 0)
        summary.total_campaigns = data.get('total_campaigns', 0)
        summary.total_counties = data.get('total_counties', 0)
        summary.click_count = data.get('click_count', 0)
        summary.overall_click_rate = data.get('overall_click_rate', 0.0)

        # Counties
        counties_data = data.get('counties', [])
        summary.counties = [
            CountySummary(
                name=c.get('name', ''),
                participant_count=c.get('participant_count', 0),
                click_count=c.get('click_count', 0),
                click_rate=c.get('click_rate', 0.0)
            )
            for c in counties_data
        ]

        # Campaigns
        campaigns_data = data.get('campaigns', [])
        summary.campaigns = [
            CampaignSummary(
                campaign_id=c.get('campaign_id', ''),
                name=c.get('name'),
                exposure_count=c.get('exposure_count', 0),
                click_count=c.get('click_count', 0),
                click_rate=c.get('click_rate', 0.0),
                message_types=c.get('message_types', [])
            )
            for c in campaigns_data
        ]

        # Missing data
        missing = data.get('missing_data', {})
        summary.missing_data = MissingDataSummary(
            participants_no_county=missing.get('participants_no_county', 0),
            participants_no_demographics=missing.get('participants_no_demographics', 0),
            participants_no_income=missing.get('participants_no_income', 0),
            participants_no_energy_burden=missing.get('participants_no_energy_burden', 0),
            exposures_no_campaign_match=missing.get('exposures_no_campaign_match', 0),
            exposures_no_participant_match=missing.get('exposures_no_participant_match', 0),
            campaigns_no_message_types=missing.get('campaigns_no_message_types', 0),
            counties_excluded_low_count=missing.get('counties_excluded_low_count', 0),
            excluded_county_names=missing.get('excluded_county_names', [])
        )

        summary.min_campaigns_per_county = data.get('min_campaigns_per_county', 0)
        summary.date_range_start = data.get('date_range_start')
        summary.date_range_end = data.get('date_range_end')
        summary.model_id = data.get('model_id', '')
        summary.generated_at = data.get('generated_at', datetime.now().isoformat())
        summary.data_sources = data.get('data_sources', [])
        summary.treatment_summary = data.get('treatment_summary', {})

        return summary

    def save(self, output_dir: Path) -> Path:
        """Save summary to JSON file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / 'data_summary.json'

        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.info(f"Data summary saved to {output_path}")
        return output_path

    @classmethod
    def load(cls, output_dir: Path) -> Optional['DataIngestionSummary']:
        """Load summary from JSON file."""
        summary_path = output_dir / 'data_summary.json'

        if not summary_path.exists():
            logger.warning(f"Data summary not found at {summary_path}")
            return None

        try:
            with open(summary_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading data summary: {e}")
            return None


def load_data_summary_for_model(model_id: str) -> Optional[DataIngestionSummary]:
    """
    Load data ingestion summary for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        DataIngestionSummary if found, None otherwise
    """
    from src.bayesian_models.base_model import MODELS_OUTPUT_DIR

    model_output_dir = MODELS_OUTPUT_DIR / model_id / 'reports'
    return DataIngestionSummary.load(model_output_dir)
