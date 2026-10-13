# Contrato de Fase 3: asociaciones geométricas OSM

## Estado y propósito

D050 fija el contrato global de Fase 3. Este documento describe su operación
prevista; **F3 todavía no está implementada** y no existen artefactos derivados
generados por ella.

F3 vinculará de forma reproducible las celdas de un catálogo F1 materializado
con los objetos de un snapshot F2 local. Materializa D022 y consume la política
de ways D049 sin incorporar interpretación lingüística, scoring o datos de
evaluación.

## Alcance

F3 debe:

1. consumir un manifest F1 ya materializado;
2. consumir exclusivamente un snapshot F2 local ya adquirido;
3. validar schemas, identidades, hashes y compatibilidad de los inputs;
4. leer nodes, ways y relations desde `source.osm`;
5. reconstruir geometrías completas de nodes y ways;
6. aplicar D049/`way_is_area-v1` a los ways;
7. trabajar en EPSG:25830 mediante la transformación de F1;
8. construir un índice espacial temporal;
9. asociar muchos-a-muchos geometrías elegibles y celdas por intersección;
10. calcular predicados y distancias neutrales;
11. propagar contexto parcial de relations un solo nivel;
12. producir un dataset canónico con provenance e integridad;
13. publicar el resultado de forma atómica e inmutable.

F3 no modifica F1 o F2, no genera candidatos, no usa red ni Overpass y no
incluye LLM, vocabularios de consulta, buffers, radios, fallback, scoring,
ground truth, imágenes, embeddings, CrossText2Loc o GOTPR. No resuelve D003 ni
D021.

## Estado de F3.3

F3.3 implementa la normalización y construcción geométrica. Proyecta las
coordenadas OSM mediante la transformación usada por F1 y construye Point para
nodes, LineString para ways lineales y Polygon para ways areales. Aplica D049,
valida las geometrías y asigna `geometry_role`, `geometry_status`,
`geometry_reason` y bbox métrica.

La etapa opera sobre `VerifiedF3Inputs` mediante
`src.tfg_phase0.f3_geometry.normalize_osm_geometries`. El resultado conserva las
geometrías Shapely solo en memoria y mantiene las relations como contexto sin
geometría. El diagnóstico interno `unrecognized_area_value` se conserva para
ways abiertos sin alterar el contrato serializado de `geometry_reason`. F3.3 no
construye índices ni asociaciones entre candidatos y OSM; esas operaciones
siguen pendientes para F3.4.

## Input F1

F3 recibe mediante una ruta explícita un manifest ya materializado y nunca lo
regenera implícitamente. Usa:

- `schema_version`, `manifest_id`, `region_id` y `catalog_version`;
- bbox, CRS, `spacing_m`, `cell_size_m`, `grid_hash` y versión del generador;
- provenance del manifest;
- `candidate_id`, centro y polígono de cada celda;
- `center_easting_m` y `center_northing_m`.

La validación comprueba el schema F1, SHA-256 y tamaño de los bytes exactos,
unicidad de `candidate_id`, valores finitos, celdas válidas, CRS esperado y
compatibilidad de región y bbox con F2. El path guardado en provenance es lógico
y relativo.

Conforme a D051, F3.2 exige manifests nuevos con
`provenance.input_hashes.f1_config` y
`provenance.code_version=phase1-manifest-v2`. El hash `f1_config` cubre solo
`schema_version` y los bloques efectivos `region` y `catalog` definidos por F1;
excluye `osm_acquisition`, `artifacts` y los valores configurables nulos de
spacing y tamaño. Estos últimos se registran con sus valores efectivos en
`generation` y `parameters_hash`. No existe fallback automático a la provenance
v1.

La celda métrica autoritativa se reconstruye como un cuadrado en EPSG:25830 a
partir de `center_easting_m`, `center_northing_m` y `cell_size_m`. El Polygon
WGS84 redondeado del manifest se utiliza para validar coherencia, no como fuente
primaria de la geometría métrica.

El manifest conserva `osm_snapshot_id=null`. La vinculación F1-F2 pertenece a
la provenance F3 y no modifica F1. Un manifest de 25 m y otro de 50 m producen
datasets F3 distintos sin decidir cuál es definitivo.

## Input F2

F3 recibe el directorio local:

```text
data/raw/osm/snapshots/<osm_snapshot_id>/
  source.osm
  provenance.json
  sha256.txt
```

Antes de procesarlo verifica schema, ID, hash y tamaño del raw, checksum,
conteos, región, bbox, selección y clausura. El contrato requiere:

```text
closure.ways = all_referenced_nodes
closure.relations = not_expanded
```

Todos los `nd ref` de ways deben estar presentes. Los members ausentes de
relations son válidos si coinciden con los conteos de provenance. F3 no habilita
transporte de red para completar el snapshot.

## Identidad OSM

La identidad es `(osm_type, osm_id)` y su representación derivada:

```text
osm_ref = "<osm_type>/<osm_id>"
```

El orden canónico es `node < way < relation`, seguido por ID numérico. Nodes y
ways aparecen en `osm_objects.jsonl`; las relations aparecen exclusivamente en
`relation_context.jsonl`.

## Nodes

Los nodes se clasifican por procedencia:

| `source_role` | Geometría | Asociación directa |
|---|---|---|
| `node_bbox` | Point | Sí |
| `added_way_node` | Point | No |

Un node dentro o sobre la bbox inclusiva es `node_bbox`, aunque también sea
member de un way. Los nodes exteriores añadidos para completar ways son
`added_way_node`: se inventarían como evidencia local si se asociaran
directamente, pero sus coordenadas sí forman parte de las geometrías de ways.

Los tags no determinan la elegibilidad de un `node_bbox`. IDs duplicados o
coordenadas ausentes, no finitas o fuera de rango invalidan el input.

## Ways

D049 produce los siguientes estados:

| Resultado | `geometry_role` | `geometry_status` | Asociable |
|---|---|---|---|
| `line` | `line` | `valid` | Sí |
| `area` | `area` | `valid` | Sí |
| `unknown_closed_way` | `none` | `not_associable` | No |
| `invalid_area` | `none` | `invalid` | No |
| `invalid_way_geometry` | `none` | `invalid` | No |

Una línea cerrada sigue siendo LineString. F3 no usa centroides, no repara
geometrías y no hereda semántica de relations. `geometry_reason` conserva una
razón versionada para estados no asociables o inválidos.

Enumeraciones iniciales:

```text
geometry_role: point | line | area | none
geometry_status: valid | not_associable | invalid

geometry_reason:
  added_way_node_direct_association_forbidden
  unknown_closed_way_no_votes
  unknown_closed_way_conflict
  unknown_closed_way_unrecognized_area_value
  invalid_area_open_way
  invalid_area_empty
  invalid_area_non_positive
  invalid_area_invalid_polygon
  invalid_way_geometry_missing_node
  invalid_way_geometry_too_few_positions
  invalid_way_geometry_non_finite_coordinate
```

## CRS y transformación

Predicados, bbox métricas y distancias se calculan en EPSG:25830. F3 reutiliza
exactamente `tfg_phase0.crs.wgs84_to_epsg25830`, sin introducir `pyproj`
silenciosamente.

La provenance registra nombre, versión y hash del código de transformación.
Los tests deben confirmar que F1 y F3 producen las mismas coordenadas métricas.
La implementación propia usa parámetros WGS84 y considera ETRS89/WGS84
equivalentes para la precisión del piloto; no se promete identidad universal
con PROJ.

## Shapely, GEOS y STRtree

Esta sección define la implementación espacial aceptada por D050. Para el
contraste con índices vectoriales opcionales y la referencia ilustrativa de
integración, véase [INDEXING_OPTIONS.md](INDEXING_OPTIONS.md).

Shapely 2.x y GEOS serán la única capa geométrica nueva. Deben aportar Point,
LineString, Polygon, validación, predicados, distancia y STRtree. No se
introducirán inicialmente GeoPandas, `rtree`, PyArrow, Parquet ni `pyproj`.

El preflight en CPython 3.12/Linux `aarch64` fijó `NumPy==2.5.4` y
`Shapely==2.1.2`. El wheel binario de Shapely incluye GEOS 3.13.1 y GEOS C API
1.19.2, sin compilación local ni dependencia de una copia GEOS del sistema.
Shapely y GEOS se registrarán en provenance y participarán en la identidad F3.

STRtree indexará las geometrías OSM asociables y se consultará una vez por celda
F1. Para cada consulta, los resultados se convierten a identidad OSM, se
deduplican, se ordenan y solo entonces se evalúan los predicados exactos. El
orden interno del índice nunca se persiste.

## Asociación y predicados

Una asociación existe si y solo si:

```text
osm_geometry.intersects(candidate_cell) == true
```

La relación es muchos-a-muchos. No hay nearest-only, ganador, desempate, buffer,
radio, score ni filtro semántico.

La dirección formal es `osm_geometry <predicate> candidate_cell`:

```text
contains = osm_geometry.contains(candidate_cell)
within = osm_geometry.within(candidate_cell)
crosses = osm_geometry.crosses(candidate_cell)
touches = osm_geometry.touches(candidate_cell)
overlaps = osm_geometry.overlaps(candidate_cell)
```

`intersects` siempre es verdadero en una fila persistida. Para geometrías
válidas de F3 v1, `boundary_contact_only == touches`: se deriva del predicado
topológico y no de bbox, epsilon o distancia aproximada.

Se incluyen Points interiores o sobre frontera; LineStrings que cruzan o solo
tocan borde o vértice; y Polygons contenidos, contenedores, solapados o en
contacto de frontera.

## Distancia

`center_distance_m` es la distancia en EPSG:25830 entre el Point formado por
`center_easting_m`/`center_northing_m` de F1 y la geometría OSM completa. No es
distancia a centroide y no filtra asociaciones.

Se persiste como número JSON redondeado a seis decimales, finito y no negativo.
Todo cero se normaliza a `0.0`; se prohíben NaN e infinitos. No se exige mostrar
seis posiciones decimales si los ceros finales no aportan información.

## Contexto parcial de relations

F3 no construye geometría de relations, no reconstruye multipolygons, no
descarga members, no hereda tags y no crea asociaciones directas
`candidate_id`-relation.

`relation_context.jsonl` contiene una fila por relation con al menos un member
node o way presente que tenga asociaciones directas. Conserva:

- `relation_id`, `relation_ref` y tags;
- `closure_status=not_expanded`;
- total y conteos de members presentes y ausentes por tipo;
- members presentes asociados, con tipo, ID, referencia y role;
- `candidate_ids` propagados desde cada member.

La propagación es de un solo nivel. Las relations sin members asociados se
omiten del fichero y se contabilizan en provenance. Una fila anidada por
relation evita duplicar tags y conteos; un SQLite plano podrá derivarse después.

## Outputs canónicos

```text
data/processed/osm/<osm_snapshot_id>/<f3_dataset_id>/
  osm_objects.jsonl
  candidate_osm_associations.jsonl
  relation_context.jsonl
  provenance.json
  sha256.txt
```

No se crea un manifest F1 enriquecido. SQLite y los índices persistentes son
derivados regenerables, no fuentes canónicas.

### `osm_objects.jsonl`

Una fila por node o way F2 con:

```text
osm_type, osm_id, osm_ref, tags, source_role,
geometry_role, geometry_status, geometry_reason,
is_closed para ways, metric_bbox cuando esté disponible
```

No duplica geometrías, WKT, WKB, GeoJSON ni listas completas de `nd ref`. La
geometría original se reconstruye desde el `source.osm` identificado en
provenance.

### `candidate_osm_associations.jsonl`

Una fila por clave única `(candidate_id, osm_type, osm_id)` con:

```text
candidate_id, osm_type, osm_id, osm_ref, geometry_role,
intersects, contains, within, crosses, touches, overlaps,
boundary_contact_only, center_distance_m
```

No duplica tags. El objeto debe existir en `osm_objects.jsonl`, estar marcado
como `valid` y ser asociable.

### `relation_context.jsonl`

Una fila por relation emitida con identidad, tags, clausura, conteos y una lista
ordenada de members asociados con sus `candidate_ids`.

## Provenance

`provenance.json` registra:

- `schema_version`, `contract_version`, `generator_version` y `f3_dataset_id`;
- manifest F1: path lógico, tamaño, SHA-256, identidad, granularidad, CRS y grid;
- snapshot F2: path lógico, ID, hash, tamaño, selección y clausura;
- D049: política, release, commit, fichero, hash y licencia;
- configuración: path lógico, schema y hashes exacto y canónico;
- geometría: CRS, transformación y políticas de asociación, relations e
  inválidos;
- software: código, Python, Shapely, GEOS, `platform_system` y
  `platform_machine`;
- serialización: encoding, orden, precisión y política de valores numéricos;
- conteos por tipo, procedencia, geometría, estado, asociaciones y relations.

No contiene paths absolutos, hostname, usuario, PID ni tiempos de ejecución.

## Identidad `f3_dataset_id`

Formato:

```text
f3-madrid-pilot-associations-sha256-<SHA256_IDENTIDAD>
```

El SHA-256 se calcula sobre JSON canónico del siguiente contenido lógico:

```text
contract_version
generator_version
catalog.manifest_sha256
catalog.manifest_id
osm.osm_snapshot_id
osm.raw_sha256
rules.policy
rules.sha256
config.canonical_sha256
geometry.projected_crs
geometry.transform_version
geometry.transform_source_sha256
geometry.association_predicate
geometry.predicate_direction
geometry.boundary_contact_policy
geometry.relation_policy
geometry.invalid_geometry_policy
software.generator_source_sha256
software.python_version
software.shapely_version
software.geos_version
serialization_version
```

No participan directamente:

```text
path absoluto, hostname, usuario, timestamp, duración,
orden de STRtree, número de cores, platform_system, platform_machine
```

`platform_system` y `platform_machine` sí se registran en
`provenance.software`. Describen el entorno experimental, pero no fragmentan por
sí solos la identidad lógica. Si dos plataformas con iguales inputs, reglas y
software producen bytes distintos, la divergencia será visible en los hashes de
outputs y deberá investigarse.

## Serialización y checksums

Los JSONL usan UTF-8 sin BOM, `ensure_ascii=false`, claves ordenadas, separadores
compactos, `allow_nan=false`, una fila por línea y newline final. El orden es:

- objetos: `node < way`, después `osm_id` numérico;
- asociaciones: `candidate_id`, `node < way`, `osm_id`;
- relations: `relation_id`;
- members: `node < way < relation`, `member_id`, `role`;
- `candidate_ids`: lexicográfico y sin duplicados;
- tags: clave lexicográfica.

`sha256.txt` contiene, en este orden, dos espacios entre hash y nombre y un
newline final:

```text
<SHA256>  osm_objects.jsonl
<SHA256>  candidate_osm_associations.jsonl
<SHA256>  relation_context.jsonl
<SHA256>  provenance.json
```

No incluye su propio hash.

El bundle canónico no contiene un `created_at_utc` variable. Puede conservar
timestamps fijos heredados de inputs. Los logs operativos con tiempos o duración
quedan fuera del bundle.

## Schemas previstos

Sin crearlos todavía, F3 necesitará:

```text
schemas/f3_osm_object.schema.json
schemas/f3_association.schema.json
schemas/f3_relation_context.schema.json
schemas/f3_provenance.schema.json
```

Los schemas validarán filas y provenance; un validador de dataset comprobará
unicidad, referencias cruzadas, conteos, orden y hashes.

### Validación manual en Python

Las invariantes estructurales que no quedan expresadas completamente mediante
JSON Schema se comprueban en `src/tfg_phase0/validation.py`. Los contratos F3 se
validan mediante `validate_document` y los nombres `f3_osm_object`,
`f3_association`, `f3_relation_context` y `f3_provenance`.

El validador manual comprueba:

- igualdad exacta de `osm_ref` con el tipo y el ID;
- compatibilidad de `source_role` con node o way;
- matriz exacta entre estado, rol y razón geométrica;
- tratamiento exacto de `added_way_node`;
- cierre obligatorio de `unknown_closed_way`;
- cierre compatible con cada razón `invalid_area`;
- bbox métrica finita y no invertida;
- `boundary_contact_only == touches`;
- distancia finita, rechazando NaN e infinitos;
- igualdad exacta de las referencias de relations y members;
- ausencia de members asociados duplicados;
- suma de conteos igual a `member_count`;
- associated members respaldados por el conteo presente de su tipo;
- `osm_snapshot_id` coherente con `raw_sha256`;
- paths lógicos relativos;
- reglas D049 exactas;
- políticas geométricas D050 exactas;
- serialización D050 exacta;
- conteos de provenance no negativos.

Estas comprobaciones son estructurales. F3.1 no valida todavía la existencia
real de candidatos u objetos, la geometría, los predicados, las distancias ni
el orden global de las filas JSONL.

## Publicación atómica

La generación seguirá esta secuencia:

1. validar inputs y calcular `f3_dataset_id`;
2. detectar cache hit o conflicto si ya existe el destino;
3. generar en un directorio temporal del mismo filesystem;
4. validar filas, invariantes y referencias cruzadas;
5. construir provenance y checksums;
6. releer y verificar todos los hashes;
7. sincronizar ficheros y directorio;
8. publicar con operación atómica no-replace y lock exclusivo;
9. sincronizar el directorio padre;
10. eliminar solo temporales propios ante error.

Un ID existente con hashes correctos es cache hit. Un ID existente incompleto o
inconsistente es error y no se repara ni sobrescribe automáticamente.

## Tests previstos

### Unitarios

- identidad y orden OSM;
- roles de nodes;
- D049 y estados de ways;
- transformación coherente con F1;
- geometrías válidas e inválidas;
- predicados, bordes y distancia;
- serialización, Unicode, floats, `-0.0`, NaN e infinitos;
- identidad F3 y orden independiente de STRtree.

### Integración

- validación F1/F2 y rechazo de hashes o regiones incompatibles;
- muchos-a-muchos y objetos multi-cell;
- relations parciales;
- outputs byte-identical en el entorno fijado;
- checksums, cache hit, conflicto y publicación atómica;
- cero red e inputs F1/F2 de solo lectura;
- manifests de 25 m y 50 m sin resolver D003.

### Snapshot real

Tras completar implementación y fixtures se validarán conteos, estados D049,
asociaciones, contexto de relations, repetición byte-identical y recursos sobre
el snapshot F2 local. Esta validación no forma parte del diseño documental.

## Riesgos

- diferencias de predicados o validación entre versiones de GEOS;
- sensibilidad numérica cerca de fronteras;
- transformación propia no idéntica universalmente a PROJ;
- tabla D049 histórica e incompleta;
- crecimiento del número de asociaciones para objetos extensos;
- menor eficiencia de consumo por no duplicar geometrías completas;
- contexto limitado por relations no expandidas;
- obligaciones ODbL si se publica el derivado.

El contrato exige determinismo para una identidad algorítmica fijada, pero no
promete igualdad byte a byte universal entre plataformas.
