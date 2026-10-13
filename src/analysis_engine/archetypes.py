"""Program archetypes (rules.json) -> MongoDB filters, compiled at query time so tuning needs no rebuild.

Every count is reported against its known-enough denominator: the households for which all of the
archetype's inputs are known (spec §6).
"""

from typing import Dict, Tuple

OPS = {'>=': '$gte', '<=': '$lte', '==': '$eq', '!=': '$ne'}


def _known_dim_count(minimum: int) -> Dict:
    known = {'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}
    return {'$expr': {'$gte': [known, minimum]}}


def compile_archetype(name: str, rules: Dict) -> Tuple[Dict, Dict]:
    """(match, known) filters for one archetype; known == {} means every household is a valid denominator."""
    spec, dims = rules['archetypes'][name], rules['dims']
    if spec.get('kind') == 'no_known_need':
        known = _known_dim_count(spec['min_known'])
        return {'$and': [known, {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, known
    match, known = [], []
    for clause in spec['all']:
        if 'dim' in clause:
            path = f"dims.{dims.index(clause['dim'])}"
            match.append({path: {OPS[clause['op']]: clause['value']}})
            known.append({path: {'$gte': 0}})
        else:
            match.append({clause['field']: {OPS[clause['op']]: clause['value']}})
            if not clause.get('unknown_ok'):
                known.append({clause['field']: {'$exists': True}})
    return {'$and': match}, ({'$and': known} if known else {})
