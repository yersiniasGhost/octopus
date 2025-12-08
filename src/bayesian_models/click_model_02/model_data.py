"""
Click Model 02 Data Loader
===========================

This module defines the data format for the click-through model version 02,
which adds house age (year built) as a predictor.

Data Flow:
    empower_development.participants (campaign engagement)
        ↓ match by email
    empower_development.{County}Demographic (income, energy_burden, parcel_id)
        ↓ match by parcel_id
    empower_development.{County}Residential (house age / year built)
        ↓
    ClickModelData (model-ready format)

Database Schema Reference:
    participants: campaign_id, contact_id, email_address, engagement.clicked
    {County}Demographic: email, estimated_income, total_energy_burden, parcel_id
    {County}Residential: parcel_id, age (year built)
"""

import os
from datetime import datetime
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
    """
    load_dotenv()

    host = os.getenv('MONGODB_HOST_RM', 'localhost')
    port = int(os.getenv('MONGODB_PORT_RM', '27017'))
    db_name = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

    client = MongoClient(host, port)
    return client, db_name


# =============================================================================
# RESIDENTIAL DATA LOADER (HOUSE AGE)
# =============================================================================

def load_residential_index(db, verbose: bool = True) -> Dict[str, dict]:
    """
    Load all residential records indexed by parcel_id.

    Parameters
    ----------
    db : pymongo.database.Database
        MongoDB database connection
    verbose : bool
        Print loading progress

    Returns
    -------
    Dict[str, dict]
        Dictionary mapping parcel_id -> residential data
        Each entry contains: county, age (year built)
    """
    # Find all residential collections
    res_collections = [c for c in db.list_collection_names() if 'Residential' in c]

    if verbose:
        print(f"Loading residential data from {len(res_collections)} county collections...")

    res_by_parcel = {}

    for coll_name in res_collections:
        # Extract county name from collection name
        county = coll_name.replace('CountyResidential', '').replace('Residential', '')
        coll = db[coll_name]

        county_count = 0
        for doc in coll.find({'age': {'$exists': True, '$ne': None}}):
            parcel_id = doc.get('parcel_id')
            if parcel_id:
                age = doc.get('age')
                # age is year built (e.g., 1987, 2013)
                if age and isinstance(age, (int, float)) and 1800 <= age <= 2025:
                    res_by_parcel[parcel_id] = {
                        'county': county,
                        'year_built': int(age),
                    }
                    county_count += 1

        if verbose and county_count > 0:
            print(f"  {county}: {county_count:,} parcels with house age")

    if verbose:
        print(f"Total residential parcels indexed: {len(res_by_parcel):,}")

    return res_by_parcel


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
    Data container for the click-through model version 02.

    This version adds house_age (years since built) as a predictor.

    Attributes
    ----------
    contact_id : np.ndarray
        Unique identifier for each contact (for tracking, not used in model)

    income : np.ndarray
        Annual household income in dollars (will be standardized internally)

    energy_burden : np.ndarray
        Energy burden as percentage of income spent on energy (0-100 scale)

    house_age : np.ndarray
        Age of the house in years (current_year - year_built)
        Example: [35, 10, 95, 5, ...]  # 35 years old, 10 years old, etc.

    click : np.ndarray
        Binary outcome: 1 = clicked, 0 = did not click

    age : Optional[np.ndarray]
        Age of contact in years (placeholder for future - not currently available)

    channel : Optional[np.ndarray]
        Communication channel used: 'email', 'text', 'mailer'

    county : Optional[np.ndarray]
        County name for each contact (for stratified analysis)
    """
    # Required fields
    contact_id: np.ndarray
    income: np.ndarray
    energy_burden: np.ndarray
    house_age: np.ndarray  # NEW: Age of house in years
    click: np.ndarray

    # Optional demographic (owner age not currently available)
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
        assert len(self.house_age) == n, f"house_age length {len(self.house_age)} != {n}"
        assert len(self.click) == n, f"click length {len(self.click)} != {n}"

        # Check click is binary
        assert set(np.unique(self.click)).issubset({0, 1}), "click must be binary (0 or 1)"

        # Check for missing values in required fields
        assert not np.any(np.isnan(self.income)), "income contains NaN values"
        assert not np.any(np.isnan(self.energy_burden)), "energy_burden contains NaN values"
        assert not np.any(np.isnan(self.house_age)), "house_age contains NaN values"

        # Validate owner age if provided
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
            ('House Age (years)', self.house_age),
            ('Click', self.click),
        ]

        if self.age is not None:
            rows.insert(0, ('Owner Age', self.age))

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
            'house_age': self.house_age,
            'click': self.click,
        })

        return df.groupby('county').agg({
            'income': ['count', 'mean'],
            'energy_burden': 'mean',
            'house_age': 'mean',
            'click': ['sum', 'mean']
        }).round(2)


# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_data(use_synthetic: bool = False, verbose: bool = True,
              deduplicate_contacts: bool = True) -> ClickModelData:
    """
    Load click model data from MongoDB with house age.

    Matches campaign participants to demographic and residential data.

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
    - empower_development.{County}Residential: House age (year built)

    Match Strategy
    --------------
    1. Email address match (participant.email_address → demographic.email)
    2. Parcel ID match (demographic.parcel_id → residential.parcel_id)
    """
    if use_synthetic:
        return _load_synthetic_data()

    # Connect to database
    client, db_name = get_mongo_client()
    db = client[db_name]

    current_year = datetime.now().year

    if verbose:
        print("=" * 60)
        print("LOADING CLICK MODEL 02 DATA FROM MONGODB")
        print("(with house age)")
        print("=" * 60)
        print()

    # Load residential index (parcel_id -> year_built)
    res_by_parcel = load_residential_index(db, verbose=verbose)

    if verbose:
        print()

    # Load demographic index
    demo_by_email = load_demographic_index(db, verbose=verbose)

    if verbose:
        print()
        print("Loading participants and matching to demographics + residential...")

    # Query participants (only those with campaign engagement data)
    participants = db['participants']

    # Build matched dataset with proper click aggregation
    contact_data = {}  # contact_id -> {data dict with aggregated click}
    total_participants = 0
    matched_with_house_age = 0

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

        # Skip if missing required demographic fields
        income = demo.get('income')
        energy_burden = demo.get('energy_burden')

        if income is None or energy_burden is None:
            continue

        # Get house age from residential data
        parcel_id = demo.get('parcel_id')
        if parcel_id is None or parcel_id not in res_by_parcel:
            continue  # Skip if no house age data

        res = res_by_parcel[parcel_id]
        year_built = res.get('year_built')
        if year_built is None:
            continue

        house_age = current_year - year_built
        matched_with_house_age += 1

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
                    'house_age': float(house_age),
                    'click': clicked,
                    'county': demo.get('county'),
                }
        else:
            # No deduplication - keep all records
            contact_data[f"{contact_id}_{doc.get('campaign_id')}"] = {
                'contact_id': contact_id,
                'income': float(income),
                'energy_burden': float(energy_burden),
                'house_age': float(house_age),
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
        print(f"  Matched contacts (with demographics + house age): {len(matched_records):,}")
        print()

    # Convert to arrays
    df = pd.DataFrame(matched_records)

    # Build ClickModelData
    data = ClickModelData(
        contact_id=df['contact_id'].values,
        income=df['income'].values,
        energy_burden=df['energy_burden'].values,
        house_age=df['house_age'].values,
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

    # Simulate demographics
    income = np.random.lognormal(10.8, 0.5, n).clip(15000, 500000)
    energy_burden = np.random.exponential(6, n).clip(1, 30)
    house_age = np.random.exponential(30, n).clip(1, 150)  # House age in years

    # Simulate click probability (include house age effect)
    logit_p = (
        -4.0  # Baseline (~2-3% CTR)
        + 0.3 * ((energy_burden - 6) / 5)  # Higher burden → more clicks
        + 0.2 * np.exp(-((income - 60000) / 30000) ** 2)  # Middle income peak
        + 0.1 * ((house_age - 30) / 20)  # Older houses → slightly more clicks
    )
    p_click = 1 / (1 + np.exp(-logit_p))
    click = np.random.binomial(1, p_click)

    return ClickModelData(
        contact_id=np.arange(n).astype(str),
        income=income,
        energy_burden=energy_burden,
        house_age=house_age,
        click=click,
        channel=np.random.choice(['email', 'text', 'mailer'], n, p=[0.6, 0.25, 0.15]),
    )


# =============================================================================
# DIAGNOSTIC FUNCTIONS
# =============================================================================

def diagnose_match_coverage(verbose: bool = True) -> Dict[str, any]:
    """
    Analyze match coverage between participants, demographics, and residential.

    Returns detailed statistics about data availability including house age coverage.
    """
    client, db_name = get_mongo_client()
    db = client[db_name]

    if verbose:
        print("Diagnosing match coverage (with house age)...")

    # Load indices
    demo_by_email = load_demographic_index(db, verbose=False)
    res_by_parcel = load_residential_index(db, verbose=False)

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

    # Count with house age
    matched_with_house_age = 0
    by_county = {}
    for email in matched_emails:
        demo = demo_by_email[email]
        county = demo.get('county', 'Unknown')
        parcel_id = demo.get('parcel_id')
        if parcel_id and parcel_id in res_by_parcel:
            matched_with_house_age += 1
            by_county[county] = by_county.get(county, 0) + 1

    client.close()

    result = {
        'total_participants': total_records,
        'unique_contacts': len(unique_contacts),
        'unique_emails': len(participant_emails),
        'demo_emails': len(demo_email_set),
        'residential_parcels': len(res_by_parcel),
        'matched_emails': len(matched_emails),
        'matched_with_house_age': matched_with_house_age,
        'house_age_coverage': matched_with_house_age / len(matched_emails) * 100 if matched_emails else 0,
        'by_county': by_county,
    }

    if verbose:
        print(f"\n{'='*50}")
        print("MATCH COVERAGE DIAGNOSIS (with house age)")
        print('='*50)
        print(f"Total participant records: {result['total_participants']:,}")
        print(f"Unique contacts: {result['unique_contacts']:,}")
        print(f"Unique participant emails: {result['unique_emails']:,}")
        print(f"Demographic emails available: {result['demo_emails']:,}")
        print(f"Residential parcels available: {result['residential_parcels']:,}")
        print(f"Matched emails: {result['matched_emails']:,}")
        print(f"Matched with house age: {result['matched_with_house_age']:,}")
        print(f"House age coverage: {result['house_age_coverage']:.1f}%")
        print(f"\nBy County (with house age):")
        for county, count in sorted(by_county.items(), key=lambda x: -x[1]):
            print(f"  {county}: {count:,}")

    return result


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Click Model 02 Data Loader (with house age)")
    parser.add_argument("--diagnose", action="store_true", help="Run match coverage diagnosis")
    parser.add_argument("--synthetic", action="store_true", help="Load synthetic data")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")

    args = parser.parse_args()

    if args.diagnose:
        diagnose_match_coverage(verbose=not args.quiet)
    else:
        data = load_data(use_synthetic=args.synthetic, verbose=not args.quiet)
        print(f"\nLoaded {data.n_contacts:,} contacts with {data.click.sum():.0f} clicks")
