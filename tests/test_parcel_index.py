"""ParcelIndex -- the dual parcel_key / parcel_id lookup, shared by the thermal tools and the analysis engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.parcel_id import ParcelIndex, parcel_id_of, parcel_key_of  # noqa: E402


def test_identity_helpers_normalize_and_treat_blank_as_absent():
    assert parcel_key_of({'parcel_key': ' 10-088712-00 '}) == '10-088712-00'
    assert parcel_id_of({'parcel_id': 30324005}) == '30324005'
    assert parcel_key_of({'parcel_key': ''}) is None
    assert parcel_id_of({}) is None


def test_resolve_prefers_parcel_key_then_parcel_id():
    index = ParcelIndex()
    index.add({'parcel_key': 'K1', 'parcel_id': 'I1'}, 'by-key-doc')
    index.add({'parcel_id': 123}, 'by-id-doc')
    assert index.resolve({'parcel_key': 'K1', 'parcel_id': 'zzz'}) == ('by-key-doc', 'parcel_key')
    assert index.resolve({'parcel_key': 'nope', 'parcel_id': '123'}) == ('by-id-doc', 'parcel_id')
    assert index.resolve({'parcel_id': 'I1'}) == ('by-key-doc', 'parcel_id')
    assert index.resolve({'parcel_id': None}) == (None, 'unmatched')


def test_first_value_added_wins():
    index = ParcelIndex()
    index.add({'parcel_key': 'K1'}, 'first')
    index.add({'parcel_key': 'K1'}, 'second')
    assert index.resolve({'parcel_key': 'K1'})[0] == 'first'
