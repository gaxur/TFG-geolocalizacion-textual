import test from 'node:test';
import assert from 'node:assert/strict';
import { simulateSearch, extractClues, examples } from '../src/demo.js';

test('la región restringe candidatos y se respeta Top-K', () => {
  const results = simulateSearch(examples[0].text, 'centro', 'cross', 3);
  assert.equal(results.length, 3);
  assert.ok(results.every(p => p.region === 'centro'));
  assert.equal(simulateSearch('Veo una plaza', 'chamberi', 'gotpr', 5).length, 1);
});
test('no se fabrican coincidencias para consultas fuera de los escenarios', () => {
  assert.deepEqual(simulateSearch('Estoy viendo una montaña nevada', 'centro', 'cross'), []);
});
test('cada ejemplo prioriza el escenario correspondiente', () => {
  for (const [index, expected] of ['sol', 'mayor', 'retiro'].entries()) {
    const sample = examples[index];
    assert.equal(simulateSearch(sample.text, sample.region, 'cross')[0].id, expected);
  }
});
test('las dos variantes producen puntuaciones distintas manteniendo el ámbito', () => {
  const cross = simulateSearch('Veo una plaza', 'centro', 'cross', 5);
  const graph = simulateSearch('Veo una plaza', 'centro', 'gotpr', 5);
  assert.deepEqual(cross.map(p => p.id).sort(), graph.map(p => p.id).sort());
  assert.notEqual(cross[0].id, graph[0].id);
});
test('la extracción de pistas mantiene explícita la orientación desconocida', () => {
  const clues = extractClues('Una PLAZA y una torre a mi derecha');
  assert.ok(clues.includes('Plaza'));
  assert.ok(clues.includes('A la derecha · orientación pendiente'));
});
