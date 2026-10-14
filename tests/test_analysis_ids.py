"""Surrogate meter ids are hashed; opaque ids pass through; the key must be configured."""

import sys
from pathlib import Path

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_engine import ids  # noqa: E402
from src.analysis_engine.ids import analysis_id, is_surrogate, load_id_key  # noqa: E402

ADDRESS, ACCOUNT, KEY = 'AEP:CSP:43002|1 MAIN ST', 'AEP:CSP:123456789', b'test-key'


def test_opaque_ids_are_unchanged():
    oid, hex32 = ObjectId(), 'a' * 32
    assert analysis_id(oid, KEY, 'Franklin') is oid and analysis_id(hex32, KEY, 'Adams') == hex32
    assert not is_surrogate(oid) and not is_surrogate(hex32)


@pytest.mark.parametrize('source', [ADDRESS, ACCOUNT])
def test_surrogates_hash_deterministically_without_separators(source):
    hashed = analysis_id(source, KEY, 'Franklin')
    assert is_surrogate(source) and hashed == analysis_id(source, KEY, 'Franklin')
    assert hashed[0] == 'h' and len(hashed) == 33 and int(hashed[1:], 16) >= 0
    assert ':' not in hashed and '|' not in hashed and not is_surrogate(hashed)
    assert hashed != analysis_id(source, b'other-key', 'Franklin')


def test_same_surrogate_in_two_counties_gets_different_ids():
    a, b = analysis_id('FE:OE:ALL', KEY, 'Adams'), analysis_id('FE:OE:ALL', KEY, 'Allen')
    assert a != b and a == analysis_id('FE:OE:ALL', KEY, 'Adams')
    for h in (a, b):
        assert h[0] == 'h' and len(h) == 33 and int(h[1:], 16) >= 0


def test_opaque_id_is_unchanged_regardless_of_county():
    hex32 = 'b' * 32
    assert analysis_id(hex32, KEY, 'Adams') == analysis_id(hex32, KEY, 'Allen') == hex32


def test_load_id_key_reads_env_and_refuses_when_unset(monkeypatch):
    env = ids.EnvVars()
    monkeypatch.setattr(env, 'get_env', lambda name, default=None: '  s3cret ')
    assert load_id_key() == b's3cret'
    for blank in (None, '', '   '):
        monkeypatch.setattr(env, 'get_env', lambda name, default=None, v=blank: v)
        with pytest.raises(RuntimeError, match='ANALYSIS_ID_KEY is not set'):
            load_id_key()
