"""In-memory stand-ins for the two collections the thermal tools join.

Filters are deliberately ignored. The server-side filters in get_missing_parcels
and get_target_parcels are performance optimisations; the in-Python guards are
what make the result correct, and these fakes exercise those guards rather than
re-implementing MongoDB semantics.
"""


class FakeCollection:
    """Returns every document regardless of filter."""

    def __init__(self, docs):
        self._docs = docs

    def find(self, _filter=None, _projection=None):
        return iter(self._docs)

    def count_documents(self, _filter=None):
        return len(self._docs)


class FakeDB:
    """A single county pair, named Testville unless told otherwise."""

    def __init__(self, electrical, thermal, county='Testville'):
        self._cols = {
            f'{county}ElectricalDB': FakeCollection(electrical),
            f'{county}ThermalLoads': FakeCollection(thermal),
        }

    def __getitem__(self, name):
        return self._cols[name]
