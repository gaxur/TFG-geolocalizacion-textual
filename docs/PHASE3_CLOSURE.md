# Cierre de Fase 3: catálogo geométrico OSM de Madrid

## Declaración de estado

**F3: CERRADA PARA USO INTERNO Y CONTINUIDAD TÉCNICA HACIA F4.**

**Fecha de cierre:** 14 de octubre de 2026.

Este cierre acepta los artefactos geométricos para experimentación interna. No
aprueba todavía la distribución pública autónoma del snapshot F2 ni de los
bundles F3, que requiere una revisión específica del paquete distributivo,
atribución a OpenStreetMap y cumplimiento de ODbL 1.0.

## Objetivo y alcance

F3 vincula de forma reproducible las celdas candidatas F1 con los objetos del
snapshot OSM F2. Comprende contratos, validación de inputs, normalización
geométrica, asociaciones exactas, contexto parcial de relations, serialización,
identidad, publicación robusta y materialización real.

F3 no incluye interpretación lingüística, preselección semántica, ground truth,
imágenes, embeddings, CrossText2Loc, GOTPR, scoring ni ranking Top-K.

## Resumen de etapas

| Etapa | Entregable | Estado |
|---|---|---|
| F3.1 | Schemas y contratos estructurales | PASS |
| F3.2 | Frontera verificada F1/F2/D049 | PASS |
| F3.3 | Geometrías normalizadas en EPSG:25830 | PASS |
| F3.4 | STRtree y asociaciones muchos-a-muchos | PASS |
| F3.5 | Contexto de relations de un salto | PASS |
| F3.6 | Identidad, serialización, validación y publicación D052 | PASS |
| F3.7 | Robustez, concurrencia y recuperación ante fallos | PASS |
| F3.8 | Bundles reales de 50 m y 25 m | PASS |
| F3.9 | Revisión científica, licencias y cierre | PASS |

## Matriz de aceptación

| Criterio | Evidencia | Estado | Acción posterior |
|---|---|---|---|
| Inputs F1/F2 explícitos, locales e inmutables | Manifests F1 v2 y snapshot F2 `f2152555...` | PASS | Ninguna |
| Validación de schemas, hashes, región, bbox, CRS y conteos | F3.1-F3.2 | PASS | Ninguna |
| D049 aplicada sin reparación ni inferencia silenciosa | F3.3 y reglas v0.9.2 fijadas | PASS | Mantener sus limitaciones |
| Geometrías y distancias en EPSG:25830 | F3.3-F3.4 | PASS | Ninguna |
| Intersección exacta muchos-a-muchos, sin scoring ni ground truth | D022, D050 y F3.4 | PASS | Ninguna |
| Contexto de relations de un salto | F3.5 | PASS | No interpretarlo como geometría completa |
| Cinco archivos canónicos, identidad y checksums D052 | F3.6 y bundles reales | PASS | Ninguna |
| Publicación robusta, no-replace y cache hit | F3.7-F3.8 | PASS | Revalidar si cambia el filesystem |
| Materialización de 50 m y 25 m | F3.8 | PASS | Ninguna |
| Elección definitiva 25 m/50 m | D003 | NOT APPLICABLE | Experimento posterior |
| Parámetros de preselección | D021 | NOT APPLICABLE | Fases posteriores |
| Imágenes, embeddings y retrieval | Frontera F3/F4 | NOT APPLICABLE | F4 |
| Uso interno con procedencia y atribución | Provenance F2 y documentación ODbL | PASS | Ninguna |
| Distribución pública de F2/F3 | Paquete distributivo no definido | PENDING | Revisión ODbL específica |

## Inputs congelados

| Input | Identidad | Conteo o tamaño | SHA-256 |
|---|---|---:|---|
| Manifest F1 50 m | `madrid-pilot-grid-v1-s50-l50` | 253 candidatos | `ad35d5cb3b602a9ce313e06e10f913f169430d62a948c0f5e77b396bc810f2aa` |
| Manifest F1 25 m | `madrid-pilot-grid-v1-s25-l25` | 1.115 candidatos | `a23d3f3b54958661db76914dff9ff40a3f01a133ee86499fb9e4ddf706a49f11` |
| Snapshot F2 | `osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141` | 8.420.815 bytes | `f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141` |

F2 contiene 25.537 nodes, 4.240 ways y 498 relations contextuales. Los ways
están completos respecto a sus `nd ref`; las relations no están expandidas.

## Bundles aceptados

### 50 m

- `f3_dataset_id`: `f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453`.
- Objetos serializados: 29.777.
- Objetos asociables: 26.546.
- Asociaciones: 23.808.
- Relations emitidas: 196.
- Members asociados: 945.
- Tamaño total: 18.744.138 bytes.

| Archivo | SHA-256 |
|---|---|
| `osm_objects.jsonl` | `c928a1b9a1b43d89d3376395043aca6fe37803f17941823af966ac0049a3e94f` |
| `candidate_osm_associations.jsonl` | `6a43797300c40628c55c64e0fd72bde6a86ccebc6614a7883dfcfea637144b20` |
| `relation_context.jsonl` | `2e91a080b6da1be95913ad1a630bf14be7194d10fb4225ea348c0ecbb5618897` |
| `provenance.json` | `d637f6ef3f2168f7cdcf52412cd04c94bd0adb199e584f65b34841a4e9fbc7ea` |
| `sha256.txt` | `99982cd5d0357f83ad6c02cec24745fd69e8b93e01eefe1215b53c8e94029f0f` |

### 25 m

- `f3_dataset_id`: `f3-madrid-pilot-associations-sha256-902e8edcd7892c4b9f6a686a6573fb5c15bf19858ecf2ce14d09fb687e9e0ffa`.
- Objetos serializados: 29.777.
- Objetos asociables: 26.546.
- Asociaciones: 30.118.
- Relations emitidas: 210.
- Members asociados: 1.058.
- Tamaño total: 20.917.604 bytes.

| Archivo | SHA-256 |
|---|---|
| `osm_objects.jsonl` | `c928a1b9a1b43d89d3376395043aca6fe37803f17941823af966ac0049a3e94f` |
| `candidate_osm_associations.jsonl` | `e6073f04ec36e565b972c1bb687273547c855b08c3a26c135f1dcbe2068ae4d3` |
| `relation_context.jsonl` | `463061b5273632354a846c0ff053fe940c00a5c67a3be6db9298254dc120fee2` |
| `provenance.json` | `528e2cee3388e6e1f889dd2ab19387ffe5b1e6c5a3e4f4ebc4f3d5c31d5a2da8` |
| `sha256.txt` | `0a898420116658d9983222ac94f823db2a688487e859c1fbd49299f5f51d6ba9` |

## Resultados geométricos aceptados

El inventario común contiene 26.546 objetos válidos y asociables, 3.231 no
asociables y ninguna geometría inválida.

| Razón de no asociación | Conteo |
|---|---:|
| `added_way_node_direct_association_forbidden` | 2.518 |
| `unknown_closed_way_no_votes` | 710 |
| `unknown_closed_way_conflict` | 3 |

Los nodes exteriores completan geometrías de ways, pero D050 prohíbe usarlos
como evidencia puntual local. Los 713 closed ways ambiguos se excluyen conforme
a D049. No se repararon geometrías ni se heredó semántica de relations.

En 50 m, 1.349 objetos intersectan varias celdas; en 25 m son 2.235. Todos los
candidatos de 50 m tienen asociaciones. Dos candidatos de 25 m carecen de
asociaciones directas y se conservan porque F3 no filtra ni modifica F1.

Las 498 relations de entrada se contabilizan. Solo se emiten las respaldadas por
members node/way presentes y asociados. El contexto es parcial, de un salto y
no transitivo.

## Reproducibilidad y limitaciones

Los bundles reconstruyen su identidad desde `provenance.json`, validan schemas,
referencias cruzadas y conteos, y conservaron bytes, tamaños y mtimes durante
cache hit. El hash efectivo del generador es
`ac6333c7e277a381f37e2cc5416b93083495cdfa15dc2280be957bceae90dc38`.

La primera ejecución F3.8 utilizó un entrypoint todavía no versionado y sus
informes iniciales fueron sobrescritos por informes de cache hit. Esta limitación
afecta a la trazabilidad operativa histórica, no a los bytes canónicos ni a la
identidad D052, comprobados de forma independiente.

## OSM/ODbL y atribución

Los datos OpenStreetMap se usan bajo ODbL 1.0. La atribución conservada es:

> © OpenStreetMap contributors. Datos disponibles bajo la Open Database License
> (ODbL). https://www.openstreetmap.org/copyright

El uso interno académico de snapshot y bundles queda aceptado con su provenance.
La distribución pública autónoma no queda aprobada. Requerirá un paquete que
incluya atribución, referencia a ODbL, snapshot de origen, transformaciones y el
mecanismo de acceso a la base derivada o a sus alteraciones, tras revisar el
artefacto concreto.

La ODbL de los datos no se aplica automáticamente al código propio. Las imágenes
cartográficas de F4 deberán revisar por separado los datos, el estilo y las
condiciones del proveedor o renderizador. El servidor estándar de tiles de OSM
no debe emplearse para descarga masiva u offline.

Fuentes oficiales:

- [Copyright de OpenStreetMap](https://www.openstreetmap.org/copyright).
- [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- [Directrices de atribución OSMF](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines).
- [Política del servidor estándar de tiles](https://operations.osmfoundation.org/policies/tiles/).

## Riesgos aceptados

- D049 usa una heurística histórica e incompleta.
- Las relations son parciales y de un salto.
- Algunos objetos extensos intersectan numerosas celdas.
- Dos celdas de 25 m no tienen asociación directa.
- La transformación propia no promete identidad universal con PROJ.
- La igualdad byte a byte se circunscribe al entorno algorítmico identificado.
- Los locks abandonados requieren revisión manual.
- D003 y D021 siguen pendientes de experimento.
- Los bundles F3 no son paquetes públicos autónomos aprobados.

## Handoff a F4

F3 entrega candidatos estables, objetos OSM normalizados, asociaciones,
contexto de relations, provenance e integridad. F4 deberá generar sus propios
artefactos de imágenes y embeddings sin modificar F1 ni F3.

F4 debe fijar el perfil de imagen OSM, una fuente o renderizador permitido, el
checkpoint, el preprocesamiento, los embeddings y el ranking Top-K. D007, D013 y
D016 continúan pendientes de F4. La generación masiva no debe usar el servidor
estándar `tile.openstreetmap.org` como fuente offline; se requiere un proveedor
compatible o renderizado propio.

## Declaración formal

**F3: CERRADA PARA USO INTERNO Y CONTINUIDAD TÉCNICA HACIA F4.**

Reservas:

- D003 y D021 siguen pendientes de experimento.
- La distribución pública de snapshot F2 y bundles F3 requiere revisión ODbL
  específica y un paquete de atribución/licencia.
- F4 todavía debe generar imágenes, embeddings y recuperación Top-K.
