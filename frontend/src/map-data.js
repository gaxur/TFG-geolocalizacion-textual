const MAP_ASSETS_CONTRACT = 'madrid-map-assets-v1';
const GALLERY_SIZES = Object.freeze({ 'madrid-25m': 25, 'madrid-50m': 50 });

const isNumber = value => typeof value === 'number' && Number.isFinite(value);

export function validateMapAssetsManifest(document, searchArea) {
  if (document?.schema_version !== '1.0' || document?.contract_version !== MAP_ASSETS_CONTRACT) {
    throw new TypeError('Contrato de recursos cartográficos incompatible.');
  }
  if (document.region_id !== searchArea?.region_id || document.region_id !== 'madrid_pilot') {
    throw new TypeError('Los recursos cartográficos pertenecen a otra región.');
  }
  const bbox = document.region_bbox_wgs84;
  const expected = searchArea?.bbox;
  if (!bbox || !expected || !['north', 'south', 'east', 'west'].every(key => isNumber(bbox[key]) && bbox[key] === expected[key])) {
    throw new TypeError('La bbox cartográfica no coincide exactamente con las capacidades de la API.');
  }
  if (!document.galleries || typeof document.galleries !== 'object') {
    throw new TypeError('El manifest cartográfico no contiene galerías.');
  }
  for (const [galleryId, size] of Object.entries(GALLERY_SIZES)) {
    const gallery = document.galleries[galleryId];
    if (!gallery || gallery.cell_size_m !== size || gallery.candidate_count !== (size === 25 ? 1115 : 253) || typeof gallery.geojson_file !== 'string' || !/^[a-z0-9-]+\.geojson$/.test(gallery.geojson_file) || !/^[0-9a-f]{64}$/.test(gallery.geojson_sha256 || '')) {
      throw new TypeError(`Metadatos de geometría inválidos para ${galleryId}.`);
    }
    if (!/^[0-9a-f]{64}$/.test(gallery.manifest_sha256 || '') ||
        gallery.manifest_sha256 !== gallery.expected_f4_manifest_sha256 ||
        (gallery.f4_manifest_sha256 && gallery.f4_manifest_sha256 !== gallery.expected_f4_manifest_sha256)) {
      throw new TypeError(`La geometría de ${galleryId} no corresponde al manifest comprometido por F4.`);
    }
  }
  return document;
}

export function validateCellGeoJSON(document, { galleryId, searchArea }) {
  const cellSize = GALLERY_SIZES[galleryId];
  if (!cellSize || document?.type !== 'FeatureCollection' || !Array.isArray(document.features)) {
    throw new TypeError(`GeoJSON de celdas inválido para ${galleryId}.`);
  }
  if (document.features.length !== (cellSize === 25 ? 1115 : 253)) {
    throw new TypeError(`El número de celdas no coincide con el catálogo ${galleryId}.`);
  }
  const { north, south, east, west } = searchArea.bbox;
  const seen = new Set();
  for (const feature of document.features) {
    const properties = feature?.properties;
    const ring = feature?.geometry?.type === 'Polygon' && feature.geometry.coordinates?.length === 1
      ? feature.geometry.coordinates[0]
      : null;
    if (!properties || properties.gallery_id !== galleryId || properties.cell_size_m !== cellSize ||
        typeof properties.candidate_id !== 'string' || !properties.candidate_id ||
        properties.candidate_key !== `${galleryId}:${properties.candidate_id}` ||
        feature.id !== properties.candidate_key || !ring || ring.length !== 5 ||
        JSON.stringify(ring[0]) !== JSON.stringify(ring[ring.length - 1]) || seen.has(properties.candidate_id)) {
      throw new TypeError(`Geometría de celda inválida en ${galleryId}.`);
    }
    for (const point of ring) {
      if (!Array.isArray(point) || point.length !== 2 || !isNumber(point[0]) || !isNumber(point[1]) ||
          point[0] < west - 1e-9 || point[0] > east + 1e-9 || point[1] < south - 1e-9 || point[1] > north + 1e-9) {
        throw new TypeError(`Coordenada de celda fuera de D004: ${properties.candidate_id}.`);
      }
    }
    seen.add(properties.candidate_id);
  }
  return document;
}

export function regionBoundaryGeoJSON(searchArea) {
  const { north, south, east, west } = searchArea.bbox;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      id: searchArea.region_id,
      properties: { region_id: searchArea.region_id },
      geometry: {
        type: 'Polygon',
        coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
      },
    }],
  };
}

export function buildRankedCandidatesGeoJSON(retrievals, selectedKey, catalogs) {
  const features = [];
  const missingCellKeys = [];
  for (const retrieval of retrievals || []) {
    const catalog = catalogs?.[retrieval.galleryId];
    for (const candidate of retrieval.results || []) {
      const selected = candidate.key === selectedKey;
      const base = {
        candidate_key: candidate.key,
        candidate_id: candidate.id,
        gallery_id: candidate.galleryId,
        rank: candidate.rank,
        selected,
        similarity: candidate.similarity,
      };
      const cell = catalog?.get(candidate.id);
      if (cell) {
        features.push({
          type: 'Feature',
          id: `${candidate.key}:cell`,
          properties: { ...base, feature_key: `${candidate.key}:cell`, feature_kind: 'cell' },
          geometry: cell.geometry,
        });
      } else {
        missingCellKeys.push(candidate.key);
      }
    }
  }
  return {
    data: { type: 'FeatureCollection', features },
    missingCellKeys,
  };
}

export function catalogIndex(document) {
  return new Map(document.features.map(feature => [feature.properties.candidate_id, feature]));
}

export const galleryCellSize = galleryId => GALLERY_SIZES[galleryId] || null;
