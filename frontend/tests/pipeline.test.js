import test from 'node:test';
import assert from 'node:assert/strict';
import {
  cancelPipeline,
  completePipelineFromResponse,
  createPipelineState,
  failPipeline,
  markProgressUnavailable,
  reducePipelineEvent,
} from '../src/pipeline.js';
import { openProgressStream } from '../src/progress-stream.js';

const capabilities = {
  retrievers: [{ id: 'crosstext2loc', available: true }],
  processing_modes: [{ id: 'no_llm', available: true }, { id: 'with_llm', available: true }],
  postprocessing_capabilities: [{ id: 'topn_visual_promotion', available: false, enabled: false }],
  pipeline_progress: {
    stages: [
      { id: 'llm', available: true },
      { id: 'crosstext2loc', available: true },
      { id: 'vlm', available: false },
      { id: 'dialoguevpr', available: false, reason: 'not_integrated_in_mvp_endpoint' },
    ],
  },
};

function event(sequence, stageId, state, extra = {}) {
  return {
    schema_version: '1.0', event_type: stageId === 'pipeline' ? 'pipeline' : 'stage',
    query_id: 'q-current', sequence, stage_id: stageId, state,
    message: `${stageId}:${state}`, ...extra,
  };
}

test('pipeline inicial distingue LLM omitido, CT2L pendiente y módulos no activos', () => {
  const state = createPipelineState({ queryId: 'q-current', processingMode: 'no_llm', capabilities, startedAt: 10 });
  assert.deepEqual(state.stages.map(stage => [stage.id, stage.state]), [
    ['llm', 'skipped'], ['crosstext2loc', 'pending'], ['vlm', 'skipped'], ['dialoguevpr', 'unavailable'],
  ]);
  assert.equal(Object.hasOwn(state, 'percent'), false);
});

test('consume solo eventos del request actual, preserva secuencia y actualiza subfases reales', () => {
  let state = createPipelineState({ queryId: 'q-current', processingMode: 'with_llm', capabilities, startedAt: 10 });
  state = reducePipelineEvent(state, event(1, 'pipeline', 'running'));
  state = reducePipelineEvent(state, event(2, 'llm', 'running'));
  const stale = reducePipelineEvent(state, { ...event(3, 'llm', 'completed'), query_id: 'q-previous' });
  assert.equal(stale, state);
  state = reducePipelineEvent(state, event(3, 'llm', 'completed', { elapsed_ms: 4.2 }));
  state = reducePipelineEvent(state, event(4, 'crosstext2loc', 'running', {
    subphase: { id: 'text_encoding', state: 'running' },
  }));
  const ct2l = state.stages.find(stage => stage.id === 'crosstext2loc');
  assert.equal(ct2l.state, 'running');
  assert.equal(ct2l.subphase.id, 'text_encoding');
  assert.equal(state.stages.find(stage => stage.id === 'llm').elapsedMs, 4.2);
  assert.equal(state.transportGap, false);
});

test('ignora eventos repetidos o fuera de orden y advierte si faltan secuencias', () => {
  let state = createPipelineState({ queryId: 'q-current', processingMode: 'with_llm', capabilities, startedAt: 10 });
  state = reducePipelineEvent(state, event(1, 'pipeline', 'running'));
  state = reducePipelineEvent(state, event(3, 'llm', 'completed'));
  const completed = state;
  assert.equal(state.transportGap, true);
  assert.match(state.message, /Faltan eventos/);
  assert.equal(reducePipelineEvent(state, event(2, 'llm', 'running')), state);
  state = reducePipelineEvent(state, event(4, 'pipeline', 'completed'));
  assert.equal(reducePipelineEvent(state, event(5, 'llm', 'running')), state, 'un evento tardío no reabre un pipeline terminal');
  assert.notEqual(state, completed);
});

test('unavailable SSE no simula hitos; el resultado final confirma solo etapas ejecutadas', () => {
  let state = createPipelineState({ queryId: 'q-current', processingMode: 'with_llm', capabilities, startedAt: 10 });
  state = markProgressUnavailable(state);
  assert.equal(state.stages.find(stage => stage.id === 'llm').state, 'unknown');
  assert.equal(state.stages.find(stage => stage.id === 'crosstext2loc').state, 'unknown');
  state = completePipelineFromResponse(state, {
    processing: { mode: 'with_llm', transformer: { model_id: 'Qwen/Qwen3-8B' } },
    retrievals: [{ gallery_count: 253, effective_k: 10, results: [{ rank: 1 }] }],
    timingsMs: { transformation: 1200, text_encoding: 35, ranking_by_gallery: { 'madrid-50m': 7 } },
    visualPostprocessing: { status: 'disabled' },
  });
  assert.equal(state.overall, 'completed');
  assert.equal(state.stages.find(stage => stage.id === 'llm').state, 'completed');
  assert.equal(state.stages.find(stage => stage.id === 'crosstext2loc').state, 'completed');
  assert.equal(state.stages.find(stage => stage.id === 'vlm').state, 'skipped');
  assert.equal(state.stages.find(stage => stage.id === 'dialoguevpr').state, 'unavailable');
});

test('visual precompute fallback is completed with fallback outcome, not a live VLM claim', () => {
  const state = completePipelineFromResponse(
    createPipelineState({ queryId: 'q-current', processingMode: 'no_llm', capabilities, startedAt: 10 }),
    {
      processing: { mode: 'no_llm', transformer: null },
      retrievals: [{ gallery_count: 253, effective_k: 10, results: [{ rank: 1 }] }],
      timingsMs: { transformation: 0, text_encoding: 35, ranking_by_gallery: { 'madrid-50m': 7 } },
      visualPostprocessing: { status: 'fallback_baseline' },
    },
  );
  const visual = state.stages.find(stage => stage.id === 'vlm');
  assert.equal(visual.state, 'completed');
  assert.equal(visual.outcome, 'fallback_baseline');
  assert.match(visual.message, /precal|compatible|baseline/i);
});

test('una promoción habilitada se presenta como experimental y basada en evidencia precalculada', () => {
  const visualCapabilities = {
    ...capabilities,
    postprocessing_capabilities: [{
      id: 'topn_visual_promotion', available: true, enabled: true,
      experimental: true, source: 'precomputed_qwen3_vl', online_inference: false,
    }],
  };
  const initial = createPipelineState({ queryId: 'q-current', processingMode: 'no_llm', capabilities: visualCapabilities, startedAt: 10 });
  const pending = initial.stages.find(stage => stage.id === 'vlm');
  assert.equal(pending.state, 'pending');
  assert.match(pending.message, /experimental/i);
  assert.match(pending.message, /precalculada/i);
  const completed = completePipelineFromResponse(initial, {
    processing: { mode: 'no_llm', transformer: null },
    retrievals: [{ gallery_count: 253, effective_k: 10, results: [{ rank: 1 }] }],
    timingsMs: { transformation: 0, text_encoding: 5, ranking_by_gallery: { 'madrid-50m': 2 } },
    visualPostprocessing: { status: 'applied' },
  });
  const visual = completed.stages.find(stage => stage.id === 'vlm');
  assert.equal(visual.state, 'completed');
  assert.match(visual.message, /no se ejecutó Qwen3-VL en línea/i);
});

test('timeouts leave unobserved stages unknown and cancel describes client wait only', () => {
  const initial = createPipelineState({ queryId: 'q-current', processingMode: 'no_llm', capabilities, startedAt: 10 });
  const timedOut = failPipeline(initial, { code: 'TIMEOUT', message: 'Timeout' });
  assert.equal(timedOut.overall, 'unknown');
  assert.equal(timedOut.stages.find(stage => stage.id === 'crosstext2loc').state, 'unknown');
  assert.match(cancelPipeline(timedOut).message, /no confirma la detención del trabajo en el servidor/);
});

test('errores contractuales confirman solo las etapas que el backend garantiza', () => {
  const initial = createPipelineState({ queryId: 'q-current', processingMode: 'with_llm', capabilities, startedAt: 10 });
  const rejected = failPipeline(initial, { code: 'TRANSFORMATION_REJECTED', message: 'Rechazada' });
  assert.deepEqual(rejected.stages.map(stage => [stage.id, stage.state]), [
    ['llm', 'failed'], ['crosstext2loc', 'skipped'], ['vlm', 'skipped'], ['dialoguevpr', 'unavailable'],
  ]);

  const unavailable = failPipeline(initial, { code: 'LLM_NOT_READY', message: 'No disponible' });
  assert.deepEqual(unavailable.stages.map(stage => [stage.id, stage.state]), [
    ['llm', 'unavailable'], ['crosstext2loc', 'skipped'], ['vlm', 'skipped'], ['dialoguevpr', 'unavailable'],
  ]);

  const retrievalFailed = failPipeline(initial, { code: 'INFERENCE_FAILED', message: 'CT2L falló' });
  assert.equal(retrievalFailed.stages.find(stage => stage.id === 'crosstext2loc').state, 'failed');
  assert.equal(retrievalFailed.stages.find(stage => stage.id === 'vlm').state, 'skipped');
});

test('representa espera de respuesta sin generar preguntas y aísla consultas nuevas', () => {
  let current = createPipelineState({ queryId: 'q-new', processingMode: 'no_llm', capabilities, startedAt: 10 });
  current = reducePipelineEvent(current, { ...event(1, 'dialoguevpr', 'waiting_for_user'), query_id: 'q-new', message: 'Esperando respuesta real.' });
  assert.equal(current.stages.find(stage => stage.id === 'dialoguevpr').state, 'waiting_for_user');
  assert.equal(current.stages.find(stage => stage.id === 'dialoguevpr').message, 'Esperando respuesta real.');
  assert.equal(reducePipelineEvent(current, { ...event(2, 'dialoguevpr', 'completed'), query_id: 'q-old' }), current);
  const newer = createPipelineState({ queryId: 'q-newer', processingMode: 'no_llm', capabilities, startedAt: 20 });
  assert.equal(reducePipelineEvent(newer, event(2, 'crosstext2loc', 'completed')), newer);
});

test('ausencia de eventos mantiene incertidumbre hasta que la respuesta síncrona confirma el Top-10', () => {
  const legacyCapabilities = { ...capabilities };
  delete legacyCapabilities.pipeline_progress;
  let state = createPipelineState({ queryId: 'q-current', processingMode: 'no_llm', capabilities: legacyCapabilities, startedAt: 10 });
  state = markProgressUnavailable(state, 'No se recibieron eventos SSE.');
  assert.equal(state.transport, 'unavailable');
  assert.equal(state.stages.find(stage => stage.id === 'crosstext2loc').state, 'unknown');
  state = completePipelineFromResponse(state, {
    processing: { mode: 'no_llm', transformer: null },
    retrievals: [{ gallery_count: 253, effective_k: 10, results: Array.from({ length: 10 }, (_, index) => ({ rank: index + 1 })) }],
    timingsMs: { transformation: 0, text_encoding: 12, ranking_by_gallery: { 'madrid-50m': 5 } },
    visualPostprocessing: { status: 'disabled' },
  });
  assert.equal(state.stages.find(stage => stage.id === 'crosstext2loc').state, 'completed');
  assert.equal(state.stages.find(stage => stage.id === 'llm').state, 'skipped');
  assert.equal(state.stages.find(stage => stage.id === 'vlm').state, 'skipped');
  assert.equal(state.overall, 'completed');
  assert.equal(state.transport, 'unavailable');
});

test('SSE transport accepts events and closes without reconnecting after terminal', async () => {
  let source;
  const events = [];
  class FakeEventSource {
    static CLOSED = 2;
    constructor(url) { this.url = url; this.readyState = 1; source = this; }
    close() { this.readyState = FakeEventSource.CLOSED; this.closed = true; }
  }
  const connection = openProgressStream('q/current', {
    EventSourceImpl: FakeEventSource,
    baseUrl: '/api/v1/',
    onEvent: value => events.push(value),
    connectTimeoutMs: 100,
  });
  assert.equal(source.url, '/api/v1/progress/q%2Fcurrent');
  source.onopen();
  assert.equal(await connection.ready, true);
  source.onmessage({ data: JSON.stringify({ event_type: 'connected', query_id: 'q/current', sequence: 0 }) });
  source.onmessage({ data: JSON.stringify({ event_type: 'pipeline', query_id: 'q/current', sequence: 1, stage_id: 'pipeline', state: 'completed' }) });
  assert.equal(events.length, 2);
  assert.equal(source.closed, true);
});
