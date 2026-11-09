import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'vite';

test('Vite sirve PMTiles locales con HTTP Range y no expone archivos fuera de lista', async () => {
  const assetsDirectory = await mkdtemp(path.join(os.tmpdir(), 'atlas-map-assets-'));
  const previousAssetsDirectory = process.env.MVP_MAP_ASSETS_DIR;
  const archiveBytes = Buffer.from('0123456789abcdef');
  await writeFile(path.join(assetsDirectory, 'madrid.pmtiles'), archiveBytes);
  await writeFile(path.join(assetsDirectory, 'map-assets.json'), '{"contract_version":"test"}\n');
  await writeFile(path.join(assetsDirectory, 'madrid.pmtiles.provenance.json'), '{"contract_version":"madrid-osm-vector-cartography-v1"}\n');
  process.env.MVP_MAP_ASSETS_DIR = assetsDirectory;

  const server = await createServer({
    configFile: path.resolve('vite.config.js'),
    logLevel: 'silent',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
  });
  try {
    await server.listen();
    const address = server.httpServer.address();
    assert.ok(address && typeof address === 'object');
    const baseUrl = `http://127.0.0.1:${address.port}`;
    const ranged = await fetch(`${baseUrl}/map-assets/madrid.pmtiles`, { headers: { Range: 'bytes=4-9' } });
    assert.equal(ranged.status, 206);
    assert.equal(ranged.headers.get('accept-ranges'), 'bytes');
    assert.equal(ranged.headers.get('content-range'), 'bytes 4-9/16');
    assert.equal(ranged.headers.get('content-type'), 'application/vnd.pmtiles');
    assert.equal(await ranged.text(), '456789');

    const metadata = await fetch(`${baseUrl}/map-assets/map-assets.json`);
    assert.equal(metadata.status, 200);
    assert.equal((await metadata.json()).contract_version, 'test');
    const provenance = await fetch(`${baseUrl}/map-assets/madrid.pmtiles.provenance.json`);
    assert.equal(provenance.status, 200);
    assert.equal((await provenance.json()).contract_version, 'madrid-osm-vector-cartography-v1');
    assert.equal((await fetch(`${baseUrl}/map-assets/private-key.pem`)).status, 404);
    assert.equal((await fetch(`${baseUrl}/map-assets/madrid.pmtiles`, { headers: { Range: 'bytes=99-100' } })).status, 416);
  } finally {
    await server.close();
    if (previousAssetsDirectory === undefined) delete process.env.MVP_MAP_ASSETS_DIR;
    else process.env.MVP_MAP_ASSETS_DIR = previousAssetsDirectory;
    await rm(assetsDirectory, { recursive: true, force: true });
  }
});

const projectRoot = path.resolve('..');
const realAssetsDirectory = path.join(projectRoot, 'data', 'processed', 'map-assets');
const realArchivePath = path.join(realAssetsDirectory, 'madrid.pmtiles');
const hasRealArchive = await stat(realArchivePath).then(info => info.isFile()).catch(() => false);

test('Vite sirve el PMTiles Madrid real con Range y provenance coherente', { skip: !hasRealArchive }, async () => {
  const previousAssetsDirectory = process.env.MVP_MAP_ASSETS_DIR;
  process.env.MVP_MAP_ASSETS_DIR = realAssetsDirectory;
  const server = await createServer({
    configFile: path.resolve('vite.config.js'),
    logLevel: 'silent',
    server: { host: '127.0.0.1', port: 0, strictPort: false },
  });
  try {
    await server.listen();
    const address = server.httpServer.address();
    assert.ok(address && typeof address === 'object');
    const baseUrl = `http://127.0.0.1:${address.port}`;
    const response = await fetch(`${baseUrl}/map-assets/madrid.pmtiles`, {
      headers: { Range: 'bytes=0-126' },
    });
    const archiveBytes = await readFile(realArchivePath);
    const sidecar = await (await fetch(`${baseUrl}/map-assets/madrid.pmtiles.provenance.json`)).json();
    assert.equal(response.status, 206);
    assert.equal(response.headers.get('content-range'), `bytes 0-126/${archiveBytes.length}`);
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), archiveBytes.subarray(0, 127));
    assert.equal(sidecar.pmtiles.sha256, createHash('sha256').update(archiveBytes).digest('hex'));
    assert.equal(sidecar.pmtiles.size_bytes, archiveBytes.length);
  } finally {
    await server.close();
    if (previousAssetsDirectory === undefined) delete process.env.MVP_MAP_ASSETS_DIR;
    else process.env.MVP_MAP_ASSETS_DIR = previousAssetsDirectory;
  }
});
