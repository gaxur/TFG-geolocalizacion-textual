import test from 'node:test';
import assert from 'node:assert/strict';
import { adaptFreeTextStage, finalVisualLabel } from '../src/dialogue-freetext.js';

test('MapLibre consume el Top-10 final sin perder el Top-10 posterior al diálogo', () => {
  const results = Array.from({length: 10}, (_, i) => ({candidate_id: `c${i+1}`, rank: i+1,
    latitude: 40.42, longitude: -3.7, cosine_similarity: 0.6}));
  const visual = {contract_version: 'atlas-final-visual-ranking-v1', status: 'applied', mode: 'cpu_fixture',
    depth: 50, source_ranking_sha256: 'fixture', baseline_results: results,
    final_results: [...results.slice(0, 9), {...results[9], candidate_id: 'c12'}]};
  const session = {status: 'completed', final_stage: 'E1', stage_snapshots: [
    {stage: 'E1', gallery_id: 'madrid-50m', candidate_count: 253, ranking_sha256: 'fixture',
      results, visual_postprocessing: visual}]};
  const applied = adaptFreeTextStage(session, 'E1');
  assert.equal(applied.results[9].key, 'madrid-50m:c12');
  assert.equal(applied.baselineResults[9].candidate_id, 'c10');
  assert.match(finalVisualLabel(visual), /fixture CPU/);
  visual.status = 'fallback_baseline';
  visual.final_results = results;
  assert.equal(adaptFreeTextStage(session, 'E1').results[9].id, 'c10');
  visual.source_ranking_sha256 = 'stale';
  assert.throws(() => adaptFreeTextStage(session, 'E1'), /incompatible/);
});
