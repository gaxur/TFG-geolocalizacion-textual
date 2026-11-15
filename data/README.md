# Datos locales (no versionados)

Los datos pesados permanecen fuera de Git. El repositorio contiene únicamente
documentación, configuración y contratos; la PGX mantiene localmente los
artefactos materializados de F1–F4.

| Carpeta | Uso previsto |
|---|---|
| `cvg_text/` | Anotaciones e imágenes originales utilizadas en la reproducción de Nueva York |
| `madrid/` | Espacio reservado para datasets de evaluación de Madrid |
| `processed/catalog/` | Manifiestos locales de candidatos de 25 m y 50 m |
| `processed/visual/` | Bundles locales de imágenes OSM precalculadas |
| `embeddings/` | Matrices visuales CrossText2Loc precalculadas |
| `processed/map-assets/` | GeoJSON canónico de celdas y, cuando se valide, PMTiles locales para el frontend |

Los snapshots OSM raw de Fase 2 se almacenan localmente bajo
`raw/osm/snapshots/<osm_snapshot_id>/`; están ignorados por Git. Cada directorio
contendrá `source.osm`, `provenance.json` y `sha256.txt`. Los derivados se
mantendrán separados bajo `processed/osm/<osm_snapshot_id>/`.

F4 conserva su fuente de render independiente bajo
`raw/osm/f4_sources/<source_id>/`, los recursos cartográficos bajo
`raw/osm/f4_renderer/` y los bundles visuales content-addressed bajo
`processed/visual/<visual_dataset_id>/`. Todos permanecen fuera de Git. Cada
bundle enlaza por hash F1, fuente OSM, renderer, estilo, assets, fuentes e
imágenes.

El despliegue integrado `compose.mvp.yaml` monta el proyecto completo en solo
lectura para la API y sirve los recursos cartográficos locales desde el Nginx
frontend. La API consume las rutas exactas declaradas por
`config/madrid_f46_retriever.json`: manifiestos del catálogo, selecciones,
bundles visuales y bundles de embeddings de 25 m y 50 m. No importa OSM, no
genera PMTiles ni recalcula embeddings durante el arranque. El wrapper
`scripts/run_mvp3_stack.sh` falla antes de crear el stack si falta alguno de esos
artefactos. Véase [MVP.md](../docs/MVP.md).

El GeoJSON del mapa se genera offline mediante `scripts/build_madrid_map_assets.py`
y queda en `processed/map-assets/`, carpeta fuera de Git. Si se usa un manifest
F4 local, el builder valida su hash contra la selección comprometida y contrasta
cada geometría con la cuadrícula F1 actual. El modo `--regenerate-grid` solo
materializa F1 y registra `osm_snapshot_id: null`; no crea ni repara datos F4.

El checkout local conserva el snapshot F2 y la fuente PBF F4 bajo las rutas
`raw/osm/snapshots/<osm_snapshot_id>/` y
`raw/osm/f4_sources/madrid-geofabrik-20261014/`, ambos fuera de Git. El PMTiles
`processed/map-assets/madrid.pmtiles` se genera offline desde el PBF F4 y su
provenance está en `madrid.pmtiles.provenance.json`. Usa OSM/ODbL 1.0, bbox D004
con 250 m de margen proyectado y solo etiquetas numéricas `height` explícitas
para extrusiones; `building:levels` no se convierte a metros. Nginx sirve el
archive por Range desde el volumen read-only existente.

## Bundles obligatorios del MVP

| Galería | Visual | Embeddings |
|---|---|---|
| 50 m | `processed/visual/f4-madrid-visual-sha256-15310268e0fed30180085c7ec1f14fce696c4ba94e83bf9727970451cc82f564/` | `embeddings/f4-madrid-embeddings-sha256-199dae0e3eb38b206004557f20fae0ef98f620621458fc64c2dfa3f7ef7f84c1/` |
| 25 m | `processed/visual/f4-madrid-visual-sha256-ebe6c91b8ed5600d65c3021a53c768d6e65545777efda92d7b171f705a0d42e9/` | `embeddings/f4-madrid-embeddings-sha256-2874609b95005b65823ce6efb5b7888b9d1500b7ec2f6ba301dfc3083cb56c2a/` |

Las rutas de la tabla son relativas a `data/`. También deben existir
`processed/catalog/manifest-50m.json` y `processed/catalog/manifest-25m.json`.
Estos directorios no se crean manualmente vacíos: deben conservar el contenido y
los manifests producidos y validados por F4.

Las rutas efectivas del loader oficial se configuran en el `config.yaml` del
clon local de CVG-Text y no se presuponen iguales a la disposición interna de
ningún ZIP. Documentar la procedencia, licencia, revisión y hashes de los
artefactos adquiridos en [EXPERIMENTS.md](../docs/EXPERIMENTS.md).
