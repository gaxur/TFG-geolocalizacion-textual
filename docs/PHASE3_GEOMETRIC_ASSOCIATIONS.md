# Contrato de Fase 3: asociaciones geométricas OSM

## Estado y propósito

D050 fija el contrato global de Fase 3. F3 está implementada, materializada y
cerrada para uso interno y continuidad técnica hacia F4. El acta de aceptación,
los riesgos asumidos y las reservas de distribución están en
[PHASE3_CLOSURE.md](PHASE3_CLOSURE.md).

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

## Descomposición de la Fase 3

La implementación de F3 se divide en etapas pequeñas para separar los contratos,
la lectura de inputs, la geometría, la asociación y la publicación. Una etapa no
debe adelantar responsabilidades de las siguientes.

### F3.1: contratos, schemas y validación estructural

Define la forma de los cuatro documentos estructurados de F3:
`osm_objects.jsonl`, `candidate_osm_associations.jsonl`,
`relation_context.jsonl` y `provenance.json`. Incluye sus JSON Schema, el
vocabulario cerrado de estados y razones, fixtures sintéticas y validadores
manuales para las invariantes entre campos que JSON Schema no expresa por sí
solo.

F3.1 no interpreta XML OSM ni construye geometrías. Esta etapa está
implementada y validada con tests.

### F3.2: preparación y verificación de inputs

Carga un manifest F1 indicado mediante un path explícito, valida un snapshot F2
exclusivamente local y comprueba el recurso de reglas D049. También parsea
`source.osm` en estructuras inmutables que conservan candidates, nodes, orden de
referencias de ways, relations, members, tags, roles y presencia de referencias.

Su salida es una representación interna verificada y no geométrica para F3.3.
No materializa un manifest real, no aplica `way_is_area-v1`, no crea outputs F3
y no dispone de fallback de red. La selección de un manifest de 25 m o 50 m es
explícita y no resuelve D003.

### F3.3: normalización y construcción geométrica

Proyecta las coordenadas OSM mediante la transformación usada por F1 y construye
Point para nodes, LineString para ways lineales y Polygon para ways areales.
Aplica D049, valida las geometrías y asigna
`geometry_role`, `geometry_status`, `geometry_reason` y bbox métrica.

Esta etapa está implementada sobre `VerifiedF3Inputs` mediante
`src.tfg_phase0.f3_geometry.normalize_osm_geometries`. El resultado conserva las
geometrías Shapely solo en memoria y mantiene las relations como contexto sin
geometría. El diagnóstico interno `unrecognized_area_value` se conserva para
ways abiertos sin alterar el contrato serializado de `geometry_reason`. No
construye todavía asociaciones entre candidatos y OSM.

### F3.4: índice espacial y asociaciones

Está implementada en `src.tfg_phase0.f3_associations`. Construye cada celda
cuadrada exclusivamente desde su centro EPSG:25830 y `cell_size_m`, e indexa en
un STRtree temporal solo las geometrías OSM asociables. Para cada celda resuelve
los índices enteros devueltos por Shapely contra una secuencia estable, elimina
duplicados, ordena por identidad OSM y aplica la intersección exacta
muchos-a-muchos.

También calcula los predicados neutrales y `center_distance_m` desde el centro
de la celda hasta la geometría OSM completa. La salida permanece en memoria,
ordenada por `candidate_id`, tipo OSM e ID. No aplica buffers, radios,
nearest-only, desempates, scoring ni semántica de consulta, y no serializa los
outputs finales de F3.

La integración real sobre el snapshot
`osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141`
indexó 26.546 geometrías. El catálogo de 25 m produjo 30.118 asociaciones para
1.115 candidatos; el de 50 m produjo 23.808 para 253 candidatos. Una muestra
determinista de candidatos de cada resolución coincidió exactamente con una
búsqueda exhaustiva. Estos conteos describen la ejecución observada y no
resuelven D003 ni D021.

### F3.5: contexto parcial de relations

Está implementada en `src.tfg_phase0.f3_relations`. Propaga, en un solo nivel,
los `candidate_id` de nodes y ways presentes que tengan asociaciones directas
hacia las relations que los referencian. Conserva tags, roles y conteos de todas
las entradas member presentes y ausentes.

No reconstruirá geometrías de relations o multipolygons, no descargará members
ausentes y no creará asociaciones directas entre candidates y relations.

Las entradas member repetidas con igual `(member_type, ref, role)` cuentan por
separado en `member_count` y en los conteos por presencia, pero se agrupan en un
único `associated_member`, como exige el contrato sin duplicados. Los roles
distintos permanecen separados. Relations member presentes o ausentes solo se
contabilizan: no propagan candidatos y no permiten transitividad.

En la integración real, ambas resoluciones conservaron las 498 relations y los
conteos F2: 380 nodes, 1.594 ways y 2 relations presentes; 3.285 nodes, 10.167
ways y 40 relations ausentes. El catálogo de 25 m emitió 210 relations, 1.058
members asociados y 3.918 apariciones de `candidate_id`; el de 50 m emitió 196,
945 y 2.122, respectivamente. Se agruparon una entrada duplicada asociada en 25
m y ninguna en 50 m; las demás entradas duplicadas del snapshot no tenían
asociación directa en esas ejecuciones. Estos resultados no resuelven D003.

### F3.6: serialización, identidad y provenance

Está implementada en `src.tfg_phase0.f3_identity`,
`src.tfg_phase0.f3_serialization`, `src.tfg_phase0.f3_validation` y
`src.tfg_phase0.f3_bundle`. Ordena y serializa los tres JSONL canónicos,
construye el objeto de identidad de `f3_dataset_id`, genera `provenance.json` y
calcula `sha256.txt`. Aplica UTF-8, JSON compacto, orden canónico, redondeo
métrico `ROUND_HALF_EVEN`, normalización de `-0.0` y rechazo de valores no
finitos.

La decisión D052 fija el preimage JSON exacto de la identidad, la proyección
`f3-config-v1`, el manifiesto cerrado `f3-generator-source-v1`, el hash de los
bytes de `crs.py`, el redondeo `ROUND_HALF_EVEN`, los JSONL vacíos de cero bytes
y la publicación Linux mediante `renameat2(RENAME_NOREPLACE)` sin fallback.

Esta etapa no añadirá timestamps variables al bundle canónico. Las versiones de
Python, NumPy, Shapely y GEOS participarán en la identidad; `python_implementation`,
`platform_system` y `platform_machine` se conservarán únicamente en provenance.
Un bundle válido de otra plataforma podrá ser cache hit, mientras que un destino
incompleto o incoherente será conflicto y nunca se sobrescribirá.

La validación integral relee los bytes, comprueba checksums, schemas, orden,
unicidad, referencias cruzadas, conteos e identidad. La publicación usa un
temporal en el mismo filesystem, lock exclusivo, `fsync` y
`renameat2(RENAME_NOREPLACE)`. F3.6 se ha validado solo con fixtures y
directorios temporales; la generación de bundles reales queda reservada a F3.8.

### F3.7: pruebas completas

Está implementada mediante pruebas unitarias, integración multiproceso y
comprobaciones específicas de Linux. Cubre corrupción con checksums
recalculados, escrituras parciales, fallos de `write`, `flush`, `fsync` y
`renameat2`, interrupciones capturables, carreras de destino, locks
preexistentes o abandonados y publicaciones concurrentes del mismo ID y de IDs
distintos.

El endurecimiento derivado garantiza escritura completa, valida cada fichero
desde un único descriptor con `O_NOFOLLOW` y `fstat`, informa explícitamente de
filesystems sin `fsync` de directorio y conserva el error principal si también
falla la retirada del lock. La revalidación aplica la misma apertura segura a
los inputs y usa una única instantánea de bytes para comprobar la configuración
exacta y efectiva. La prueba Linux real confirma una colisión
`RENAME_NOREPLACE` sin alterar fuente ni destino, además de publicación normal,
validación integral, cache hit y ausencia de residuos tras una ejecución normal.

Una terminación no capturable puede dejar un temporal o lock abandonado. D052
prohíbe romper ese lock automáticamente: su retirada sigue siendo una operación
manual tras comprobar que no existe un escritor activo. Estas pruebas no
demuestran durabilidad ante pérdida eléctrica ni las garantías de filesystems
remotos; ambas requieren validar el filesystem operativo antes de F3.8. La
lectura por descriptor evita que una sustitución posterior de la ruta redirija
los bytes ya abiertos, pero no impide que otro proceso con permisos modifique el
bundle visible durante o después de validarlo. También permanece una ventana
entre la última revalidación de inputs y código y el rename final; F3 presupone
inputs y bundles inmutables y no introduce un protocolo nuevo de bloqueo para
actores externos.

### F3.8: generación real

Está implementada mediante `scripts/materialize_f3_bundle.py`, que recibe un
manifest F1 explícito y el snapshot F2 local, ejecuta el pipeline F3.2-F3.6 y
una validación integral posterior, apoyándose en la campaña F3.7 previamente
superada. Registra fuera del bundle tiempos, tamaños, hashes, pico RSS, commit,
estado Git y hash del propio entrypoint. No contiene una selección implícita de
resolución ni rutas de red.

El 14 de octubre de 2026 se publicaron y validaron los bundles reales de 50 m y
25 m sobre el snapshot F2 `f2152555...`. Ambos reprodujeron los conteos ya
observados en F3.4/F3.5 y una segunda ejecución completa fue cache hit sin
alterar hashes, tamaños o mtimes de los cinco archivos canónicos.

| Resolución | `f3_dataset_id` | Candidatos | Asociaciones | Relations | Tamaño |
|---|---|---:|---:|---:|---:|
| 50 m | `f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453` | 253 | 23.808 | 196 | 18.744.138 B |
| 25 m | `f3-madrid-pilot-associations-sha256-902e8edcd7892c4b9f6a686a6573fb5c15bf19858ecf2ce14d09fb687e9e0ffa` | 1.115 | 30.118 | 210 | 20.917.604 B |

Los bundles y los informes JSON operativos permanecen fuera de Git. Materializar
ambas resoluciones no cierra D003; conserva dos alternativas para evaluación.
Los informes solo pueden publicarse sin reemplazo bajo `results/generated/f3/`:
se rechazan aliases de inputs, snapshots, outputs, destinos existentes y rutas
con ancestros inválidos antes de ejecutar el pipeline. La raíz de informes se
debe crear de forma explícita antes de ejecutar el entrypoint y se abre
componente a componente con `O_DIRECTORY|O_NOFOLLOW`; su descriptor se
mantiene durante toda la ejecución y la creación, enlace, limpieza y `fsync` se
realizan respecto al mismo `dir_fd`. El contenido se escribe en un inode anónimo
creado con `O_TMPFILE` y se publica directamente desde su descriptor mediante
`linkat(AT_EMPTY_PATH)`, sin nombre temporal que otro proceso pueda sustituir.
Así, cambiar posteriormente la ruta léxica no redirige la publicación.

El informe distingue publicación visible de durabilidad confirmada. Si el hard
link final existe pero falla el `fsync` del directorio, el error conserva
`report_published=true` y `durability_unknown=true`; no elimina el informe ni
recomienda reutilizar el mismo nombre. La trazabilidad Git y el hash del
entrypoint se capturan antes de cargar F1/F2. Una ruta externa con permisos puede
modificar un bundle después de validarlo, y la ventana entre la última
revalidación y el rename continúa siendo un riesgo residual documentado.

### F3.9: validación y cierre

Revisó los conteos reales, objetos ambiguos o inválidos, asociaciones multi-cell,
relations propagadas, hashes, consumo de recursos y repetibilidad. La revisión
acepta los dos bundles para uso interno y continuidad técnica; la distribución
pública del snapshot o de los bundles continúa pendiente de una revisión ODbL
del paquete concreto.

El cierre documentado en [PHASE3_CLOSURE.md](PHASE3_CLOSURE.md) acredita que el
dataset se generó conforme a D049, D050 y D052. No resuelve D003, D021 ni el
rendimiento de las etapas de recuperación posteriores.

### Por qué se separan F3.6, F3.7, F3.8 y F3.9

Estas etapas convierten un resultado geométrico en un artefacto científico
reproducible de forma progresiva. Separarlas evita confundir cuatro preguntas
distintas: cómo representar el resultado, si la publicación resiste fallos, qué
ocurre al ejecutarla sobre Madrid y si el resultado real puede darse por
cerrado.

| Etapa | Por qué es necesaria | Ventaja principal |
|---|---|---|
| F3.6: identidad, serialización y publicación | Los inventarios en memoria de F3.3-F3.5 no bastan para compartir, reutilizar o auditar un dataset. Es necesario fijar bytes, orden, hashes, provenance e identidad antes de generar resultados reales. | Produce bundles deterministas, autocontenidos y verificables. Permite detectar corrupción, distinguir configuraciones y reutilizar un resultado válido mediante cache hit sin sobrescribirlo. |
| F3.7: robustez y recuperación ante fallos | Una publicación correcta en el caso ideal no demuestra seguridad ante escrituras parciales, concurrencia, interrupciones, symlinks, locks abandonados o filesystems incompatibles. | Reduce el riesgo de aceptar bundles parciales o mezclar ejecuciones. Demuestra que los fallos se detectan explícitamente, que los destinos existentes no se reemplazan y que solo se limpian recursos propios. |
| F3.8: materialización real | Los tests sintéticos no prueban por sí solos que los contratos soporten el volumen, los conteos y las particularidades del snapshot real de Madrid. | Genera los dos datasets utilizables de 25 m y 50 m, mide recursos, confirma los conteos reales y comprueba repetibilidad y cache hit sobre los inputs efectivos, sin usar red ni modificar F1/F2. |
| F3.9: validación y cierre | Que un programa termine sin error no basta para cerrar una fase de datos. Es necesario revisar los resultados observados, sus anomalías, sus obligaciones de publicación y sus límites metodológicos. | Separa la generación de la aceptación científica. Permite documentar incidencias, justificar los artefactos finales y evitar que resultados no revisados pasen silenciosamente a recuperación o evaluación. |

El orden también reduce el coste de corregir errores. Un defecto de formato se
resuelve en F3.6 antes de crear datos reales; un defecto de atomicidad se detecta
en F3.7 antes de comprometer artefactos; F3.8 se limita a ejecutar un pipeline ya
probado; y F3.9 puede centrarse en interpretar y cerrar resultados, no en cambiar
silenciosamente el generador. Esta separación mantiene además fuera de los
bundles canónicos los tiempos, logs e informes operativos, que son útiles para
auditar una ejecución pero no deben alterar `f3_dataset_id`.

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

### Cómo interpretar el directorio generado

El primer nivel, `<osm_snapshot_id>`, identifica los bytes exactos del mapa OSM
de partida. Los dos directorios `<f3_dataset_id>` materializados dentro de ese
snapshot corresponden a los catálogos F1 de 50 m y 25 m:

| Resolución | Identificador del bundle | Candidatos | Asociaciones |
|---|---|---:|---:|
| 50 m | `f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453` | 253 | 23.808 |
| 25 m | `f3-madrid-pilot-associations-sha256-902e8edcd7892c4b9f6a686a6573fb5c15bf19858ecf2ce14d09fb687e9e0ffa` | 1.115 | 30.118 |

Ambos bundles parten del mismo snapshot y, por ello, contienen el mismo
inventario de objetos OSM. Cambian las asociaciones y el contexto de relations
porque cambia el tamaño y el número de celdas candidatas.

| Archivo | Función |
|---|---|
| `osm_objects.jsonl` | Inventario normalizado de nodes y ways OSM, con sus tags, procedencia y estado geométrico. Responde a «qué objetos cartográficos existen y cuáles son asociables». |
| `candidate_osm_associations.jsonl` | Relación muchos-a-muchos entre celdas F1 y objetos OSM que las intersectan. Responde a «qué elementos del mapa corresponden a cada candidato». |
| `relation_context.jsonl` | Contexto de las relations OSM padre directas de los nodes y ways asociados. Añade roles y agrupaciones sin construir geometrías de relations. |
| `provenance.json` | Identidad y trazabilidad: inputs, hashes, reglas D049, configuración efectiva, políticas, versiones y conteos del bundle. |
| `sha256.txt` | Hashes SHA-256 de los cuatro archivos canónicos anteriores para detectar corrupción o modificaciones. No incluye su propio hash. |

En conjunto, los archivos se leen así:

```text
osm_objects.jsonl
    qué objetos OSM existen y qué estado geométrico tienen
candidate_osm_associations.jsonl
    qué objetos intersectan cada candidate_id
relation_context.jsonl
    a qué relations padre pertenecen los objetos asociados
provenance.json
    con qué inputs, reglas y software se generó el resultado
sha256.txt
    cómo comprobar la integridad de los cuatro archivos anteriores
```

Estos bundles todavía no contienen imágenes OSM ni embeddings de
CrossText2Loc. Constituyen la base geográfica que conecta las celdas candidatas
de Madrid con los objetos vectoriales de OpenStreetMap.

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
config.policy
config.canonical_sha256
geometry.projected_crs
geometry.transform_version
geometry.transform_source_sha256
geometry.association_predicate
geometry.predicate_direction
geometry.boundary_contact_policy
geometry.relation_policy
geometry.invalid_geometry_policy
geometry.direct_node_policy
software.generator_source_sha256
software.python_version
software.numpy_version
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

## Schemas implementados

F3 utiliza los siguientes schemas versionados:

```text
schemas/f3_osm_object.schema.json
schemas/f3_association.schema.json
schemas/f3_relation_context.schema.json
schemas/f3_provenance.schema.json
```

Los schemas validan filas y provenance; el validador integral comprueba además
unicidad, referencias cruzadas, conteos, orden, hashes e identidad.

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

Estas comprobaciones estructurales se complementan en
`src/tfg_phase0/f3_validation.py` con la validación integral del bundle contra
los inventarios F3.3-F3.5.

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

## Cobertura de tests implementada

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

F3.8 validó conteos, estados D049, asociaciones, contexto de relations,
repetibilidad, cache hit y recursos sobre el snapshot F2 local. Los resultados
y hashes están en [EXPERIMENTS.md](EXPERIMENTS.md#materialización-f3-de-madrid)
y su aceptación final en [PHASE3_CLOSURE.md](PHASE3_CLOSURE.md).

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
