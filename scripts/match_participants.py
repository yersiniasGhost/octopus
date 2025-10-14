"""
Match EmailOctopus participants with county demographic/residential data

This script:
1. Finds all opened/clicked participants from MONGO_DB
2. Matches them to county data in MONGO_DB_RM using:
   - Address matching (with normalization)
   - Phone number matching
   - Name matching
3. Reports match statistics (good, fuzzy, no match)
"""
import os
import sys
import re
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

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
    match_quality: MatchQuality
    county_record: Optional[Dict] = None
    match_method: Optional[str] = None  # 'address', 'phone', 'name'
    match_score: float = 0.0


class AddressNormalizer:
    """Normalize addresses for matching"""

    # Common street type abbreviations
    STREET_ABBREV = {
        'street': 'st',
        'avenue': 'ave',
        'road': 'rd',
        'drive': 'dr',
        'lane': 'ln',
        'court': 'ct',
        'circle': 'cir',
        'boulevard': 'blvd',
        'parkway': 'pkwy',
        'place': 'pl',
        'terrace': 'ter',
        'way': 'way',
    }

    # Directional abbreviations
    DIRECTIONAL_ABBREV = {
        'north': 'n',
        'south': 's',
        'east': 'e',
        'west': 'w',
        'northeast': 'ne',
        'northwest': 'nw',
        'southeast': 'se',
        'southwest': 'sw',
    }

    @classmethod
    def normalize(cls, address: str) -> str:
        """
        Normalize address for matching

        Examples:
            "123 Main Street" -> "123 main st"
            "456 Oak Ave." -> "456 oak ave"
        """
        if not address:
            return ""

        # Convert to lowercase
        addr = address.lower().strip()

        # Remove punctuation
        addr = re.sub(r'[,.]', '', addr)

        # Normalize street types
        for full, abbrev in cls.STREET_ABBREV.items():
            # Replace full word at end or before number
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        # Normalize directionals
        for full, abbrev in cls.DIRECTIONAL_ABBREV.items():
            addr = re.sub(rf'\b{full}\b', abbrev, addr)

        # Collapse multiple spaces
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

        Returns:
            (is_match, confidence_score)
        """
        norm1 = cls.normalize(addr1)
        norm2 = cls.normalize(addr2)

        if not norm1 or not norm2:
            return False, 0.0

        # Exact match after normalization
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

        # Simple substring matching
        if rest1 in rest2 or rest2 in rest1:
            score = min(len(rest1), len(rest2)) / max(len(rest1), len(rest2))
            return score > 0.7, score

        return False, 0.0


class PhoneNormalizer:
    """Normalize phone numbers for matching"""

    @classmethod
    def normalize(cls, phone: str) -> str:
        """
        Normalize phone number to digits only

        Examples:
            "(216) 225-3312" -> "2162253312"
            "216-225-3312" -> "2162253312"
        """
        if not phone:
            return ""

        # Convert to string if float
        phone_str = str(phone)

        # Remove all non-digits
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

        # Convert to lowercase, remove extra spaces
        name = re.sub(r'\s+', ' ', name.lower().strip())

        # Remove common suffixes
        name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)

        return name.strip()

    @classmethod
    def match(cls, first: str, last: str, full_name: str) -> Tuple[bool, str]:
        """
        Match first/last name against full name

        Args:
            first: First name from participant
            last: Last name from participant
            full_name: Full name from county data (e.g., "SEAN D CONWAY")

        Returns:
            (is_match, match_type) where match_type is 'exact' or 'fuzzy'
        """
        if not first and not last:
            return False, ""

        if not full_name:
            return False, ""

        norm_first = cls.normalize(first) if first else ""
        norm_last = cls.normalize(last) if last else ""
        norm_full = cls.normalize(full_name)

        # Exact match: "john doe" in "john doe"
        if norm_first and norm_last:
            full_constructed = f"{norm_first} {norm_last}"
            if full_constructed in norm_full or norm_full.startswith(full_constructed):
                return True, "exact"

        # Fuzzy match: last name matches
        if norm_last and norm_last in norm_full:
            # Check if first name or initial matches
            if norm_first and (norm_first in norm_full or norm_full.startswith(norm_first[0])):
                return True, "fuzzy"

        return False, ""


class ParticipantMatcher:
    """Main matching logic"""

    def __init__(self):
        """Initialize MongoDB connections"""
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

        # Statistics
        self.stats = {
            'total_participants': 0,
            'good_matches': 0,
            'fuzzy_matches': 0,
            'no_matches': 0,
            'match_methods': {
                'address': 0,
                'phone': 0,
                'name': 0,
                'address_phone': 0,
                'address_name': 0,
            }
        }

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

    def get_county_collections(self) -> List[str]:
        """Get all county demographic collection names"""
        collections = self.db_county.list_collection_names()

        # Filter for demographic collections (pattern: *CountyDemographic)
        demo_collections = [c for c in collections if 'Demographic' in c]

        logger.info(f"Found {len(demo_collections)} county demographic collections")
        return demo_collections

    def match_participant(self, participant: Dict) -> MatchResult:
        """
        Match a single participant to county data

        Tries matching in order:
        1. Address + Phone (best)
        2. Address only
        3. Phone only
        4. Name + Address
        """
        p_id = str(participant.get('_id', 'unknown'))
        fields = participant.get('fields', {})

        p_address = fields.get('Address', '')
        p_phone = fields.get('Cell', '')
        p_first = fields.get('FirstName', '')
        p_last = fields.get('LastName', '')
        p_zip = fields.get('ZIP', '')

        # Get all county collections to search
        collections = self.get_county_collections()

        best_match = None
        best_score = 0.0

        for collection_name in collections:
            collection = self.db_county[collection_name]

            # Strategy 1: Address + Phone (GOOD match)
            if p_address and p_phone:
                match = self._match_address_phone(collection, p_address, p_phone, p_zip)
                if match and match.match_quality == MatchQuality.GOOD:
                    return match
                if match and match.match_score > best_score:
                    best_match = match
                    best_score = match.match_score

            # Strategy 2: Address only (FUZZY match)
            if p_address:
                match = self._match_address(collection, p_address, p_zip)
                if match and match.match_score > best_score:
                    best_match = match
                    best_score = match.match_score

            # Strategy 3: Phone only (GOOD match if found)
            if p_phone:
                match = self._match_phone(collection, p_phone)
                if match and match.match_quality == MatchQuality.GOOD:
                    return match

            # Strategy 4: Name + Address (FUZZY match)
            if p_first and p_last and p_address:
                match = self._match_name_address(collection, p_first, p_last, p_address, p_zip)
                if match and match.match_score > best_score:
                    best_match = match
                    best_score = match.match_score

        # Return best match or no match
        if best_match:
            return best_match

        return MatchResult(
            participant_id=p_id,
            match_quality=MatchQuality.NO_MATCH
        )

    def _match_address_phone(self, collection, address: str, phone: str, zip_code: str) -> Optional[MatchResult]:
        """Match by both address and phone (highest confidence)"""
        norm_addr = AddressNormalizer.normalize(address)
        norm_phone = PhoneNormalizer.normalize(phone)

        if not norm_addr or not norm_phone:
            return None

        # Search county data
        for record in collection.find():
            county_addr = record.get('address', '')
            county_phone = str(record.get('mobile', ''))

            addr_match = AddressNormalizer.exact_match(address, county_addr)
            phone_match = PhoneNormalizer.match(phone, county_phone)

            if addr_match and phone_match:
                self.stats['match_methods']['address_phone'] += 1
                return MatchResult(
                    participant_id="",
                    match_quality=MatchQuality.GOOD,
                    county_record=record,
                    match_method='address_phone',
                    match_score=1.0
                )

        return None

    def _match_address(self, collection, address: str, zip_code: str) -> Optional[MatchResult]:
        """Match by address only"""
        # Build query with ZIP filter if available
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

            # Address must match (at least fuzzy)
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
                    match_quality=quality,
                    county_record=record,
                    match_method='address_name',
                    match_score=score
                )

        return None

    def run_matching(self) -> List[MatchResult]:
        """Run matching process for all engaged participants"""
        logger.info("Starting participant matching process...")

        participants = self.get_engaged_participants()
        results = []

        for i, participant in enumerate(participants, 1):
            if i % 100 == 0:
                logger.info(f"Processing participant {i}/{len(participants)}...")

            result = self.match_participant(participant)
            result.participant_id = str(participant.get('_id'))
            results.append(result)

            # Update statistics
            if result.match_quality == MatchQuality.GOOD:
                self.stats['good_matches'] += 1
            elif result.match_quality == MatchQuality.FUZZY:
                self.stats['fuzzy_matches'] += 1
            else:
                self.stats['no_matches'] += 1

        return results

    def print_statistics(self):
        """Print matching statistics"""
        print("\n" + "="*60)
        print("MATCHING STATISTICS")
        print("="*60)
        print(f"Total Participants: {self.stats['total_participants']}")
        print(f"Good Matches:       {self.stats['good_matches']} ({self._pct('good_matches')}%)")
        print(f"Fuzzy Matches:      {self.stats['fuzzy_matches']} ({self._pct('fuzzy_matches')}%)")
        print(f"No Matches:         {self.stats['no_matches']} ({self._pct('no_matches')}%)")
        print("\nMatch Methods:")
        for method, count in self.stats['match_methods'].items():
            if count > 0:
                print(f"  {method:20s}: {count}")
        print("="*60 + "\n")

    def _pct(self, key: str) -> str:
        """Calculate percentage for statistics"""
        total = self.stats['total_participants']
        if total == 0:
            return "0.0"
        return f"{(self.stats[key] / total * 100):.1f}"

    def close(self):
        """Close database connections"""
        self.client_participants.close()
        self.client_county.close()


def main():
    """Main execution"""
    matcher = ParticipantMatcher()

    try:
        # Run matching
        results = matcher.run_matching()

        # Print statistics
        matcher.print_statistics()

        # TODO: Next step - generate CSV output with combined data
        logger.info(f"Matching complete. {len(results)} results ready for CSV export.")

    except Exception as e:
        logger.error(f"Error during matching: {e}", exc_info=True)
        return 1
    finally:
        matcher.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
