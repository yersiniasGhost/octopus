"""
Optimized participant matching using zipcode-to-county lookup

This script:
1. Loads zipcode-to-county mapping from cache file
2. Finds all opened/clicked participants from MONGO_DB
3. Uses participant zipcode to identify target county collection
4. Matches participants to county demographic/residential data using:
   - Address matching (exact and fuzzy)
   - Phone number matching
   - Name matching
5. Reports match statistics (good, fuzzy, no match)
"""
import os
import sys
import re
import json
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MatchQuality(Enum):
    """Match quality levels"""
    GOOD = "good"           # Direct exact match
    FUZZY = "fuzzy"         # Normalized/partial match
    NO_MATCH = "no_match"   # No match found


@dataclass
class MatchResult:
    """Result of matching a participant to county data"""
    participant_id: str
    participant_email: str
    participant_data: Dict
    match_quality: MatchQuality
    county_record: Optional[Dict] = None
    residential_record: Optional[Dict] = None
    match_method: Optional[str] = None
    match_score: float = 0.0
    county_name: Optional[str] = None


class AddressNormalizer:
    """Normalize addresses for matching"""

    STREET_ABBREV = {
        'street': 'st', 'avenue': 'ave', 'road': 'rd', 'drive': 'dr',
        'lane': 'ln', 'court': 'ct', 'circle': 'cir', 'boulevard': 'blvd',
        'parkway': 'pkwy', 'place': 'pl', 'terrace': 'ter', 'way': 'way',
    }

    DIRECTIONAL_ABBREV = {
        'north': 'n', 'south': 's', 'east': 'e', 'west': 'w',
        'northeast': 'ne', 'northwest': 'nw', 'southeast': 'se', 'southwest': 'sw',
    }

    @classmethod
    def normalize(cls, address: str) -> str:
        """Normalize address for matching"""
        if not address:
            return ""

        addr = address.lower().strip()
        addr = re.sub(r'[,.]', '', addr)

        for full, abbrev in cls.STREET_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        for full, abbrev in cls.DIRECTIONAL_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        addr = re.sub(r'\s+', ' ', addr)
        return addr.strip()

    @classmethod
    def exact_match(cls, addr1: str, addr2: str) -> bool:
        """Check if two addresses match exactly after normalization"""
        return cls.normalize(addr1) == cls.normalize(addr2)

    @classmethod
    def fuzzy_match(cls, addr1: str, addr2: str) -> Tuple[bool, float]:
        """
        Fuzzy address matching with score
        Returns: (is_match, confidence_score)
        """
        norm1 = cls.normalize(addr1)
        norm2 = cls.normalize(addr2)

        if not norm1 or not norm2:
            return False, 0.0

        if norm1 == norm2:
            return True, 1.0

        # Extract street number
        match1 = re.match(r'^(\d+)', norm1)
        match2 = re.match(r'^(\d+)', norm2)

        if not match1 or not match2:
            return False, 0.0

        # Street numbers must match
        if match1.group(1) != match2.group(1):
            return False, 0.0

        # Calculate similarity of rest of address
        rest1 = norm1[len(match1.group(1)):].strip()
        rest2 = norm2[len(match2.group(1)):].strip()

        if rest1 in rest2 or rest2 in rest1:
            score = min(len(rest1), len(rest2)) / max(len(rest1), len(rest2))
            return score > 0.7, score

        return False, 0.0


class PhoneNormalizer:
    """Normalize phone numbers for matching"""

    @classmethod
    def normalize(cls, phone: str) -> str:
        """Normalize phone number to digits only"""
        if not phone:
            return ""

        phone_str = str(phone)
        digits = re.sub(r'\D', '', phone_str)

        # Remove leading 1 if 11 digits
        if len(digits) == 11 and digits[0] == '1':
            digits = digits[1:]

        return digits

    @classmethod
    def match(cls, phone1: str, phone2: str) -> bool:
        """Check if two phone numbers match"""
        norm1 = cls.normalize(phone1)
        norm2 = cls.normalize(phone2)

        if not norm1 or not norm2:
            return False

        return norm1 == norm2


class NameMatcher:
    """Match names with various formats"""

    @classmethod
    def normalize(cls, name: str) -> str:
        """Normalize name for comparison"""
        if not name:
            return ""

        name = re.sub(r'\s+', ' ', name.lower().strip())
        name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
        return name.strip()

    @classmethod
    def match(cls, first: str, last: str, full_name: str) -> Tuple[bool, str]:
        """
        Match first/last name against full name
        Returns: (is_match, match_type)
        """
        if not first and not last:
            return False, ""

        if not full_name:
            return False, ""

        norm_first = cls.normalize(first) if first else ""
        norm_last = cls.normalize(last) if last else ""
        norm_full = cls.normalize(full_name)

        # Exact match
        if norm_first and norm_last:
            full_constructed = f"{norm_first} {norm_last}"
            if full_constructed in norm_full or norm_full.startswith(full_constructed):
                return True, "exact"

        # Fuzzy match: last name + first initial
        if norm_last and norm_last in norm_full:
            if norm_first and (norm_first in norm_full or norm_full.startswith(norm_first[0])):
                return True, "fuzzy"

        return False, ""


class OptimizedParticipantMatcher:
    """Optimized matching using zipcode-to-county lookup"""

    def __init__(self):
        """Initialize MongoDB connections and load zipcode cache"""
        # MONGO_DB - participant data
        self.mongo_host = os.getenv('MONGODB_HOST', 'localhost')
        self.mongo_port = int(os.getenv('MONGODB_PORT', '27017'))
        self.mongo_db = os.getenv('MONGODB_DATABASE', 'emailoctopus_db')

        # MONGO_DB_RM - county data
        self.mongo_host_rm = os.getenv('MONGODB_HOST_RM', 'localhost')
        self.mongo_port_rm = int(os.getenv('MONGODB_PORT_RM', '27017'))
        self.mongo_db_rm = os.getenv('MONGODB_DATABASE_RM', 'empower_development')

        # Connect to databases
        logger.info(f"Connecting to participant DB: {self.mongo_host}:{self.mongo_port}/{self.mongo_db}")
        self.client_participants = MongoClient(self.mongo_host, self.mongo_port)
        self.db_participants = self.client_participants[self.mongo_db]

        logger.info(f"Connecting to county DB: {self.mongo_host_rm}:{self.mongo_port_rm}/{self.mongo_db_rm}")
        self.client_county = MongoClient(self.mongo_host_rm, self.mongo_port_rm)
        self.db_county = self.client_county[self.mongo_db_rm]

        # Load zipcode-to-county mapping
        self.zipcode_map = self._load_zipcode_cache()

        # Statistics
        self.stats = {
            'total_participants': 0,
            'with_zipcode': 0,
            'without_zipcode': 0,
            'good_matches': 0,
            'fuzzy_matches': 0,
            'no_matches': 0,
            'match_methods': {
                'address': 0,
                'phone': 0,
                'name': 0,
                'address_phone': 0,
                'address_name': 0,
            },
            'by_county': {}
        }

    def _load_zipcode_cache(self) -> Dict[str, str]:
        """Load zipcode-to-county mapping from JSON file"""
        cache_path = Path(__file__).parent.parent / 'data' / 'zipcode_to_county_cache.json'

        logger.info(f"Loading zipcode cache from: {cache_path}")

        if not cache_path.exists():
            logger.error(f"Zipcode cache file not found: {cache_path}")
            raise FileNotFoundError(f"Missing zipcode cache: {cache_path}")

        with open(cache_path, 'r') as f:
            data = json.load(f)

        zipcode_map = data.get('zipcode_map', {})
        logger.info(f"Loaded {len(zipcode_map)} zipcode mappings")

        return zipcode_map

    def get_engaged_participants(self) -> List[Dict]:
        """Get all participants who opened or clicked"""
        logger.info("Fetching engaged participants (opened or clicked)...")

        query = {
            '$or': [
                {'engagement.opened': True},
                {'engagement.clicked': True}
            ]
        }

        participants = list(self.db_participants.participants.find(query))
        self.stats['total_participants'] = len(participants)

        logger.info(f"Found {len(participants)} engaged participants")
        return participants

    def get_county_from_zipcode(self, zipcode: str) -> Optional[str]:
        """Get county name from zipcode using cache"""
        if not zipcode:
            return None

        # Normalize zipcode to 5 digits
        zip_str = str(zipcode).strip().zfill(5)

        county = self.zipcode_map.get(zip_str)

        if not county:
            logger.debug(f"No county mapping found for zipcode: {zipcode}")

        return county

    def match_participant(self, participant: Dict) -> MatchResult:
        """
        Match a single participant to county data using zipcode lookup

        Process:
        1. Get participant zipcode
        2. Look up county name
        3. Search only that county's collections
        4. Try multiple matching strategies
        """
        p_id = str(participant.get('_id', 'unknown'))
        p_email = participant.get('email_address', '')
        fields = participant.get('fields', {})

        p_address = fields.get('Address', '')
        p_phone = fields.get('Cell', '')
        p_first = fields.get('FirstName', '')
        p_last = fields.get('LastName', '')
        p_zip = fields.get('ZIP', '')

        # Create base result
        base_result = MatchResult(
            participant_id=p_id,
            participant_email=p_email,
            participant_data=participant,
            match_quality=MatchQuality.NO_MATCH
        )

        # Check if we have zipcode
        if not p_zip:
            logger.debug(f"Participant {p_email} has no zipcode")
            self.stats['without_zipcode'] += 1
            return base_result

        self.stats['with_zipcode'] += 1

        # Get county name from zipcode
        county_name = self.get_county_from_zipcode(p_zip)

        if not county_name:
            logger.debug(f"No county found for zipcode {p_zip} (participant: {p_email})")
            return base_result

        base_result.county_name = county_name

        # Initialize county stats if needed
        if county_name not in self.stats['by_county']:
            self.stats['by_county'][county_name] = {
                'total': 0, 'matched': 0, 'unmatched': 0
            }
        self.stats['by_county'][county_name]['total'] += 1

        # Target collections for this county
        demographic_collection = f"{county_name}Demographic"
        residential_collection = f"{county_name}Residential"

        # Check if collections exist
        available_collections = self.db_county.list_collection_names()

        if demographic_collection not in available_collections:
            logger.warning(f"Demographic collection not found: {demographic_collection}")
            return base_result

        logger.debug(f"Searching {demographic_collection} for participant {p_email}")

        # Get collection reference
        demo_coll = self.db_county[demographic_collection]

        # Try matching strategies
        best_match = None
        best_score = 0.0

        # Strategy 1: Address + Phone (GOOD match)
        if p_address and p_phone:
            match = self._match_address_phone(demo_coll, p_address, p_phone, p_zip)
            if match and match.match_quality == MatchQuality.GOOD:
                match.participant_id = p_id
                match.participant_email = p_email
                match.participant_data = participant
                match.county_name = county_name
                self._update_match_stats(match, county_name)
                return match
            if match and match.match_score > best_score:
                best_match = match
                best_score = match.match_score

        # Strategy 2: Address only
        if p_address:
            match = self._match_address(demo_coll, p_address, p_zip)
            if match and match.match_score > best_score:
                best_match = match
                best_score = match.match_score

        # Strategy 3: Phone only (GOOD match if found)
        if p_phone:
            match = self._match_phone(demo_coll, p_phone)
            if match and match.match_quality == MatchQuality.GOOD:
                match.participant_id = p_id
                match.participant_email = p_email
                match.participant_data = participant
                match.county_name = county_name
                self._update_match_stats(match, county_name)
                return match

        # Strategy 4: Name + Address
        if p_first and p_last and p_address:
            match = self._match_name_address(demo_coll, p_first, p_last, p_address, p_zip)
            if match and match.match_score > best_score:
                best_match = match
                best_score = match.match_score

        # Return best match or no match
        if best_match:
            best_match.participant_id = p_id
            best_match.participant_email = p_email
            best_match.participant_data = participant
            best_match.county_name = county_name
            self._update_match_stats(best_match, county_name)

            # Try to get residential data
            if residential_collection in available_collections:
                res_coll = self.db_county[residential_collection]
                parcel_id = best_match.county_record.get('parcel_id')
                if parcel_id:
                    res_record = res_coll.find_one({'parcel_id': parcel_id})
                    if res_record:
                        best_match.residential_record = res_record

            return best_match

        # No match found
        self.stats['by_county'][county_name]['unmatched'] += 1
        return base_result

    def _update_match_stats(self, match: MatchResult, county_name: str):
        """Update statistics for a match"""
        if match.match_quality == MatchQuality.GOOD:
            self.stats['good_matches'] += 1
        elif match.match_quality == MatchQuality.FUZZY:
            self.stats['fuzzy_matches'] += 1
        else:
            self.stats['no_matches'] += 1

        if county_name:
            self.stats['by_county'][county_name]['matched'] += 1

    def _match_address_phone(self, collection, address: str, phone: str, zip_code: str) -> Optional[MatchResult]:
        """Match by both address and phone (highest confidence)"""
        norm_phone = PhoneNormalizer.normalize(phone)

        if not norm_phone:
            return None

        # Build query
        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            county_addr = record.get('address', '')
            county_phone = str(record.get('mobile', ''))

            addr_match = AddressNormalizer.exact_match(address, county_addr)
            phone_match = PhoneNormalizer.match(phone, county_phone)

            if addr_match and phone_match:
                self.stats['match_methods']['address_phone'] += 1
                return MatchResult(
                    participant_id="",
                    participant_email="",
                    participant_data={},
                    match_quality=MatchQuality.GOOD,
                    county_record=record,
                    match_method='address_phone',
                    match_score=1.0
                )

        return None

    def _match_address(self, collection, address: str, zip_code: str) -> Optional[MatchResult]:
        """Match by address only"""
        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            county_addr = record.get('address', '')

            # Try exact match first
            if AddressNormalizer.exact_match(address, county_addr):
                self.stats['match_methods']['address'] += 1
                return MatchResult(
                    participant_id="",
                    participant_email="",
                    participant_data={},
                    match_quality=MatchQuality.GOOD,
                    county_record=record,
                    match_method='address',
                    match_score=1.0
                )

            # Try fuzzy match
            is_match, score = AddressNormalizer.fuzzy_match(address, county_addr)
            if is_match:
                self.stats['match_methods']['address'] += 1
                return MatchResult(
                    participant_id="",
                    participant_email="",
                    participant_data={},
                    match_quality=MatchQuality.FUZZY,
                    county_record=record,
                    match_method='address',
                    match_score=score
                )

        return None

    def _match_phone(self, collection, phone: str) -> Optional[MatchResult]:
        """Match by phone number only"""
        norm_phone = PhoneNormalizer.normalize(phone)

        if not norm_phone:
            return None

        for record in collection.find():
            county_phone = str(record.get('mobile', ''))

            if PhoneNormalizer.match(phone, county_phone):
                self.stats['match_methods']['phone'] += 1
                return MatchResult(
                    participant_id="",
                    participant_email="",
                    participant_data={},
                    match_quality=MatchQuality.GOOD,
                    county_record=record,
                    match_method='phone',
                    match_score=1.0
                )

        return None

    def _match_name_address(self, collection, first: str, last: str,
                           address: str, zip_code: str) -> Optional[MatchResult]:
        """Match by name and address combination"""
        query = {}
        if zip_code:
            try:
                query['parcel_zip'] = int(zip_code)
            except ValueError:
                pass

        for record in collection.find(query):
            county_addr = record.get('address', '')
            county_name = record.get('customer_name', '')

            # Address must match
            addr_exact = AddressNormalizer.exact_match(address, county_addr)
            addr_fuzzy, addr_score = AddressNormalizer.fuzzy_match(address, county_addr)

            if not (addr_exact or addr_fuzzy):
                continue

            # Name must match
            name_match, match_type = NameMatcher.match(first, last, county_name)

            if name_match:
                quality = MatchQuality.GOOD if (addr_exact and match_type == 'exact') else MatchQuality.FUZZY
                score = 1.0 if quality == MatchQuality.GOOD else addr_score * 0.9

                self.stats['match_methods']['address_name'] += 1
                return MatchResult(
                    participant_id="",
                    participant_email="",
                    participant_data={},
                    match_quality=quality,
                    county_record=record,
                    match_method='address_name',
                    match_score=score
                )

        return None

    def run_matching(self) -> List[MatchResult]:
        """Run matching process for all engaged participants"""
        logger.info("Starting optimized participant matching process...")

        participants = self.get_engaged_participants()
        results = []

        for i, participant in enumerate(participants, 1):
            if i % 100 == 0:
                logger.info(f"Processing participant {i}/{len(participants)}...")

            result = self.match_participant(participant)
            results.append(result)

        # Update final no_match count
        self.stats['no_matches'] = len([r for r in results if r.match_quality == MatchQuality.NO_MATCH])

        return results

    def print_statistics(self):
        """Print matching statistics"""
        print("\n" + "="*70)
        print("OPTIMIZED MATCHING STATISTICS")
        print("="*70)
        print(f"Total Participants:     {self.stats['total_participants']}")
        print(f"With Zipcode:           {self.stats['with_zipcode']} ({self._pct('with_zipcode')}%)")
        print(f"Without Zipcode:        {self.stats['without_zipcode']} ({self._pct('without_zipcode')}%)")
        print()
        print(f"Good Matches:           {self.stats['good_matches']} ({self._pct_matched('good_matches')}%)")
        print(f"Fuzzy Matches:          {self.stats['fuzzy_matches']} ({self._pct_matched('fuzzy_matches')}%)")
        print(f"No Matches:             {self.stats['no_matches']} ({self._pct_matched('no_matches')}%)")
        print()
        print("Match Methods:")
        for method, count in self.stats['match_methods'].items():
            if count > 0:
                print(f"  {method:20s}: {count}")

        if self.stats['by_county']:
            print()
            print("By County:")
            for county, counts in sorted(self.stats['by_county'].items()):
                matched_pct = (counts['matched'] / counts['total'] * 100) if counts['total'] > 0 else 0
                print(f"  {county:30s}: {counts['matched']:4d}/{counts['total']:4d} matched ({matched_pct:.1f}%)")

        print("="*70 + "\n")

    def _pct(self, key: str) -> str:
        """Calculate percentage of total participants"""
        total = self.stats['total_participants']
        if total == 0:
            return "0.0"
        return f"{(self.stats[key] / total * 100):.1f}"

    def _pct_matched(self, key: str) -> str:
        """Calculate percentage of participants with zipcode"""
        total = self.stats['with_zipcode']
        if total == 0:
            return "0.0"
        return f"{(self.stats[key] / total * 100):.1f}"

    def close(self):
        """Close database connections"""
        self.client_participants.close()
        self.client_county.close()


def main():
    """Main execution"""
    matcher = OptimizedParticipantMatcher()

    try:
        # Run matching
        results = matcher.run_matching()

        # Print statistics
        matcher.print_statistics()

        logger.info(f"Matching complete. {len(results)} results ready for CSV export.")

    except Exception as e:
        logger.error(f"Error during matching: {e}", exc_info=True)
        return 1
    finally:
        matcher.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
