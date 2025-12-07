"""
Click Model Data Loader
========================

This module defines the data format for the click-through model and provides
functions to load real data from the MongoDB databases.

Data Flow:
    empower_development.participants (campaign engagement)
        ↓ match by email
    empower_development.{County}Demographic (income, energy_burden)
        ↓
    ClickModelData (model-ready format)

Database Schema Reference:
    participants: campaign_id, contact_id, email_address, engagement.clicked
    {County}Demographic: email, estimated_income, total_energy_burden, customer_name
"""

import os
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_mongo_client() -> Tuple[MongoClient, str]:
    """
    Get MongoDB client connected to empower_development database.

    Returns
    -------
    Tuple[MongoClient, str]
        MongoDB client and database name

    Environment Variables
    ---------------------
    MONGODB_HOST_RM : str
        MongoDB host (default: localhost)
    MONGODB_PORT_RM : int
        MongoDB port (default: 27017)
    MONGODB_DATABASE_RM : str
        Database name (default: empower_development)
    """
    load_dotenv()

    host = os.getenv('MONGODB_HOST_RM', 'localhost')
    port = int(os.getenv('MONGODB_PORT_RM', '27017'))
    db_name = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    client = MongoClient(host, port)
    return client, db_name


# =============================================================================
# DEMOGRAPHIC DATA LOADER
# =============================================================================

def load_demographic_index(db, verbose: bool = True) -> Dict[str, dict]:
    """
    Load all demographic records indexed by email address.

    Parameters
    ----------
    db : pymongo.database.Database
        MongoDB database connection
    verbose : bool
        Print loading progress

    Returns
    -------
    Dict[str, dict]
        Dictionary mapping lowercase email -> demographic data
        Each entry contains: county, parcel_id, income, energy_burden, customer_name
    """
    # Find all demographic collections
    demo_collections = [c for c in db.list_collection_names() if 'Demographic' in c]

    if verbose:
        print(f"Loading demographics from {len(demo_collections)} county collections...")

    demo_by_email = {}

    for coll_name in demo_collections:
        county = coll_name.replace('CountyDemographic', '').replace('Demographic', '')
        coll = db[coll_name]

        county_count = 0
        for doc in coll.find():
            email = doc.get('email')
            if email and isinstance(email, str) and '@' in email:
                email_key = email.lower().strip()
                demo_by_email[email_key] = {
                    'county': county,
                    'parcel_id': doc.get('parcel_id'),
                    'income': doc.get('estimated_income'),
                    'energy_burden': doc.get('total_energy_burden'),
                    'customer_name': doc.get('customer_name'),
                    'annual_kwh_cost': doc.get('annual_kwh_cost'),
                }
                county_count += 1

        if verbose and county_count > 0:
            print(f"  {county}: {county_count:,} emails indexed")

    if verbose:
        print(f"Total demographic emails indexed: {len(demo_by_email):,}")

    return demo_by_email


# =============================================================================
# DATA FORMAT SPECIFICATION
# =============================================================================

@dataclass
class ClickModelData:
    """
    Data container for the click-through model.

    This dataclass defines the exact format expected by the model.

    Attributes
    ----------
    contact_id : np.ndarray
        Unique identifier for each contact (for tracking, not used in model)
        Shape: (n_contacts,)

    income : np.ndarray
        Annual household income in dollars (will be standardized internally)
        Shape: (n_contacts,)
        Example: [35000, 75000, 120000, ...]

    energy_burden : np.ndarray
        Energy burden as percentage of income spent on energy (0-100 scale)
        (will be standardized internally)
        Shape: (n_contacts,)
        Example: [3.5, 8.2, 15.0, ...]  # 3.5% of income on energy

    click : np.ndarray
        Binary outcome: 1 = clicked, 0 = did not click
        Shape: (n_contacts,)
        Example: [0, 0, 1, 0, 0, 0, 1, ...]

    age : Optional[np.ndarray]
        Age of contact in years (will be standardized internally)
        Currently NOT available in demographic data - placeholder for future
        Shape: (n_contacts,)
        Example: [25, 34, 67, 45, ...]

    # ----- TREATMENT VARIABLES (for Version 1+) -----

    channel : Optional[np.ndarray]
        Communication channel used: 'email', 'text', 'mailer'

    timing : Optional[np.ndarray]
        Time of day message was sent: 'morning', 'afternoon', 'evening'

    campaign_name : Optional[np.ndarray]
        Name/ID of specific campaign

    framing : Optional[np.ndarray]
        Message framing type: 'hopeful', 'funny', 'urgent'

    # ----- METADATA -----

    county : Optional[np.ndarray]
        County name for each contact (for stratified analysis)
    """
    # Required fields
    contact_id: np.ndarray
    income: np.ndarray
    energy_burden: np.ndarray
    click: np.ndarray

    # Optional demographic (age not currently available)
    age: Optional[np.ndarray] = None

    # Optional treatment variables (for Version 1+)
    channel: Optional[np.ndarray] = None
    timing: Optional[np.ndarray] = None
    campaign_name: Optional[np.ndarray] = None
    framing: Optional[np.ndarray] = None

    # Metadata
    county: Optional[np.ndarray] = None

    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()

    def _validate(self):
        """Run validation checks on the data."""
        n = len(self.contact_id)

        # Check required arrays have same length
        assert len(self.income) == n, f"income length {len(self.income)} != {n}"
        assert len(self.energy_burden) == n, f"energy_burden length {len(self.energy_burden)} != {n}"
        assert len(self.click) == n, f"click length {len(self.click)} != {n}"

        # Check click is binary
        assert set(np.unique(self.click)).issubset({0, 1}), "click must be binary (0 or 1)"

        # Check for missing values in required fields
        assert not np.any(np.isnan(self.income)), "income contains NaN values"
        assert not np.any(np.isnan(self.energy_burden)), "energy_burden contains NaN values"

        # Validate age if provided
        if self.age is not None:
            assert len(self.age) == n, f"age length {len(self.age)} != {n}"
            assert not np.any(np.isnan(self.age)), "age contains NaN values"

        print(f"✓ Data validated: {n} contacts, {int(self.click.sum())} clicks ({100 * self.click.mean():.2f}% CTR)")

    @property
    def n_contacts(self) -> int:
        """Number of contacts in dataset."""
        return len(self.contact_id)

    @property
    def click_rate(self) -> float:
        """Overall click-through rate."""
        return float(self.click.mean())

    def summary(self) -> pd.DataFrame:
        """Return summary statistics for the data."""
        rows = [
            ('Income ($)', self.income),
            ('Energy Burden (%)', self.energy_burden),
            ('Click', self.click),
        ]

        if self.age is not None:
            rows.insert(0, ('Age', self.age))

        return pd.DataFrame({
            'Variable': [r[0] for r in rows],
            'Mean': [r[1].mean() for r in rows],
            'Std': [r[1].std() for r in rows],
            'Min': [r[1].min() for r in rows],
            'Max': [r[1].max() for r in rows],
            'N': [len(r[1]) for r in rows],
        })

    def county_summary(self) -> Optional[pd.DataFrame]:
        """Return summary statistics by county."""
        if self.county is None:
            return None

        df = pd.DataFrame({
            'county': self.county,
            'income': self.income,
            'energy_burden': self.energy_burden,
            'click': self.click,
        })

        return df.groupby('county').agg({
            'income': ['count', 'mean'],
            'energy_burden': 'mean',
            'click': ['sum', 'mean']
        }).round(2)


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_data(use_synthetic: bool = False, verbose: bool = True,
              deduplicate_contacts: bool = True) -> ClickModelData:
    """
    Load click model data from MongoDB.

    Matches campaign participants to demographic data by email address.

    Parameters
    ----------
    use_synthetic : bool
        If True, return synthetic data for testing (default: False)
    verbose : bool
        Print loading progress (default: True)
    deduplicate_contacts : bool
        If True, keep only first occurrence per unique contact_id
        This aggregates across campaigns (default: True)

    Returns
    -------
    ClickModelData
        Populated data container ready for modeling

    Data Sources
    ------------
    - empower_development.participants: Campaign engagement data
    - empower_development.{County}Demographic: Income and energy burden

    Match Strategy
    --------------
    Primary: Email address match (participant.email_address → demographic.email)
    Coverage: ~65% of unique contacts match
    """
    if use_synthetic:
        return _load_synthetic_data()

    # Connect to database
    client, db_name = get_mongo_client()
    db = client[db_name]

    if verbose:
        print("=" * 60)
        print("LOADING CLICK MODEL DATA FROM MONGODB")
        print("=" * 60)
        print()

    # Load demographic index
    demo_by_email = load_demographic_index(db, verbose=verbose)

    if verbose:
        print()
        print("Loading participants and matching to demographics...")

    # Query participants (only those with campaign engagement data)
    participants = db['participants']

    # Build matched dataset with proper click aggregation
    # When deduplicating, a contact "clicked" if they clicked on ANY campaign
    contact_data = {}  # contact_id -> {data dict with aggregated click}
    total_participants = 0

    for doc in participants.find({'campaign_id': {'$exists': True, '$ne': None}}):
        total_participants += 1

        contact_id = doc.get('contact_id')
        email = doc.get('email_address', '')
        if not email:
            continue

        email_key = email.lower().strip()

        if email_key not in demo_by_email:
            continue

        demo = demo_by_email[email_key]

        # Skip if missing required fields
        income = demo.get('income')
        energy_burden = demo.get('energy_burden')

        if income is None or energy_burden is None:
            continue

        # Extract engagement
        engagement = doc.get('engagement', {})
        clicked = 1 if engagement.get('clicked', False) else 0

        if deduplicate_contacts:
            if contact_id in contact_data:
                # Update click to 1 if ANY campaign had a click (OR aggregation)
                if clicked:
                    contact_data[contact_id]['click'] = 1
            else:
                contact_data[contact_id] = {
                    'contact_id': contact_id,
                    'income': float(income),
                    'energy_burden': float(energy_burden),
                    'click': clicked,
                    'county': demo.get('county'),
                }
        else:
            # No deduplication - keep all records
            contact_data[f"{contact_id}_{doc.get('campaign_id')}"] = {
                'contact_id': contact_id,
                'income': float(income),
                'energy_burden': float(energy_burden),
                'click': clicked,
                'county': demo.get('county'),
                'campaign_id': doc.get('campaign_id'),
            }

    matched_records = list(contact_data.values())

    client.close()

    if not matched_records:
        raise ValueError("No matched records found! Check database connection and data.")

    if verbose:
        print(f"  Total participant records scanned: {total_participants:,}")
        print(f"  Matched contacts (with demographics): {len(matched_records):,}")
        print()

    # Convert to arrays
    df = pd.DataFrame(matched_records)

    # Build ClickModelData
    data = ClickModelData(
        contact_id=df['contact_id'].values,
        income=df['income'].values,
        energy_burden=df['energy_burden'].values,
        click=df['click'].values,
        county=df['county'].values,
        channel=np.array(['email'] * len(df)),  # All are email campaigns
    )

    if verbose:
        print("=" * 60)
        print("DATA SUMMARY")
        print("=" * 60)
        print(data.summary().to_string(index=False))
        print()
        if data.county is not None:
            print("By County:")
            print(data.county_summary())

    return data


def _load_synthetic_data() -> ClickModelData:
    """Generate synthetic data for testing."""
    print("⚠️  Using SYNTHETIC data for testing")

    np.random.seed(42)
    n = 10000

    # Simulate demographics (no age)
    income = np.random.lognormal(10.8, 0.5, n).clip(15000, 500000)
    energy_burden = np.random.exponential(6, n).clip(1, 30)

    # Simulate click probability
    logit_p = (
        -4.0  # Baseline (~2-3% CTR)
        + 0.3 * ((energy_burden - 6) / 5)  # Higher burden → more clicks
        + 0.2 * np.exp(-((income - 60000) / 30000) ** 2)  # Middle income peak
    )
    p_click = 1 / (1 + np.exp(-logit_p))
    click = np.random.binomial(1, p_click)

    return ClickModelData(
        contact_id=np.arange(n).astype(str),
        income=income,
        energy_burden=energy_burden,
        click=click,
        channel=np.random.choice(['email', 'text', 'mailer'], n, p=[0.6, 0.25, 0.15]),
    )


# =============================================================================
# DIAGNOSTIC FUNCTIONS
# =============================================================================

def diagnose_match_coverage(verbose: bool = True) -> Dict[str, any]:
    """
    Analyze match coverage between participants and demographics.

    Returns detailed statistics about data availability.

    Returns
    -------
    Dict with keys:
        - total_participants: Total participant records
        - unique_contacts: Unique contact IDs
        - unique_emails: Unique email addresses in participants
        - demo_emails: Unique emails in demographics
        - matched_emails: Emails that match both sources
        - match_rate: Percentage of contacts matched
        - by_county: Match counts per county
    """
    client, db_name = get_mongo_client()
    db = client[db_name]

    if verbose:
        print("Diagnosing match coverage...")

    # Load demographics
    demo_by_email = load_demographic_index(db, verbose=False)

    # Analyze participants
    participants = db['participants']

    total_records = participants.count_documents({'campaign_id': {'$exists': True}})
    unique_contacts = set()
    participant_emails = set()

    for doc in participants.find({'campaign_id': {'$exists': True}}):
        unique_contacts.add(doc.get('contact_id'))
        email = doc.get('email_address', '')
        if email:
            participant_emails.add(email.lower().strip())

    # Calculate overlap
    demo_email_set = set(demo_by_email.keys())
    matched_emails = participant_emails & demo_email_set

    # Count by county
    by_county = {}
    for email in matched_emails:
        county = demo_by_email[email].get('county', 'Unknown')
        by_county[county] = by_county.get(county, 0) + 1

    client.close()

    result = {
        'total_participants': total_records,
        'unique_contacts': len(unique_contacts),
        'unique_emails': len(participant_emails),
        'demo_emails': len(demo_email_set),
        'matched_emails': len(matched_emails),
        'match_rate': len(matched_emails) / len(participant_emails) * 100 if participant_emails else 0,
        'by_county': by_county,
    }

    if verbose:
        print(f"\n{'='*50}")
        print("MATCH COVERAGE DIAGNOSIS")
        print('='*50)
        print(f"Total participant records: {result['total_participants']:,}")
        print(f"Unique contacts: {result['unique_contacts']:,}")
        print(f"Unique participant emails: {result['unique_emails']:,}")
        print(f"Demographic emails available: {result['demo_emails']:,}")
        print(f"Matched emails: {result['matched_emails']:,}")
        print(f"Match rate: {result['match_rate']:.1f}%")
        print(f"\nBy County:")
        for county, count in sorted(by_county.items(), key=lambda x: -x[1]):
            print(f"  {county}: {count:,}")

    return result


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Click Model Data Loader")
    parser.add_argument("--diagnose", action="store_true", help="Run match coverage diagnosis")
    parser.add_argument("--synthetic", action="store_true", help="Load synthetic data")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")

    args = parser.parse_args()

    if args.diagnose:
        diagnose_match_coverage(verbose=not args.quiet)
    else:
        data = load_data(use_synthetic=args.synthetic, verbose=not args.quiet)
        print(f"\nLoaded {data.n_contacts:,} contacts with {data.click.sum():.0f} clicks")
