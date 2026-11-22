import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildRankedCandidatesGeoJSON,
  catalogIndex,
  regionBoundaryGeoJSON,
  validateCellGeoJSON,
  validateMapAssetsManifest,
} from '../src/map-data.js';

const searchArea = {
  region_id: 'madrid_pilot',
  crs: 'EPSG:4326',
  bbox: { north: 40.42, south: 40.412, east: -3.699, west: -3.709 },
};

function makeCells(galleryId, size, count) {
  const features = Array.from({ length: count }, (_, index) => {
    const lon = -3.708 + (index % 50) * 0.0001;
    const lat = 40.413 + Math.floor(index / 50) * 0.0001;
    const candidateId = `${galleryId}-candidate-${index + 1}`;
    const candidateKey = `${galleryId}:${candidateId}`;
    return {
      type: 'Feature',
      id: candidateKey,
      properties: { candidate_key: candidateKey, candidate_id: candidateId, gallery_id: galleryId, cell_size_m: size },
      geometry: { type: 'Polygon', coordinates: [[[lon, lat], [lon + 0.00001, lat], [lon + 0.00001, lat + 0.00001], [lon, lat + 0.00001], [lon, lat]]] },
    };
  });
  return { type: 'FeatureCollection', features };
}

test('valida metadatos y bbox sin aceptar otra región', () => {
  const assets = {
    schema_version: '1.0', contract_version: 'madrid-map-assets-v1', region_id: 'madrid_pilot',
    region_bbox_wgs84: searchArea.bbox,
    galleries: {
      'madrid-25m': { candidate_count: 1115, cell_size_m: 25, geojson_file: 'cells-25m.geojson', geojson_sha256: 'a'.repeat(64), manifest_sha256: 'c'.repeat(64), expected_f4_manifest_sha256: 'c'.repeat(64), f4_manifest_sha256: null },
      'madrid-50m': { candidate_count: 253, cell_size_m: 50, geojson_file: 'cells-50m.geojson', geojson_sha256: 'b'.repeat(64), manifest_sha256: 'd'.repeat(64), expected_f4_manifest_sha256: 'd'.repeat(64), f4_manifest_sha256: null },
    },
  };
  assert.equal(validateMapAssetsManifest(assets, searchArea), assets);
  assert.throws(() => validateMapAssetsManifest({ ...assets, region_bbox_wgs84: { ...searchArea.bbox, east: -3.7 } }, searchArea));
});

test('valida el GeoJSON canónico y exige celdas cerradas de la galería correcta', () => {
  const cells = makeCells('madrid-50m', 50, 253);
  assert.equal(validateCellGeoJSON(cells, { galleryId: 'madrid-50m', searchArea }), cells);
  cells.features[0].properties.gallery_id = 'madrid-25m';
  assert.throws(() => validateCellGeoJSON(cells, { galleryId: 'madrid-50m', searchArea }));
});

test('crea límite D004 y sincroniza polígonos/puntos del Top-10 sin alterar el ranking', () => {
  const boundary = regionBoundaryGeoJSON(searchArea);
  assert.deepEqual(boundary.features[0].geometry.coordinates[0][0], [-3.709, 40.412]);
  const cells = catalogIndex(makeCells('madrid-50m', 50, 253));
  const results = [{
    galleryId: 'madrid-50m', galleryCount: 253,
    results: [
      { key: 'madrid-50m:madrid-50m-candidate-2', id: 'madrid-50m-candidate-2', rank: 1, lat: 40.414, lon: -3.705, similarity: 0.31, galleryId: 'madrid-50m' },
      { key: 'madrid-50m:missing', id: 'missing', rank: 2, lat: 40.415, lon: -3.704, similarity: 0.2, galleryId: 'madrid-50m' },
    ],
  }];
  const overlay = buildRankedCandidatesGeoJSON(results, results[0].results[0].key, { 'madrid-50m': cells });
  assert.deepEqual(overlay.data.features.map(row => row.properties.rank), [1]);
  assert.equal(overlay.data.features[0].properties.selected, true);
  assert.deepEqual(overlay.data.features[0].geometry, cells.get('madrid-50m-candidate-2').geometry);
  assert.deepEqual(overlay.missingCellKeys, ['madrid-50m:missing']);
});
