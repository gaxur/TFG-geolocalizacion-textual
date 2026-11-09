import { defineConfig } from 'vite';
import { createReadStream, statSync } from 'node:fs';
import { extname, isAbsolute, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('.', import.meta.url));
const projectRoot = resolve(frontendRoot, '..');
const configuredMapAssets = process.env.MVP_MAP_ASSETS_DIR || './data/processed/map-assets';
const mapAssetsRoot = isAbsolute(configuredMapAssets)
  ? resolve(configuredMapAssets)
  : resolve(projectRoot, configuredMapAssets);
const allowedMapAssets = new Set([
  'map-assets.json',
  'cells-25m.geojson',
  'cells-50m.geojson',
  'madrid.pmtiles',
  'madrid.pmtiles.provenance.json',
  'madrid-osm-building-audit.json',
]);
const mapAssetTypes = {
  '.geojson': 'application/geo+json; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.pmtiles': 'application/vnd.pmtiles',
};

function localMapAssets() {
  return {
    name: 'atlas-local-map-assets',
    configureServer(server) {
      server.middlewares.use('/map-assets', (request, response, next) => {
        if (!['GET', 'HEAD'].includes(request.method || 'GET')) return next();
        let name;
        try {
          name = decodeURIComponent(new URL(request.url || '/', 'http://vite.local').pathname)
            .replace(/^\/+/, '')
            .replace(/^map-assets\//, '');
        } catch {
          response.writeHead(400).end('Ruta inválida');
          return;
        }
        if (!allowedMapAssets.has(name)) {
          response.writeHead(404).end('Recurso cartográfico no encontrado');
          return;
        }
        const file = resolve(mapAssetsRoot, name);
        if (!file.startsWith(`${mapAssetsRoot}${sep}`)) {
          response.writeHead(403).end('Acceso denegado');
          return;
        }
        let info;
        try { info = statSync(file); }
        catch {
          response.writeHead(404).end('Recurso cartográfico no preparado');
          return;
        }
        if (!info.isFile()) {
          response.writeHead(404).end('Recurso cartográfico no encontrado');
          return;
        }
        const headers = {
          'Accept-Ranges': 'bytes',
          'Cache-Control': 'no-store',
          'Content-Type': mapAssetTypes[extname(file)] || 'application/octet-stream',
        };
        const range = request.headers.range;
        if (range) {
          const match = /^bytes=(\d+)-(\d*)$/.exec(range);
          if (!match) {
            response.writeHead(416, { ...headers, 'Content-Range': `bytes */${info.size}` }).end();
            return;
          }
          const start = Number(match[1]);
          const end = Math.min(match[2] ? Number(match[2]) : info.size - 1, info.size - 1);
          if (start >= info.size || end < start) {
            response.writeHead(416, { ...headers, 'Content-Range': `bytes */${info.size}` }).end();
            return;
          }
          response.writeHead(206, {
            ...headers,
            'Content-Length': end - start + 1,
            'Content-Range': `bytes ${start}-${end}/${info.size}`,
          });
          if (request.method === 'HEAD') response.end();
          else createReadStream(file, { start, end }).pipe(response);
          return;
        }
        response.writeHead(200, { ...headers, 'Content-Length': info.size });
        if (request.method === 'HEAD') response.end();
        else createReadStream(file).pipe(response);
      });
    },
  };
}

export default defineConfig({
  plugins: [localMapAssets()],
  preview: {
    host: '127.0.0.1',
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
});
