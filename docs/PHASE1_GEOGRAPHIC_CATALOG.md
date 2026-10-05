# Fase 1: modelo geográfico y manifest de Madrid

## Alcance

La Fase 1 implementa exclusivamente la construcción determinista del catálogo
geométrico para la bbox piloto D004. No descarga OSM, no genera imágenes, no
calcula embeddings, no ejecuta CrossText2Loc y no utiliza ground truth.

```text
bbox WGS84
  -> proyección EPSG:25830
  -> cuadrícula métrica
  -> centros y celdas
  -> centros y geometrías WGS84
  -> candidate_id estable
  -> manifest versionado
```

## Configuración

La fuente es [`config/madrid.yaml`](../config/madrid.yaml):

- región `madrid_pilot`;
- norte `40.4200`, sur `40.4120`, este `-3.6990`, oeste `-3.7090`;
- entrada y salida geográfica `EPSG:4326`;
- construcción métrica `EPSG:25830`;
- versión `madrid-pilot-grid-v1`;
- prefijo de candidatos `MADP`;
- política de borde `full_cell_within_bbox`.

`candidate_spacing_m` y `cell_size_m` permanecen `null` en la configuración
base. El usuario debe indicar `--spacing-m`; si omite `--cell-size-m`, el lado
de cada celda toma el mismo valor que el spacing. Esto permite generar 25 m y
50 m sin cambiar código ni convertir D003 en una decisión definitiva.

## Cuadrícula y bordes

Las cuatro esquinas de la bbox WGS84 se proyectan a EPSG:25830 y definen el
sobre métrico inicial. Los centros se recorren de sur a norte y, dentro de cada
fila, de oeste a este. Cada celda es un cuadrado en EPSG:25830.

Solo se incluyen celdas cuyo centro y cuatro vértices, transformados de nuevo a
WGS84, están dentro de los límites D004. No se recortan celdas en el borde ni se
crean candidatos con centro fuera del piloto. Esta regla puede dejar una franja
inferior al tamaño de celda sin cubrir junto a los límites.

## Identidad

El formato físico de Fase 1 es:

```text
<PREFIX>_<CATALOG_VERSION>_G<grid-hash>_S<spacing>_L<cell-size>_R<row>_C<column>
```

Ejemplo:

```text
MADP_MADRID_PILOT_GRID_V1_G<12-HEX>_S025_L025_R0003_C0012
```

Los índices se refieren al grid proyectado antes del filtrado de borde. El ID
depende únicamente de versión, bbox, CRS, algoritmo, spacing, tamaño, fila y
columna. El hash corto identifica esos parámetros de grid y evita reutilizar un
ID si cambia su geometría. No depende de imágenes, embeddings, `scene_id`,
timestamps, memoria o datos de evaluación.

## Manifest

El manifest cumple [`schemas/manifest.schema.json`](../schemas/manifest.schema.json)
y contiene:

- identidad y versión del catálogo;
- bbox, CRS, spacing, tamaño, política de borde y orden;
- provenance con hash canónico de configuración y parámetros;
- centro WGS84 por candidato;
- polígono WGS84 de cada celda;
- fila, columna y centro EPSG:25830;
- referencias futuras a imágenes, embeddings y scenes como `null`;
- `osm_snapshot_id: null`, porque Fase 2 todavía no ha comenzado.

No contiene OSM, imágenes, embeddings, consultas, ground truth ni etiquetas
humanas.

## Generación

Manifest de 25 m:

```bash
python3 scripts/generate_madrid_catalog.py \
  --spacing-m 25 \
  --output data/processed/catalog/manifest-25m.json
```

Manifest de 50 m:

```bash
python3 scripts/generate_madrid_catalog.py \
  --spacing-m 50 \
  --output data/processed/catalog/manifest-50m.json
```

Las comprobaciones locales produjeron:

| Spacing y lado | Candidatos | Tamaño JSON | SHA-256 |
|---|---:|---:|---|
| 25 m | 1115 | 666713 bytes | `14584d8b7e54faa5c99779862dbb9bd6adba40a6eff528c60760e181cae3ec7f` |
| 50 m | 253 | 151837 bytes | `ae4e954d0a6279f89d00bdf387fecfd65c88a6869f4f4f31c49c7d7424497cce` |

Se generaron en una ubicación temporal para validar tamaño y determinismo. No se
añaden al repositorio porque 25 m frente a 50 m continúa pendiente en D003; el
manifest definitivo se elegirá después del experimento correspondiente.

## Dependencias y precisión

La implementación usa únicamente la biblioteca estándar de Python. Las
transformaciones UTM siguen las ecuaciones WGS84 para la zona 30N; en el área
piloto ETRS89 y WGS84 se consideran equivalentes a la precisión requerida por
una cuadrícula de decenas de metros. Los tests contrastan un punto de referencia
y el round-trip numérico. `jsonschema==4.26.0` es una dependencia exclusiva de
desarrollo para contrastar el manifest con el schema publicado; no participa en
la generación.

## Validación

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest tests.test_phase0 tests.test_phase1_catalog
```

Los tests cubren bbox, ambas transformaciones, round-trip, grid no vacío,
unicidad y determinismo de IDs, determinismo de catálogo y serialización,
spacing 25/50, límites, contrato del manifest, campos futuros nulos y ausencia
de dependencia de ground truth.

## Próximo paso

La siguiente fase es Fase 2, adquisición y caché de un snapshot OSM con
procedencia. No se inicia como parte de esta implementación.
