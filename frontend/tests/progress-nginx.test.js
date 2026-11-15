import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const nginxPath = new URL('../nginx.conf', import.meta.url);

test('Nginx proxies one unbuffered SSE route and allows the synchronous LLM request timeout', async () => {
  const config = await readFile(fileURLToPath(nginxPath), 'utf8');
  const progressLocations = config.match(/location\s+\^~\s+\/api\/v1\/progress\//g) || [];
  const progressBlock = config.match(/location\s+\^~\s+\/api\/v1\/progress\/\s*\{([\s\S]*?)\n\s*\}/)?.[1] || '';
  const apiBlock = config.match(/location\s+\/api\/\s*\{([\s\S]*?)\n\s*\}/)?.[1] || '';

  assert.equal(progressLocations.length, 1, 'la ruta SSE no debe estar duplicada');
  assert.match(progressBlock, /proxy_buffering\s+off;/);
  assert.match(progressBlock, /proxy_cache\s+off;/);
  assert.match(progressBlock, /proxy_read_timeout\s+900s;/);
  assert.match(progressBlock, /proxy_http_version\s+1\.1;/);
  assert.match(progressBlock, /proxy_set_header\s+Connection\s+"";/);
  assert.match(apiBlock, /proxy_read_timeout\s+120s;/);
});
