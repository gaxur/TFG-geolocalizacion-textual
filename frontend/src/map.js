import {
  addProtocol,
  Map as MapLibreMap,
  Marker as MapLibreMarker,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
} from 'maplibre-gl';
import { PMTiles, Protocol, TileType } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import {
  buildRankedCandidatesGeoJSON,
  catalogIndex,
  regionBoundaryGeoJSON,
  validateCellGeoJSON,
  validateMapAssetsManifest,
} from './map-data.js';

const ASSET_BASE = '/map-assets';
const ASSET_MANIFEST_URL = `${ASSET_BASE}/map-assets.json`;
const PMTILES_URL = new URL(`${ASSET_BASE}/madrid.pmtiles`, window.location.origin).toString();
const PMTILES_PROTOCOL_KEY = Symbol.for('atlas.maplibre.pmtiles.protocol');
let mapInstanceCounter = 0;
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

setWorkerUrl(workerUrl);
if (!globalThis[PMTILES_PROTOCOL_KEY]) {
  const protocol = new Protocol({ metadata: true });
  addProtocol('pmtiles', protocol.tile);
  globalThis[PMTILES_PROTOCOL_KEY] = protocol;
}

function emptyFeatureCollection() {
  return { type: 'FeatureCollection', features: [] };
}

function boundsFrom(searchArea) {
  const { west, south, east, north } = searchArea.bbox;
  return [[west, south], [east, north]];
}

function baseStyle(basemap) {
  const sources = {};
  const layers = [{
    id: 'atlas-background',
    type: 'background',
    paint: { 'background-color': '#e8eee9' },
  }];

  if (!basemap.available) return { version: 8, sources, layers };

  sources['madrid-local'] = {
    type: 'vector',
    url: `pmtiles://${PMTILES_URL}`,
    attribution: basemap.attribution,
  };
  return { version: 8, sources, layers };
}

function createBoundaryLayers(map, searchArea) {
  map.addSource('madrid-region', { type: 'geojson', data: regionBoundaryGeoJSON(searchArea) });
  const firstSymbol = map.getStyle().layers.find(layer => layer.type === 'symbol')?.id;
  map.addLayer({
    id: 'madrid-region-fill', type: 'fill', source: 'madrid-region',
    paint: { 'fill-color': '#b35f3f', 'fill-opacity': 0.035 },
  }, firstSymbol);
  map.addLayer({
    id: 'madrid-region-outline', type: 'line', source: 'madrid-region',
    paint: { 'line-color': '#9d4e36', 'line-width': 2, 'line-dasharray': [2, 2], 'line-opacity': 0.9 },
  }, firstSymbol);
}

function createCandidateLayers(map) {
  map.addSource('catalog-cells', {
    type: 'geojson',
    data: emptyFeatureCollection(),
    promoteId: 'candidate_key',
  });
  map.addLayer({
    id: 'catalog-cell-grid', type: 'line', source: 'catalog-cells',
    layout: { visibility: 'none' },
    paint: { 'line-color': '#608776', 'line-width': 0.8, 'line-opacity': 0.22 },
  }, map.getStyle().layers.find(layer => layer.type === 'symbol')?.id);

  map.addSource('ranked-candidates', {
    type: 'geojson',
    data: emptyFeatureCollection(),
    promoteId: 'feature_key',
  });
  const firstSymbol = map.getStyle().layers.find(layer => layer.type === 'symbol')?.id;
  map.addLayer({
    id: 'ranked-cells', type: 'fill', source: 'ranked-candidates',
    filter: ['==', ['get', 'feature_kind'], 'cell'],
    paint: {
      'fill-color': ['case', ['get', 'selected'], '#d99a3d', ['==', ['get', 'rank'], 1], '#a96542', '#3d806b'],
      'fill-opacity': ['case', ['get', 'selected'], 0.34, 0.18],
    },
  }, firstSymbol);
  map.addLayer({
    id: 'ranked-cell-outlines', type: 'line', source: 'ranked-candidates',
    filter: ['==', ['get', 'feature_kind'], 'cell'],
    paint: {
      'line-color': ['case', ['get', 'selected'], '#8e5a1c', ['==', ['get', 'rank'], 1], '#71482f', '#285d4b'],
      'line-width': ['case', ['get', 'selected'], 3, ['==', ['get', 'rank'], 1], 2.2, 1.4],
      'line-opacity': 0.94,
    },
  }, firstSymbol);
  const selectFeature = event => {
    const feature = event.features?.[0];
    const key = feature?.properties?.candidate_key;
    if (typeof key === 'string') map.fire('atlas-candidate-select', { candidateKey: key });
  };
  for (const layerId of ['ranked-cells', 'ranked-cell-outlines']) {
    map.on('click', layerId, selectFeature);
    map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = ''; });
  }
}

function addBasemapLayers(map, basemap) {
  const available = new Set(basemap.layers.map(layer => layer.id));
  const add = (id, layer) => {
    if (available.has(id)) map.addLayer(layer);
  };
  add('landcover', {
    id: 'madrid-landcover', type: 'fill', source: 'madrid-local', 'source-layer': 'landcover',
    paint: { 'fill-color': '#e2eadc', 'fill-opacity': 0.65 },
  });
  add('landuse', {
    id: 'madrid-landuse', type: 'fill', source: 'madrid-local', 'source-layer': 'landuse',
    paint: { 'fill-color': ['match', ['get', 'class'], 'park', '#d6e7d3', 'grass', '#e1ebd8', '#edece5'], 'fill-opacity': 0.72 },
  });
  add('water', {
    id: 'madrid-water', type: 'fill', source: 'madrid-local', 'source-layer': 'water',
    paint: { 'fill-color': '#cbdfe2', 'fill-opacity': 0.94 },
  });
  add('transportation', {
    id: 'madrid-roads', type: 'line', source: 'madrid-local', 'source-layer': 'transportation',
    paint: {
      'line-color': ['match', ['get', 'class'], 'motorway', '#d4b696', 'primary', '#d8c7b0', 'secondary', '#dfd5c9', '#fffefa'],
      'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.7, 16, 3.4],
      'line-opacity': 0.98,
    },
  });
  if (available.has('building')) {
    map.addLayer({
      id: 'madrid-building-footprints', type: 'fill', source: 'madrid-local', 'source-layer': 'building',
      minzoom: 14,
      paint: { 'fill-color': '#d5d0c4', 'fill-outline-color': '#b5afa2', 'fill-opacity': 0.8 },
    });
    if (basemap.heightProperty) {
      map.addLayer({
        id: 'madrid-buildings-3d', type: 'fill-extrusion', source: 'madrid-local', 'source-layer': 'building',
        minzoom: 15,
        layout: { visibility: 'none' },
        filter: ['all', ['!=', ['get', 'hide_3d'], true], ['>', ['to-number', ['get', basemap.heightProperty], 0], 0]],
        paint: {
          'fill-extrusion-color': ['case', ['has', 'colour'], ['get', 'colour'], '#c6c0b3'],
          'fill-extrusion-height': ['to-number', ['get', basemap.heightProperty], 0],
          'fill-extrusion-base': basemap.baseHeightProperty
            ? ['to-number', ['get', basemap.baseHeightProperty], 0]
            : 0,
          'fill-extrusion-opacity': 0.96,
          'fill-extrusion-vertical-gradient': true,
        },
      });
    }
  }
  add('place', {
    id: 'madrid-place-labels', type: 'symbol', source: 'madrid-local', 'source-layer': 'place',
    layout: { 'text-field': ['coalesce', ['get', 'name:latin'], ['get', 'name'], ''], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 16, 13], 'text-max-width': 8 },
    paint: { 'text-color': '#35453e', 'text-halo-color': 'rgba(255,255,255,0.88)', 'text-halo-width': 1.1 },
  });
  add('transportation_name', {
    id: 'madrid-road-labels', type: 'symbol', source: 'madrid-local', 'source-layer': 'transportation_name',
    minzoom: 13,
    layout: { 'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'name:latin'], ['get', 'name'], ''], 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 13, 9, 17, 12], 'text-max-width': 7 },
    paint: { 'text-color': '#536057', 'text-halo-color': 'rgba(255,255,255,0.9)', 'text-halo-width': 1 },
  });
}

function supportsWebGL2() {
  try {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: false });
    if (!context) return false;
    context.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}

async function loadAssetsManifest(searchArea) {
  const response = await fetch(ASSET_MANIFEST_URL, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`No se encontró ${ASSET_MANIFEST_URL} (HTTP ${response.status}).`);
  return validateMapAssetsManifest(await response.json(), searchArea);
}

async function loadCatalog(assetManifest, galleryId) {
  const gallery = assetManifest.galleries[galleryId];
  const cellResponse = await fetch(`${ASSET_BASE}/${encodeURIComponent(gallery.geojson_file)}`, {
    headers: { Accept: 'application/geo+json, application/json' },
  });
  if (!cellResponse.ok) throw new Error(`No se encontró la geometría ${gallery.geojson_file} (HTTP ${cellResponse.status}).`);
  const cells = validateCellGeoJSON(await cellResponse.json(), { galleryId, searchArea: assetManifest.region_bbox_wgs84 ? { region_id: assetManifest.region_id, bbox: assetManifest.region_bbox_wgs84 } : null });
  return { assetManifest, catalog: catalogIndex(cells), gallery };
}

async function inspectLocalBasemap(searchArea, assetManifest) {
  if (assetManifest?.basemap?.expected_tile_schema !== 'madrid-osm-explicit-height-v1') {
    throw new Error('map-assets.json no declara el esquema local de alturas explícitas esperado.');
  }
  const archive = new PMTiles(PMTILES_URL);
  const [header, metadata] = await Promise.all([archive.getHeader(), archive.getMetadata()]);
  if (header.minLon > searchArea.bbox.west || header.minLat > searchArea.bbox.south ||
      header.maxLon < searchArea.bbox.east || header.maxLat < searchArea.bbox.north) {
    throw new Error('La cobertura del archivo PMTiles no incluye toda la bbox D004.');
  }
  const layers = Array.isArray(metadata?.vector_layers) ? metadata.vector_layers : [];
  const layerIds = new Set(layers.map(layer => layer?.id));
  if (!layerIds.has('building') || !layerIds.has('transportation')) {
    throw new Error('PMTiles no contiene las capas building y transportation del esquema esperado.');
  }
  const building = layers.find(layer => layer?.id === 'building');
  const fields = building?.fields || {};
  const heightProperty = Object.hasOwn(fields, 'height') && /number|integer|string/i.test(String(fields.height))
    ? 'height'
    : null;
  const baseHeightProperty = Object.hasOwn(fields, 'min_height') && /number|integer|string/i.test(String(fields.min_height))
    ? 'min_height'
    : null;
  if (header.tileType !== TileType.Mvt || !layers.length) throw new Error('El archivo local no contiene teselas vectoriales con metadatos de capas.');
  const provenanceResponse = await fetch(`${ASSET_BASE}/madrid.pmtiles.provenance.json`, {
    headers: { Accept: 'application/json' },
  });
  if (!provenanceResponse.ok) throw new Error('Falta la provenance local de madrid.pmtiles.');
  const provenance = await provenanceResponse.json();
  if (provenance?.contract_version !== 'madrid-osm-vector-cartography-v1' ||
      provenance?.profile !== 'madrid-osm-explicit-height-v1' ||
      !/^[0-9a-f]{64}$/.test(provenance?.pmtiles?.sha256 || '') ||
      provenance?.pmtiles?.path !== 'madrid.pmtiles' ||
      !/^[0-9a-f]{64}$/.test(provenance?.source?.source_pbf_sha256 || '') ||
      provenance?.source?.license !== 'ODbL-1.0') {
    throw new Error('La provenance del PMTiles local no coincide con el perfil/licencia esperados.');
  }
  const heightAudit = provenance?.feature_audit?.height_coverage_base_buildings;
  const partsAudit = provenance?.feature_audit?.height_coverage_building_parts;
  if (!Number.isInteger(heightAudit?.denominator) || !Number.isInteger(heightAudit?.explicit_numeric_metre_height) ||
      !Number.isInteger(partsAudit?.denominator) || !Number.isInteger(partsAudit?.explicit_numeric_metre_height)) {
    throw new Error('La provenance PMTiles no contiene el resumen verificable de alturas.');
  }
  const explicitHeightCount = heightAudit.explicit_numeric_metre_height + partsAudit.explicit_numeric_metre_height;
  const declaredHeightCount = provenance?.pmtiles?.validation?.explicit_height_features_in_tiles;
  if (!heightProperty || explicitHeightCount < 1 || !Number.isInteger(declaredHeightCount) || declaredHeightCount < 1) {
    throw new Error('No hay alturas explícitas verificadas para habilitar edificios 3D.');
  }
  const archiveHead = await fetch(PMTILES_URL, { method: 'HEAD' });
  if (!archiveHead.ok || Number(archiveHead.headers.get('content-length')) !== provenance.pmtiles.size_bytes) {
    throw new Error('El tamaño servido de madrid.pmtiles no coincide con su provenance.');
  }
  return {
    available: true,
    layers,
    heightProperty,
    baseHeightProperty,
    heightAudit: { base: heightAudit, parts: partsAudit, explicitTileFeatures: declaredHeightCount },
    buildings3dAvailable: Boolean(building && heightProperty && explicitHeightCount > 0),
    attribution: metadata.attribution || '© OpenStreetMap contributors · ODbL 1.0',
  };
}

function currentCameraView(map) {
  const center = map.getCenter();
  return { center: [center.lng, center.lat], zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() };
}

async function createLeafletFallback({ element, searchArea, galleryId, assetManifest, catalogs, onSelect, onViewChange, onStatus, status }) {
  const [{ default: L }] = await Promise.all([
    import('leaflet'),
    import('leaflet/dist/leaflet.css'),
  ]);
  const bounds = L.latLngBounds(
    [searchArea.bbox.south, searchArea.bbox.west],
    [searchArea.bbox.north, searchArea.bbox.east],
  );
  element.dataset.renderer = 'leaflet-2d';
  element.dataset.mapInstanceId = String(++mapInstanceCounter);
  element.dataset.mapMode = '2d';
  element.classList.add('map-fallback-2d');
  const map = L.map(element, { zoomControl: false, attributionControl: true, maxBounds: bounds, keyboard: true });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
  L.rectangle(bounds, { color: '#9d4e36', weight: 2, dashArray: '6 5', fillColor: '#b35f3f', fillOpacity: 0.04, interactive: false }).addTo(map);
  map.fitBounds(bounds, { animate: false });
  const gridLayer = L.featureGroup().addTo(map);
  const group = L.featureGroup().addTo(map);
  let gridVisible = false;
  let currentCatalogs = catalogs || {};
  let currentGalleryId = galleryId;
  let currentData = { retrievals: [], selectedKey: '' };
  map.on('moveend', () => onViewChange?.({ center: [map.getCenter().lng, map.getCenter().lat], zoom: map.getZoom(), pitch: 0, bearing: 0 }));

  function update({ retrievals = currentData.retrievals, selectedKey = currentData.selectedKey, catalogs = currentCatalogs, galleryId: nextGalleryId = currentGalleryId } = {}) {
    if (nextGalleryId && nextGalleryId !== currentGalleryId) {
      currentGalleryId = nextGalleryId;
      void loadFallbackGallery(nextGalleryId);
    }
    currentData = { retrievals, selectedKey };
    currentCatalogs = catalogs;
    element.dataset.mapCandidateCount = String(retrievals.reduce((sum, row) => sum + row.results.length, 0));
    element.dataset.mapCellCount = String(retrievals.reduce((sum, row) => sum + row.results.filter(candidate => currentCatalogs?.[row.galleryId]?.has(candidate.id)).length, 0));
    element.dataset.selectedKey = selectedKey || '';
    drawGrid();
    group.clearLayers();
    for (const retrieval of retrievals || []) {
      const catalog = currentCatalogs?.[retrieval.galleryId];
      for (const candidate of retrieval.results || []) {
        const cell = catalog?.get(candidate.id);
        if (cell) {
          L.geoJSON(cell, {
            style: {
              color: candidate.key === selectedKey ? '#8e5a1c' : '#356d59',
              weight: candidate.key === selectedKey ? 3 : 1.5,
              fillColor: candidate.rank === 1 ? '#a96542' : '#3d806b',
              fillOpacity: candidate.key === selectedKey ? 0.32 : 0.14,
            },
            onEachFeature: (_feature, layer) => layer.on('click', () => onSelect?.(candidate.key)),
          }).addTo(group);
        }
        const markerButton = document.createElement('button');
        markerButton.type = 'button';
        markerButton.className = `map-result-marker${candidate.rank === 1 ? ' is-top-result' : ''}${candidate.key === selectedKey ? ' is-selected' : ''}`;
        markerButton.textContent = String(candidate.rank).padStart(2, '0');
        markerButton.dataset.candidateKey = candidate.key;
        markerButton.setAttribute('aria-label', `Seleccionar candidato ${candidate.rank}: ${candidate.id}`);
        markerButton.setAttribute('aria-pressed', String(candidate.key === selectedKey));
        markerButton.title = `Top-${candidate.rank} · ${candidate.id}`;
        markerButton.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          onSelect?.(candidate.key);
        });
        L.marker([candidate.lat, candidate.lon], {
          keyboard: false,
          icon: L.divIcon({ className: 'map-result-marker-shell', html: markerButton, iconSize: [38, 38], iconAnchor: [19, 19] }),
        }).addTo(group);
      }
    }
  }

  function drawGrid() {
    gridLayer.clearLayers();
    const catalog = currentCatalogs[currentGalleryId];
    if (!gridVisible || !catalog) return;
    L.geoJSON({ type: 'FeatureCollection', features: [...catalog.values()] }, {
      interactive: false,
      style: { color: '#608776', weight: 0.7, opacity: 0.38, fillColor: '#608776', fillOpacity: 0.015 },
    }).addTo(gridLayer);
  }

  async function loadFallbackGallery(nextGalleryId) {
    if (currentCatalogs[nextGalleryId]) { update(currentData); return; }
    status.cells = 'loading';
    status.message = `Cargando las celdas canónicas de ${nextGalleryId}…`;
    onStatus?.(status);
    try {
      if (!assetManifest) throw new Error('Falta map-assets.json.');
      const loaded = await loadCatalog(assetManifest, nextGalleryId);
      if (currentGalleryId !== nextGalleryId) return;
      currentCatalogs = { ...currentCatalogs, [nextGalleryId]: loaded.catalog };
      status.cells = 'ready';
      status.message = 'Geometrías canónicas cargadas desde los recursos locales.';
    } catch (error) {
      if (currentGalleryId !== nextGalleryId) return;
      status.cells = 'missing';
      status.message = `No se cargó la geometría canónica: ${error.message}`;
      status.detail = error.message;
    }
    onStatus?.(status);
    update(currentData);
  }

  return {
    renderer: 'leaflet-2d',
    status,
    update,
    async setGallery(nextGalleryId) {
      if (!nextGalleryId || nextGalleryId === currentGalleryId) return;
      currentGalleryId = nextGalleryId;
      await loadFallbackGallery(nextGalleryId);
    },
    resize: () => map.invalidateSize({ pan: false }),
    flyTo: candidate => map.flyTo([candidate.lat, candidate.lon], Math.max(map.getZoom(), 17), { duration: reducedMotion() ? 0 : 0.55 }),
    setMode: () => {},
    setBuildings: () => {},
    setGrid(visible) { gridVisible = Boolean(visible); drawGrid(); },
    reset: () => map.fitBounds(bounds, { animate: !reducedMotion() }),
    destroy: () => map.remove(),
  };
}

export async function createResultsMap({
  element,
  retrievals = [],
  selectedKey,
  view,
  searchArea,
  galleryId,
  onSelect,
  onViewChange,
  onStatus,
}) {
  if (!element || !searchArea?.bbox) return null;

  let assets = { status: 'missing', catalog: null, assetManifest: null };
  try {
    const assetManifest = await loadAssetsManifest(searchArea);
    assets.assetManifest = assetManifest;
    try {
      const loaded = await loadCatalog(assetManifest, galleryId);
      assets = { status: 'ready', ...loaded };
    } catch (error) {
      assets.error = error;
    }
  } catch (error) {
    assets.error = error;
  }
  if (!element.isConnected) return null;

  if (!supportsWebGL2()) {
    const status = {
      renderer: 'leaflet-2d', basemap: 'unavailable', cells: assets.status,
      buildings3dAvailable: false, missingCellCount: assets.status === 'ready' ? 0 : (retrievals[0]?.results.length || 0),
      message: 'Este navegador no ofrece WebGL2. Vista 2D local; la lista Top-10 sigue disponible.',
      detail: assets.error?.message || null,
    };
    onStatus?.(status);
    const catalogs = assets.catalog ? { [galleryId]: assets.catalog } : {};
    const fallback = await createLeafletFallback({ element, searchArea, galleryId, assetManifest: assets.assetManifest, catalogs, onSelect, onViewChange, onStatus, status });
    fallback.update({ retrievals, selectedKey, catalogs });
    return fallback;
  }

  let basemap = { available: false, layers: [], heightProperty: null, baseHeightProperty: null, buildings3dAvailable: false, attribution: '' };
  let basemapError = null;
  try {
    basemap = await inspectLocalBasemap(searchArea, assets.assetManifest);
  } catch (error) {
    basemapError = error;
  }
  const catalogs = assets.catalog ? { [galleryId]: assets.catalog } : {};
  const status = {
    renderer: 'maplibre',
    basemap: basemap.available ? 'ready' : 'missing',
    cells: assets.status,
    buildings3dAvailable: basemap.buildings3dAvailable,
    missingCellCount: 0,
    message: basemap.available
      ? basemap.buildings3dAvailable
        ? `Extrusión 3D parcial: ${basemap.heightAudit.base.explicit_numeric_metre_height}/${basemap.heightAudit.base.denominator} edificios y ${basemap.heightAudit.parts.explicit_numeric_metre_height}/${basemap.heightAudit.parts.denominator} partes tienen etiqueta height explícita en metros; no es una medición independiente y el resto sigue en 2D.`
        : 'Base local preparada, pero no ofrece un campo de altura utilizable para extrusión 3D.'
      : 'Falta madrid.pmtiles en los recursos locales. No se solicitan mapas a proveedores externos.',
    detail: assets.error?.message || basemapError?.message || null,
  };
  onStatus?.(status);
  element.dataset.renderer = 'maplibre';
  element.dataset.mapInstanceId = String(++mapInstanceCounter);
  element.dataset.mapMode = '2d';
  element.classList.toggle('map-without-tiles', !basemap.available);

  let map;
  try {
    map = new MapLibreMap({
      container: element,
      style: baseStyle(basemap),
      center: [(searchArea.bbox.west + searchArea.bbox.east) / 2, (searchArea.bbox.south + searchArea.bbox.north) / 2],
      zoom: 15,
      pitch: view?.pitch ?? 0,
      bearing: view?.bearing ?? 0,
      maxBounds: boundsFrom(searchArea),
      maxPitch: 65,
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true, failIfMajorPerformanceCaveat: false },
      fadeDuration: reducedMotion() ? 0 : 250,
    });
  } catch (error) {
    const fallbackStatus = {
      ...status,
      renderer: 'leaflet-2d',
      buildings3dAvailable: false,
      message: `No se pudo iniciar WebGL2 (${error.message}). Se muestra el fallback 2D.`,
    };
    onStatus?.(fallbackStatus);
    const fallback = await createLeafletFallback({ element, searchArea, galleryId, assetManifest: assets.assetManifest, catalogs, onSelect, onViewChange, onStatus, status: fallbackStatus });
    fallback.update({ retrievals, selectedKey, catalogs });
    return fallback;
  }
  map.addControl(new NavigationControl({ visualizePitch: true, showZoom: true, showCompass: true }), 'bottom-right');
  map.addControl(new ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-left');

  let destroyed = false;
  let styleReady = false;
  const rankedMarkers = new Map();
  let appliedCatalog = null;
  let catalogInitialized = false;
  let current = { retrievals, selectedKey, catalogs, galleryId, gridVisible: false, buildingsVisible: true, mode: '2d' };

  async function ensureGalleryCatalog(nextGalleryId) {
    if (current.catalogs?.[nextGalleryId] || destroyed) return;
    status.cells = 'loading';
    status.message = `Cargando las celdas canónicas de ${nextGalleryId}…`;
    onStatus?.(status);
    try {
    const loaded = await loadCatalog(assets.assetManifest, nextGalleryId);
      if (destroyed || current.galleryId !== nextGalleryId) return;
      current.catalogs = { ...current.catalogs, [nextGalleryId]: loaded.catalog };
      status.cells = 'ready';
      status.message = 'Geometrías canónicas cargadas desde los recursos locales.';
    } catch (error) {
      if (destroyed || current.galleryId !== nextGalleryId) return;
      status.cells = 'missing';
      status.message = `No se cargó la geometría canónica: ${error.message}`;
      status.detail = error.message;
    }
    onStatus?.(status);
    applyCurrentData();
  }
  const ready = new Promise(resolve => {
    map.once('load', () => {
      if (destroyed) { resolve(false); return; }
      if (basemap.available) addBasemapLayers(map, basemap);
      createBoundaryLayers(map, searchArea);
      createCandidateLayers(map);
      styleReady = true;
      applyCurrentData();
      if (view?.center && Array.isArray(view.center) && view.center.length === 2) {
        map.jumpTo({
          center: view.center,
          zoom: Math.max(map.getMinZoom() || 0, view.zoom || 15),
          pitch: view.pitch || 0,
          bearing: view.bearing || 0,
        });
      } else {
        map.fitBounds(boundsFrom(searchArea), { padding: 34, duration: 0 });
      }
      if (!element.isConnected) { resolve(false); return; }
      map.resize();
      resolve(true);
    });
  });

  function applyCurrentData() {
    if (!styleReady || destroyed) return;
    const source = map.getSource('ranked-candidates');
    const overlay = buildRankedCandidatesGeoJSON(current.retrievals, current.selectedKey, current.catalogs);
    source?.setData(overlay.data);
    syncRankedMarkers();
    element.dataset.mapCandidateCount = String(current.retrievals.reduce((sum, row) => sum + row.results.length, 0));
    element.dataset.mapCellCount = String(overlay.data.features.length);
    element.dataset.selectedKey = current.selectedKey || '';
    status.missingCellCount = overlay.missingCellKeys.length;
    if (overlay.missingCellKeys.length) {
      status.message = `Faltan ${overlay.missingCellKeys.length} geometrías canónicas del Top-10; se muestran solo sus centros.`;
      onStatus?.(status);
    }
    const grid = map.getSource('catalog-cells');
    const catalog = current.catalogs?.[current.galleryId];
    if (!catalogInitialized || catalog !== appliedCatalog) {
      grid?.setData(catalog
        ? { type: 'FeatureCollection', features: [...catalog.values()] }
        : emptyFeatureCollection());
      appliedCatalog = catalog;
      catalogInitialized = true;
    }
    if (map.getLayer('catalog-cell-grid')) {
      map.setLayoutProperty('catalog-cell-grid', 'visibility', current.gridVisible ? 'visible' : 'none');
    }
    if (map.getLayer('madrid-buildings-3d')) {
      map.setLayoutProperty('madrid-buildings-3d', 'visibility', current.mode === '3d' && current.buildingsVisible ? 'visible' : 'none');
    }
    const extrusionLayer = map.getLayer('madrid-buildings-3d');
    element.dataset.mapBuilding3dLayer = extrusionLayer ? 'ready' : 'unavailable';
    element.dataset.mapBuilding3dVisibility = extrusionLayer
      ? map.getLayoutProperty('madrid-buildings-3d', 'visibility')
      : 'unavailable';
  }

  function syncRankedMarkers() {
    const candidates = current.retrievals.flatMap(row => row.results);
    const wanted = new Set(candidates.map(candidate => candidate.key));
    for (const [key, entry] of rankedMarkers) {
      if (!wanted.has(key)) {
        entry.marker.remove();
        rankedMarkers.delete(key);
      }
    }
    for (const candidate of candidates) {
      let entry = rankedMarkers.get(candidate.key);
      if (!entry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'map-result-marker';
        button.dataset.candidateKey = candidate.key;
        button.addEventListener('click', event => {
          event.preventDefault();
          event.stopPropagation();
          onSelect?.(candidate.key);
        });
        const marker = new MapLibreMarker({ element: button, anchor: 'center' })
          .setLngLat([candidate.lon, candidate.lat])
          .addTo(map);
        entry = { button, marker };
        rankedMarkers.set(candidate.key, entry);
      }
      const { button, marker } = entry;
      button.textContent = String(candidate.rank).padStart(2, '0');
      button.dataset.candidateKey = candidate.key;
      button.classList.toggle('is-top-result', candidate.rank === 1);
      button.classList.toggle('is-selected', candidate.key === current.selectedKey);
      button.setAttribute('aria-label', `Seleccionar candidato ${candidate.rank}: ${candidate.id}`);
      button.setAttribute('aria-pressed', String(candidate.key === current.selectedKey));
      button.title = `Top-${candidate.rank} · ${candidate.id}`;
      marker.setLngLat([candidate.lon, candidate.lat]);
    }
  }

  map.on('atlas-candidate-select', event => onSelect?.(event.candidateKey));
  map.on('moveend', () => onViewChange?.(currentCameraView(map)));
  map.on('error', event => {
    if (event?.error && /pmtiles|madrid-local/i.test(`${event.error.message} ${event.sourceId || ''}`)) {
      const updated = { ...status, basemap: 'error', buildings3dAvailable: false, message: 'No se pudo leer madrid.pmtiles; revisa el archivo local y sus metadatos.' };
      onStatus?.(updated);
    }
  });

  return {
    renderer: 'maplibre',
    status,
    ready,
    update(next) {
      const previousGallery = current.galleryId;
      current = { ...current, ...next };
      if (current.galleryId && current.galleryId !== previousGallery) void ensureGalleryCatalog(current.galleryId);
      applyCurrentData();
    },
    resize() {
      if (!destroyed && element.isConnected && element.clientWidth > 0 && element.clientHeight > 0) map.resize();
    },
    flyTo(candidate) {
      if (!candidate || destroyed) return;
      map.flyTo({
        center: [candidate.lon, candidate.lat],
        zoom: Math.max(map.getZoom(), 16.5),
        pitch: current.mode === '3d' ? 48 : 0,
        bearing: current.mode === '3d' ? map.getBearing() : 0,
        duration: reducedMotion() ? 0 : 650,
        essential: false,
      });
    },
    setMode(mode) {
      if (destroyed) return;
      current.mode = mode === '3d' && basemap.buildings3dAvailable ? '3d' : '2d';
      element.dataset.mapMode = current.mode;
      element.dataset.mapBuilding3dRenderedFeatureCount = current.mode === '3d' ? 'pending' : '0';
      map.easeTo({
        pitch: current.mode === '3d' ? 48 : 0,
        bearing: current.mode === '3d' ? (map.getBearing() || 18) : 0,
        duration: reducedMotion() ? 0 : 620,
        essential: false,
      });
      applyCurrentData();
      if (current.mode === '3d' && map.getLayer('madrid-buildings-3d')) {
        map.once('idle', () => {
          if (destroyed || current.mode !== '3d') return;
          const visible = map.queryRenderedFeatures({ layers: ['madrid-buildings-3d'] }).length;
          element.dataset.mapBuilding3dRenderedFeatureCount = String(visible);
        });
      }
    },
    setGallery(nextGalleryId) {
      if (!nextGalleryId || destroyed) return;
      current.galleryId = nextGalleryId;
      void ensureGalleryCatalog(nextGalleryId);
      applyCurrentData();
    },
    setBuildings(visible) {
      current.buildingsVisible = Boolean(visible);
      applyCurrentData();
    },
    setGrid(visible) {
      current.gridVisible = Boolean(visible);
      applyCurrentData();
    },
    reset() {
      if (destroyed) return;
      map.easeTo({ center: [(searchArea.bbox.west + searchArea.bbox.east) / 2, (searchArea.bbox.south + searchArea.bbox.north) / 2], zoom: 15, pitch: 0, bearing: 0, duration: reducedMotion() ? 0 : 620, essential: false });
    },
    north() {
      if (destroyed) return;
      map.easeTo({ bearing: 0, pitch: current.mode === '3d' ? 48 : 0, duration: reducedMotion() ? 0 : 420, essential: false });
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      for (const { marker } of rankedMarkers.values()) marker.remove();
      rankedMarkers.clear();
      map.remove();
    },
  };
}
