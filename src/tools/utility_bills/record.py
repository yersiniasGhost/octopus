"""
Common normalized record for one utility account row.

NOTE (decision 2026-08-19): source files also carry kW peak demand (all
utilities), KVAR / on-peak splits (AES), and read-vs-estimated flags (Duke).
These are AVAILABLE in the raw files but intentionally NOT ingested; only
billed kWh per period-end date is stored.
"""
from dataclasses import dataclass, field


@dataclass
class AccountRecord:
    utility: str          # AEP | AES | DUKE | FE
    operating_co: str     # CSP, OPCO, CEI, OE, TE or ''
    account_id: str       # '' when the utility omits account numbers (AEP, Duke)
    customer_name: str
    service_address: str
    city: str
    state: str
    zip5: str
    readings: list = field(default_factory=list)  # [(date 'YYYY-MM-DD', kwh float)]

    def surrogate_key(self) -> str:
        """Deterministic id for accounts that cannot be parcel-matched."""
        tail = self.account_id or f"{self.zip5}|{self.service_address.upper()}"
        return f"{self.utility}:{self.operating_co}:{tail}"
