"""Reranking de una reserva CT2L inmutable, con o sin diálogo; no carga modelos."""

from hashlib import sha256

from .mapillary_visual_pilot import reject_ground_truth
from .visual_reranking import canonical_bytes, rerank_experimental
from .visual_verifier import SUPPORTED_LOCAL_MODELS

MODEL = {key: SUPPORTED_LOCAL_MODELS['qwen3-vl-8b'][key] for key in ('model_id', 'revision')}
DEPTHS = (10, 50, 100)
CONTRACT = 'atlas-final-visual-evidence-v1'


def digest(value):
    return sha256(canonical_bytes(value)).hexdigest()


def visual_request(*, ranking, description, depth=50):
    reject_ground_truth(ranking)
    if ranking.get('ground_truth_used', False) is not False or depth not in DEPTHS:
        raise ValueError('ranking o profundidad visual incompatible')
    rows = ranking['results']
    if (not rows or any(row['rank'] != i for i, row in enumerate(rows, 1))
            or len({row['candidate_id'] for row in rows}) != len(rows)):
        raise ValueError('orden o candidatos CT2L inválidos')
    return {'ranking_sha256': digest(ranking), 'description_sha256': sha256(description.encode()).hexdigest(),
            'depth': depth, 'candidate_ids': [r['candidate_id'] for r in rows[:depth]]}


def final_visual_ranking(*, ranking, description, depth=50, evidence=None, mode):
    request = visual_request(ranking=ranking, description=description, depth=depth)
    reserve = ranking['results']
    selected = reserve[:depth]
    scores = {}
    if evidence is not None:
        reject_ground_truth(evidence)
        if (set(evidence) != {'contract_version', 'request', 'model', 'mode', 'observations', 'provenance'}
                or evidence['contract_version'] != CONTRACT or evidence['request'] != request
                or evidence['model'] != MODEL or evidence['mode'] != mode):
            raise ValueError('evidencia visual no vinculada al ranking final')
        from .final_visual_v4 import aggregate_observations
        scores = aggregate_observations(evidence, description=description)

    applied = any(row['visual_score'] is not None and row['visual_score'] > 0 for row in scores.values())
    combined = list(reserve)
    if applied:
        aggregate = {'candidates': [{'candidate_id': cid, 'positive_evidence': row['visual_score'], 'negative_evidence': 0.0}
                                    for cid, row in scores.items() if row['visual_score'] is not None]}
        ranking_rows = rerank_experimental({'results': selected}, aggregate, enabled=True, lambda_pos=0.1)['results']
        by_id = {r['candidate_id']: r for r in selected}
        combined[:len(selected)] = [dict(by_id[r['candidate_id']], rank=r['experimental_rank'],
                                          combined_score=r['experimental_score']) for r in ranking_rows]
    return {'contract_version': 'atlas-final-visual-ranking-v1', 'request': request, 'mode': mode,
            'status': 'applied' if applied else 'fallback_baseline',
            'reason': None if applied else 'no_positive_visual_support' if evidence is not None else 'no_visual_result',
            'model': MODEL if evidence is not None else None, 'positive_weight': 0.1,
            'baseline_results': reserve[:10], 'combined_ranking': combined, 'final_results': combined[:10],
            'evidence': [{'candidate_id': cid, **scores.get(cid, {'visual_score': None,
                         'abstention': 'no_mapillary_evidence' if evidence is not None else 'visual_not_executed'})}
                         for cid in request['candidate_ids']]}
