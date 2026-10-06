# Diseño de Fase 2: snapshot OSM reproducible

## Estado

La Fase 2 está **implementada y validada** con fixtures locales y con la primera
adquisición real autorizada de la bbox D004. El snapshot raw permanece fuera de
Git y está identificado por contenido. Las decisiones canónicas son D043-D048
de [DECISIONS.md](DECISIONS.md).

## Snapshot real de D004

La primera adquisición válida con la consulta limitada de D048 terminó en un
único intento HTTP 200:

| Campo | Valor observado |
|---|---|
| `osm_snapshot_id` | `osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141` |
| Raw SHA-256 | `f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141` |
| Tamaño raw | 8.420.815 bytes |
| Adquisición UTC | `2026-10-06T08:52:43.930134Z` |
| Endpoint | `https://overpass-api.de/api/interpreter` |
| Backend observado en el preflight | `gall.openstreetmap.de` |
| Query SHA-256 | `11b8fe8f8b781c2fbceb1e24def956321ff141ffe1e5b09ffa14d0ff4df36145` |
| Intentos / HTTP final | 1 / 200 |

Conteos registrados:

| Grupo | Conteos |
|---|---|
| Objetos | 25.537 nodes; 4.240 ways; 498 relations |
| Selección | 23.019 `node_bbox`; 4.240 `way_bbox_intersection`; 498 `relation_context` |
| Cierre de ways | 2.518 `added_way_nodes` |
| Members resueltos | 380 node; 1.594 way; 2 relation |
| Members no resueltos | 3.285 node; 10.167 way; 40 relation |

Los 25.537 nodes son exactamente los 23.019 seleccionados por bbox más los
2.518 añadidos para completar ways. Todos los `nd ref` de ways están resueltos.
Los `unresolved_relation_members` no indican corrupción: son referencias
esperables porque las 498 relations se conservan como contexto y
`closure.relations = not_expanded`. No se afirma que esas relations estén
completas.

La validación confirmó XML y provenance válidas, conteos coincidentes,
`sha256.txt` correcto, correspondencia entre `osm_snapshot_id` y SHA-256 raw,
publicación atómica y ausencia de temporales o locks residuales. Un acceso
posterior por `--snapshot-id`, sin habilitar red, produjo cache hit y conservó
idénticos los hashes de `source.osm`, `provenance.json` y `sha256.txt`.

## Alcance aprobado

- D043 fija Overpass como fuente primaria para una adquisición controlada de la
  bbox D004 y excluye su uso como dependencia query-time.
- D044 fija OSM XML como raw inmutable y prohíbe sobrescribir snapshots.
- D045 define los mínimos de integridad y provenance.
- D046 separa raw, derivados, imágenes, embeddings e índices y excluye el raw
  voluminoso de Git.
- D047 vincula catálogo y preselección al snapshot y excluye ground truth,
  imágenes, embeddings e índices de Fase 2.
- D048 fija endpoint configurable, consulta limitada, bordes, timeouts,
  reintentos, identidad content-addressed, escritura atómica y validación. La
  consulta inicial con clausura `>>` quedó sustituida antes de existir un
  snapshot real, después de intentos fallidos HTTP 429 y 504 que no demuestran
  causalidad pero sí motivaron revisar su expansión.

La bbox continúa siendo la definida en D004:

```yaml
north: 40.4200
south: 40.4120
east: -3.6990
west: -3.7090
```

## Flujo implementado

```text
configuración de adquisición versionada
  → consulta Overpass exacta para D004
  → respuesta OSM XML temporal
  → validación estructural y conteos
  → escritura atómica del raw inmutable
  → SHA-256 y tamaño
  → provenance
  → osm_snapshot_id
```

Las fases posteriores consumirán el raw local o derivados explícitos. No se
consultará Overpass durante cada petición de usuario.

## Contenido raw

La adquisición preserva nodes y ways locales, completa todos los nodes de esos
ways y conserva como contexto las relations que los referencian directamente.
No expande todos los members de relations ni subrelations; las referencias
ausentes son válidas y se contabilizan por tipo. No aplica un vocabulario
semántico ni filtra categorías por su utilidad prevista.

Los `nd ref` de ways siguen siendo obligatoriamente resolubles. Para relations,
los members conservan tipo, referencia y role; los objetos presentes se cuentan
como resueltos y los ausentes como `unresolved_relation_members` separados por
`node`, `way` y `relation`.

La provenance separa los conteos seleccionados como `node_bbox`,
`way_bbox_intersection` y `relation_context`, además de los nodes exteriores
añadidos para completar ways. El SHA-256 de la consulta corregida es
`11b8fe8f8b781c2fbceb1e24def956321ff141ffe1e5b09ffa14d0ff4df36145`.

## Almacenamiento

La organización conceptual fijada por D044-D048 es:

```text
data/raw/osm/snapshots/<osm_snapshot_id>/
  source.osm
  provenance.json

data/processed/osm/<osm_snapshot_id>/
  ... derivados posteriores ...
```

El raw y su provenance local no se incorporan a Git. Ningún derivado
sobrescribirá el raw.

## Provenance mínima

D045 exige registrar fuente, endpoint, UTC de adquisición, bbox, consulta,
formato, tamaño, SHA-256, versión del mecanismo, conteos, licencia, atribución y
resultado de la adquisición. La provenance no contendrá credenciales ni
convertirá una URL pública en autorización de redistribución.

## Licencia

Los datos OSM están bajo ODbL 1.0. Cualquier memoria o publicación deberá incluir
una atribución equivalente a:

> © OpenStreetMap contributors. Datos disponibles bajo la Open Database License
> (ODbL). https://www.openstreetmap.org/copyright

La publicación de raw o bases derivadas requerirá revisar las obligaciones del
artefacto concreto conforme a
[LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md).

## Fuera de alcance

Fase 2 no incluye:

- procesamiento geométrico de Fase 3;
- renderizado, tiles o imágenes OSM;
- CrossText2Loc o embeddings;
- índice geoespacial o preselección;
- LLM, GOTPR, VLM o diálogo;
- ground truth o datos de evaluación.

D007 permanece pendiente y no se modifica.

## Operación fijada

D048 es la referencia canónica para la consulta Overpass QL exacta, selección
`local`, completitud de ways, contexto parcial de relations, endpoint
configurable, timeouts, reintentos, formato de
`osm_snapshot_id`, publicación atómica y validaciones. Este documento no duplica
esos parámetros.

Antes de cualquier adquisición futura se deberá volver a comprobar la política
y disponibilidad vigentes del endpoint y obtener autorización de ejecución. La
publicación de provenance o derivados seguirá requiriendo la revisión ODbL de
D045-D046. El éxito de esta adquisición no autoriza nuevas llamadas de red.

## Materialización

- `config/madrid.yaml` contiene los parámetros operativos fijados por D048.
- `schemas/osm_snapshot.schema.json` define la provenance versionada.
- `src/tfg_phase0/osm_snapshot.py` genera la consulta, valida OSM XML, aplica la
  política de reintentos, construye la provenance y publica snapshots
  inmutables.
- `scripts/acquire_osm_snapshot.py` expone la adquisición y validó una
  adquisición real autorizada y un cache hit exclusivamente local.
- `tests/fixtures/osm/valid.osm` y `tests/test_phase2_osm_snapshot.py` validan el
  flujo sin Internet mediante transporte inyectado.

Los tests no invocan el transporte real. Cualquier nueva adquisición continúa
requiriendo una autorización separada.
