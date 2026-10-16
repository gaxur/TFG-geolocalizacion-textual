import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const DEFAULT_CENTER = [40.416, -3.704];
const DEFAULT_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const DEFAULT_ATTRIBUTION = '&copy; OpenStreetMap contributors';

export function createResultsMap({ element, retrievals, selectedKey, view, onSelect, onViewChange }) {
  if (!element) return null;
  const map = L.map(element, { zoomControl: true, attributionControl: true });
  const tileUrl = import.meta.env?.VITE_TILE_URL ?? DEFAULT_TILE_URL;
  const attribution = import.meta.env?.VITE_TILE_ATTRIBUTION ?? DEFAULT_ATTRIBUTION;
  if (tileUrl) L.tileLayer(tileUrl, { maxZoom: 19, attribution }).addTo(map);
  else element.classList.add('map-without-tiles');

  const bounds = [];
  const markers = new Map();
  for (const retrieval of retrievals) {
    for (const candidate of retrieval.results) {
      const selected = candidate.key === selectedKey;
      const marker = L.circleMarker([candidate.lat, candidate.lon], {
        radius: selected ? 11 : candidate.rank === 1 ? 9 : 7,
        weight: selected ? 4 : 2,
        color: candidate.rank === 1 ? '#173f35' : '#537565',
        fillColor: selected ? '#173f35' : '#ffffff',
        fillOpacity: 1,
        className: `candidate-marker rank-${candidate.rank}`,
      }).addTo(map);
      const tooltip = document.createElement('span');
      tooltip.textContent = `${candidate.rank}. ${candidate.id}`;
      marker.bindTooltip(tooltip, { direction: 'top' });
      marker.on('click', () => onSelect(candidate.key));
      markers.set(candidate.key, marker);
      bounds.push([candidate.lat, candidate.lon]);
    }
  }
  if (view) map.setView(view.center, view.zoom);
  else if (bounds.length > 1) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 18 });
  else if (bounds.length === 1) map.setView(bounds[0], 18);
  else map.setView(DEFAULT_CENTER, 15);
  map.on('moveend', () => onViewChange?.({ center: [map.getCenter().lat, map.getCenter().lng], zoom: map.getZoom() }));
  queueMicrotask(() => map.invalidateSize());
  return { destroy: () => map.remove(), invalidateSize: () => map.invalidateSize(), markers };
}
