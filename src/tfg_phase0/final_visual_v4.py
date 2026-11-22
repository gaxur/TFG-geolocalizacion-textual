"""Puente offline al runner V4 existente: preparar y verificar evidencia, sin GPU."""

import json
import re
from hashlib import sha256

from .final_visual_ranking import CONTRACT, MODEL, digest
from .mapillary_visual_pilot import reject_ground_truth
from .visual_reranking import aggregate_candidate_evidence, compile_atomic_claims_v2, parse_verdict_only
from .visual_verifier import SUPPORTED_LOCAL_MODELS


def prepare_v4(context, associations):
    """Las asociaciones proceden de un inventario Mapillary autorizado y revisado con OSM."""
    reject_ground_truth(associations)
    request = context['request']
    rows = [dict(row, orientation_comparable=False) for row in associations
            if row['candidate_id'] in request['candidate_ids']]
    if (any(row.get('provider') != 'mapillary' or not _sha(row.get('image_sha256')) for row in rows)
            or len({(r['candidate_id'], r['image_id']) for r in rows}) != len(rows)):
        raise ValueError('solo se admite evidencia Mapillary')
    # El operador revisa cada claim sobre el diálogo antes de ejecutar V4, en
    # especial menciones negadas o palabras que aparezcan solo en la pregunta.
    fixture = {'request': request, 'claims': compile_atomic_claims_v2(context['description']), 'associations': rows,
               'geometry_source_sha256': context.get('geometry_source_sha256'), 'geometries': context.get('geometries', {})}
    reject_ground_truth(fixture)
    return dict(fixture, fixture_id='final-visual-v4-' + digest(fixture))


def associations_from_d112(selection):
    """Recupera solo las parejas aceptadas por el selector geométrico existente."""
    reject_ground_truth(selection)
    if (selection.get('contract_version') != 'mapillary-evidence-selector-v2-result-v1'
            or selection['protocol']['ground_truth_used'] is not False
            or selection['selector_run_id'] != 'mapillary-selector-v2-sha256-' + digest({
                k: v for k, v in selection.items() if k != 'selector_run_id'})):
        raise ValueError('selección OSM/Mapillary incompatible')
    rows = []
    for candidate in selection['records']:
        if candidate['status'] != 'selected':
            continue
        primary = candidate['primary']
        accepted = next(row for row in candidate['considered'] if row['image_id'] == primary['image_id']
                        and row['image_sha256'] == primary['image_sha256'] and row['eligible'])
        rows.append(dict(provider='mapillary', candidate_id=candidate['candidate_id'],
                         image_id=primary['image_id'], image_sha256=primary['image_sha256'],
                         geometry=accepted['geometry'], selection_id=selection['selector_run_id']))
    return rows


def evidence_from_v4(context, *, fixture_path, assets_path, review_path, run_path):
    def load(path):
        raw = path.read_bytes()
        value = json.loads(raw)
        reject_ground_truth(value)
        return value, sha256(raw).hexdigest()

    fixture, fixture_sha = load(fixture_path)
    assets, assets_sha = load(assets_path)
    review, review_sha = load(review_path)
    run, run_sha = load(run_path)
    if (fixture != prepare_v4(context, fixture['associations']) or run['fixture_id'] != fixture['fixture_id']
            or run['contract_version'] != 'visual-fixture-run-v4'
            or run['inputs'] != dict(fixture_sha256=fixture_sha, asset_manifest_sha256=assets_sha, reviewed_claims_sha256=review_sha)
            or {key: run['model'].get(key) for key in MODEL} != MODEL
            or sorted(r['sha256'] for r in run['model']['files'].values()) !=
                sorted(SUPPORTED_LOCAL_MODELS['qwen3-vl-8b']['weight_sha256'])
            or run['generation']['contract'] != 'verdict_only_v4' or run['generation']['do_sample'] is not False
            or any(run['protocol'].get(key) is not False for key in (
                'ground_truth_used', 'baseline_rank_sent_to_vlm', 'scores_sent_to_vlm', 'coordinates_sent_to_vlm', 'reranking_performed'))
            or review['fixture_id'] != fixture['fixture_id'] or review['review_status'] != 'complete'):
        raise ValueError('ejecución V4 incompatible')
    claims = {row['claim_id']: row for row in fixture['claims']['claims']}
    reviewed = {row['claim']['claim_id']: row for row in review['records']}
    if (set(reviewed) != set(claims) or len(reviewed) != len(review['records'])
            or any(row['claim'] != claims[cid] or row['decision'] not in ('approved', 'rejected')
                   for cid, row in reviewed.items())):
        raise ValueError('revisión de claims incompatible')
    approved = {cid: row['claim'] for cid, row in reviewed.items() if row['decision'] == 'approved'}
    if {row['claim_id']: row for row in run['approved_claims']} != approved:
        raise ValueError('claims ejecutados no coinciden con la revisión')
    media = {r['image_id']: r['sha256'] for r in assets['assets'] if r['status'] in ('downloaded', 'reused')}
    associations = {(r['candidate_id'], r['image_id']): r for r in fixture['associations']}
    observations = []
    for row in run['records']:
        association = associations[row['candidate_id'], row['image_id']]
        claim = approved[row['claim_id']]
        if (row['image_sha256'] != media[row['image_id']] or row['image_sha256'] != association['image_sha256']
                or row.get('sequence_id') != association.get('sequence_id')):
            raise ValueError('imagen ejecutada no coincide con el plan')
        if row['status'] == 'valid' and (claim['requires_orientation'] or parse_verdict_only(row['raw_output']) != row['verdict']):
            raise ValueError('veredicto visual no verificable')
        observations.append(dict(candidate_id=row['candidate_id'], image_id=row['image_id'], image_sha256=row['image_sha256'],
                                 sequence_id=row.get('sequence_id'), claim=claim, status=row['status'], verdict=row['verdict']))
    return dict(contract_version=CONTRACT, request=context['request'], model=MODEL, mode='real', observations=observations,
                provenance=dict(run_sha256=run_sha, fixture_sha256=fixture_sha, assets_sha256=assets_sha, review_sha256=review_sha))


def aggregate_observations(evidence, *, description):
    """Solo puntúa observaciones respaldadas por imagen y claim. Sin cobertura ≠ cero visual."""
    provenance = evidence['provenance']
    if evidence['mode'] == 'real' and (set(provenance) != {'run_sha256', 'fixture_sha256', 'assets_sha256', 'review_sha256'}
                                        or any(not _sha(value) for value in provenance.values())):
        raise ValueError('provenance V4 incompleta')
    request = evidence['request']
    ids = set(request['candidate_ids'])
    source_claims = {row['claim_id']: row for row in compile_atomic_claims_v2(description)['claims']}
    claims, associations, verdicts, seen = {}, {}, [], set()
    for row in evidence['observations']:
        if set(row) != {'candidate_id', 'image_id', 'image_sha256', 'sequence_id', 'claim', 'status', 'verdict'}:
            raise ValueError('observación visual incompatible')
        cid, iid, claim = row['candidate_id'], row['image_id'], row['claim']
        aid, key = (cid, iid), (cid, iid, claim['claim_id'])
        if (cid not in ids or not isinstance(iid, str) or not iid or not _sha(row['image_sha256']) or key in seen
                or claim != source_claims.get(claim['claim_id'])
                or row['status'] not in ('valid', 'policy_unverifiable', 'invalid_output')
                or row['status'] == 'valid' and (claim.get('requires_orientation') is not False
                    or row['verdict'] not in ('supported', 'contradicted', 'unverifiable'))):
            raise ValueError('observación ajena, duplicada o no verificable')
        seen.add(key)
        association = {k: row[k] for k in ('candidate_id', 'image_id', 'image_sha256', 'sequence_id')}
        if claims.setdefault(claim['claim_id'], claim) != claim or associations.setdefault(aid, association) != association:
            raise ValueError('claim o imagen divergente')
        verdicts.append(dict(row, claim_id=claim['claim_id']))
    result = {}
    if not verdicts:
        return result
    aggregate = aggregate_candidate_evidence(list(claims.values()), list(associations.values()), verdicts)
    for row in aggregate['candidates']:
        usable = any(claim['state'] in ('supported', 'contradicted') for claim in row['claims'])
        result[row['candidate_id']] = {'visual_score': row['positive_evidence'] if usable else None,
            'abstention': None if usable else 'no_verifiable_observation', 'claims': row['claims']}
    return result


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None
