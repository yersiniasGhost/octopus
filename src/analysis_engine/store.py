"""Where a county build lands: staging, then a swap into analysis_households.

The swap merges staging into the live collection and then deletes the county's live documents that staging no
longer holds. A build that fails before the swap leaves the previous version live (spec §10).
"""

from collections import Counter
from typing import Dict, List

HOUSEHOLDS, BUILDS = 'analysis_households', 'analysis_builds'
_DELETE_BATCH = 10000


def staging_name(county: str) -> str:
    return f'{HOUSEHOLDS}_staging_{county}'


class MongoStore:
    def __init__(self, db):
        self.db = db

    def ensure_indexes(self, dim_count: int) -> None:
        households = self.db[HOUSEHOLDS]
        for keys in ([('county', 1)], [('parcel_key', 1)], [('link', 1)],
                     *([('county', 1), (f'dims.{i}', 1)] for i in range(dim_count))):
            households.create_index(keys)

    def reset_staging(self, county: str) -> None:
        self.db[staging_name(county)].drop()

    def stage(self, county: str, docs: List[Dict]) -> None:
        self.db[staging_name(county)].insert_many(docs, ordered=False)

    def _cross_county_collisions(self, county: str) -> int:
        """Staged _ids already held by another county; a merge would silently move them."""
        pipeline = [{'$lookup': {'from': HOUSEHOLDS, 'localField': '_id', 'foreignField': '_id', 'as': 'live'}},
                    {'$match': {'live.county': {'$exists': True, '$ne': county}}}, {'$count': 'n'}]
        result = list(self.db[staging_name(county)].aggregate(pipeline, allowDiskUse=True))
        return result[0]['n'] if result else 0

    def swap(self, county: str) -> None:
        staging = staging_name(county)
        collisions = self._cross_county_collisions(county)
        if collisions:
            raise RuntimeError(f'{collisions} staged _id(s) already belong to another county')
        self.db[staging].aggregate([{'$merge': {'into': HOUSEHOLDS, 'on': '_id', 'whenMatched': 'replace',
                                                'whenNotMatched': 'insert'}}], allowDiskUse=True)
        stale = [d['_id'] for d in self.db[HOUSEHOLDS].aggregate([
            {'$match': {'county': county}},
            {'$lookup': {'from': staging, 'localField': '_id', 'foreignField': '_id', 'as': 'fresh'}},
            {'$match': {'fresh': {'$size': 0}}}, {'$project': {'_id': 1}}], allowDiskUse=True)]
        for start in range(0, len(stale), _DELETE_BATCH):
            self.db[HOUSEHOLDS].delete_many({'_id': {'$in': stale[start:start + _DELETE_BATCH]}})
        self.db[staging].drop()

    def discard_staging(self, county: str) -> None:
        self.db[staging_name(county)].drop()

    def record_build(self, build: Dict) -> None:
        self.db[BUILDS].insert_one(dict(build))


class DryRunStore:
    """Counts what a build would write and writes nothing."""

    def __init__(self):
        self.staged, self.builds = Counter(), []

    def reset_staging(self, county: str) -> None:
        self.staged[county] = 0

    def stage(self, county: str, docs: List[Dict]) -> None:
        self.staged[county] += len(docs)

    def swap(self, county: str) -> None:
        pass

    def discard_staging(self, county: str) -> None:
        self.staged.pop(county, None)

    def record_build(self, build: Dict) -> None:
        self.builds.append(build)
