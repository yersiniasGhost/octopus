"""Analysis document ids: readable surrogate meter ids are hashed so analysis docs carry no address or account.

Unlinked ElectricalDB meters use a readable surrogate _id ('{utility}:{opco}:{account}' or '...:{zip5}|{ADDRESS}').
Linked meters have opaque ids (ObjectId or 32-hex string), which stay unchanged and remain the pointer back to the
source meter. Hashing is a keyed HMAC and deterministic, so a rebuild with the same key merges onto the same
documents; rotating ANALYSIS_ID_KEY re-keys every surrogate household.

Surrogate hashes are county-scoped: each county's ElectricalDB is its own collection, so a surrogate id is unique only
within its county (e.g. 'FE:OE:ALL' recurs in many counties as different meters), while analysis_households is one
statewide collection. The HMAC covers '{county}\\x1f{source_id}'. A reverse lookup recomputes the HMAC over that
county's surrogate ids.
"""

import hashlib
import hmac
from typing import Any

from src.utils.envvars import EnvVars


def is_surrogate(source_id: Any) -> bool:
    return isinstance(source_id, str) and (':' in source_id or '|' in source_id)


def analysis_id(source_id: Any, key: bytes, county: str) -> Any:
    """Surrogate ids become 'h' + 32 hex of HMAC-SHA256 over county + id; opaque ids pass through unchanged."""
    if not is_surrogate(source_id):
        return source_id
    return 'h' + hmac.new(key, f'{county}\x1f{source_id}'.encode(), hashlib.sha256).hexdigest()[:32]


def load_id_key() -> bytes:
    """The HMAC key from ANALYSIS_ID_KEY. Never falls back to raw ids."""
    value = EnvVars().get_env('ANALYSIS_ID_KEY')
    if not value or not value.strip():
        raise RuntimeError('ANALYSIS_ID_KEY is not set; refusing to build analysis documents with readable ids')
    return value.strip().encode()
