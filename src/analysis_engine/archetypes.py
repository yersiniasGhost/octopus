"""Program archetypes (rules.json) -> MongoDB filters, compiled at query time so tuning needs no rebuild.

Every count is reported against its known-enough denominator: the households for which all of the
archetype's inputs are known (spec §6).
"""

from typing import Dict, Tuple

NOT_NONRES = {'nonres': {'$ne': True}}
OPS = {'>=': '$gte', '<=': '$lte', '==': '$eq', '!=': '$ne'}


def _known_dim_count(minimum: int) -> Dict:
    known = {'$size': {'$filter': {'input': '$dims', 'cond': {'$gte': ['$$this', 0]}}}}
    return {'$expr': {'$gte': [known, minimum]}}


def compile_archetype(name: str, rules: Dict) -> Tuple[Dict, Dict]:
    """(match, known) filters for one archetype; every denominator excludes non-residential households."""
    spec, dims = rules['archetypes'][name], rules['dims']
    if spec.get('kind') == 'no_known_need':
        known = _known_dim_count(spec['min_known'])
        known = {'$and': [known, NOT_NONRES]}
        return {'$and': [*known['$and'], {'dims': {'$not': {'$elemMatch': {'$gte': 1}}}}]}, known
    match, known = [NOT_NONRES], [NOT_NONRES]
    for clause in spec['all']:
        if 'dim' in clause:
            path = f"dims.{dims.index(clause['dim'])}"
            match.append({path: {OPS[clause['op']]: clause['value']}})
            known.append({path: {'$gte': 0}})
        else:
            match_clause = {OPS[clause['op']]: clause['value']}
            if not clause.get('unknown_ok'):
                match_clause['$exists'] = True
                known.append({clause['field']: {'$exists': True}})
            match.append({clause['field']: match_clause})
    return {'$and': match}, {'$and': known}


def proxy_mask(name: str, rules: Dict) -> int:
    """Bitmask of the dimensions an archetype reads (same bit positions as a household's proxy field)."""
    return sum(1 << rules['dims'].index(c['dim']) for c in rules['archetypes'][name].get('all', []) if 'dim' in c)
