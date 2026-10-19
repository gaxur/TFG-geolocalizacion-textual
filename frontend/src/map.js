import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const DEFAULT_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const DEFAULT_ATTRIBUTION = '&copy; OpenStreetMap contributors';

function galleryCellSize(galleryId) {
  const match = /-(25|50)m$/.exec(galleryId);
  if (!match) throw new TypeError(`Galería sin tamaño de celda reconocido: ${galleryId}`);
  return Number(match[1]);
}

function cellBounds(latitude, longitude, sizeM) {
  const half = sizeM / 2;
  const latitudeDelta = half / 111_320;
  const longitudeDelta = half / (111_320 * Math.cos(latitude * Math.PI / 180));
  return L.latLngBounds(
    [latitude - latitudeDelta, longitude - longitudeDelta],
    [latitude + latitudeDelta, longitude + longitudeDelta],
  );
}

export function createResultsMap({ element, retrievals, selectedKey, view, searchArea, onSelect, onViewChange }) {
  if (!element) return null;
  const areaBounds = L.latLngBounds(
    [searchArea.bbox.south, searchArea.bbox.west],
    [searchArea.bbox.north, searchArea.bbox.east],
  );
  const map = L.map(element, { zoomControl: false, attributionControl: true, maxBounds: areaBounds, maxBoundsViscosity: 1 });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  const tileUrl = import.meta.env?.VITE_TILE_URL ?? DEFAULT_TILE_URL;
  const attribution = import.meta.env?.VITE_TILE_ATTRIBUTION ?? DEFAULT_ATTRIBUTION;
  if (tileUrl) L.tileLayer(tileUrl, { maxZoom: 19, attribution }).addTo(map);
  else element.classList.add('map-without-tiles');
  L.rectangle(areaBounds, { color: '#dc2626', weight: 3, opacity: .95, fillColor: '#ef4444', fillOpacity: .055, dashArray: '8 6', lineCap: 'round', interactive: false, className: 'evaluation-boundary' }).addTo(map);

  const markers = new Map();
  const cells = new Map();
  for (const retrieval of retrievals) {
    const cellSize = galleryCellSize(retrieval.galleryId);
    for (const candidate of retrieval.results) {
      const selected = candidate.key === selectedKey;
      const cell = L.rectangle(cellBounds(candidate.lat, candidate.lon, cellSize), {
        color: selected ? '#0f513d' : '#2f7d64',
        weight: selected ? 3 : 1.5,
        opacity: selected ? .95 : .72,
        fillColor: selected ? '#2a8b68' : '#56a88a',
        fillOpacity: selected ? .26 : .12,
        className: `candidate-cell ${selected ? 'selected' : ''}`,
      }).addTo(map);
      const marker = L.marker([candidate.lat, candidate.lon], {
        icon: L.divIcon({
          className: 'candidate-marker-shell',
          html: `<span class="candidate-marker ${selected ? 'selected' : ''} ${candidate.rank === 1 ? 'top-result' : ''}"><span>${candidate.rank}</span></span>`,
          iconSize: [34, 34],
          iconAnchor: [17, 17],
        }),
        keyboard: true,
        title: `Candidato ${candidate.rank}`,
      }).addTo(map);
      const tooltip = document.createElement('span');
      tooltip.textContent = `${candidate.rank}. ${candidate.id}`;
      marker.bindTooltip(tooltip, { direction: 'top' });
      marker.on('click', () => onSelect(candidate.key));
      cell.on('click', () => onSelect(candidate.key));
      markers.set(candidate.key, marker);
      cells.set(candidate.key, cell);
    }
  }
  map.fitBounds(areaBounds, { animate: false });
  const minimumZoom = map.getZoom();
  map.setMinZoom(minimumZoom);
  if (view) map.setView(view.center, Math.max(view.zoom, minimumZoom));
  map.on('moveend', () => onViewChange?.({ center: [map.getCenter().lat, map.getCenter().lng], zoom: map.getZoom() }));
  queueMicrotask(() => map.invalidateSize());
  return { destroy: () => map.remove(), invalidateSize: () => map.invalidateSize(), markers, cells };
}
