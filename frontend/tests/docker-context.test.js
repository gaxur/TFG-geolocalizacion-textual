import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

test('el contexto Docker del frontend excluye entorno y credenciales locales', async () => {
  const path = fileURLToPath(new URL('../.dockerignore', import.meta.url));
  const rules = (await readFile(path, 'utf8')).split(/\r?\n/).map(line => line.trim()).filter(Boolean);

  for (const pattern of ['.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx']) {
    assert.ok(rules.includes(pattern), `falta excluir ${pattern} del contexto Docker frontend`);
  }
  assert.ok(!rules.some(line => line.startsWith('!') && /env/i.test(line)), 'no se deben reintroducir archivos de entorno al contexto');
});
