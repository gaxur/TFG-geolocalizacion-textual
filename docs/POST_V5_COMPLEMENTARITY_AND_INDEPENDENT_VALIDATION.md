# Auditoría CT2L–OSM/F3 y validación independiente posterior a v5

## Objetivo y alcance

Esta fase no busca otra mejora numérica sobre H26–H37. Audita qué información
reciben CrossText2Loc, F3 y Qwen3-VL, comprueba si sus diferencias pueden
atribuirse causalmente y prepara un protocolo de transferencia independiente.

Solo se usaron CPU y artefactos locales. No se realizaron renders, embeddings,
inferencias, descargas, consultas externas ni apertura del test sellado.

## Estado verificado

- El Top-100 H26–H37 contiene un candidato a menos de 100 m en 11/12 consultas
  y a menos de 50 m en 10/12.
- El rank medio del candidato más próximo es 50,3.
- Atlas v3 conserva las métricas GeoRecall de CT2L y reduce 0,37 m la media
  Top-1 mediante una sola consulta.
- V4 demuestra señal OSM estructurada, pero introduce degradaciones de hasta
  281,30 m.
- V5 bloquea H31/H32 y elimina degradaciones en desarrollo, pero toda su mejora
  depende de H36 y pierde las ganancias Top-10 de v4.
- H26–H37 ya no es adecuado para otra selección de reglas.

Atlas v3 continúa siendo la política congelada.

## Raster CrossText2Loc

### Fuente y representación

| Propiedad | Valor |
|---|---|
| Fuente | Geofabrik Madrid `madrid-261014.osm.pbf` |
| Timestamp OSM | `2026-10-14T20:21:12Z` |
| SHA-256 | `9ef85f5c...0db8` |
| Estilo | OpenStreetMap Carto v5.9.0, commit `491bd4a...` |
| Renderer | Mapnik 3.1.0, osm2pgsql 1.11.0 |
| Proyección | EPSG:3857, norte arriba |
| Escala | zoom 18 |
| Crop nativo | 256 × 256 px |
| Salida publicada | 512 × 512 px, resize bicúbico |
| Entrada CLIP | 336 × 336 px |
| Anchura proyectada | 152,874 m por lado |
| Estado del perfil | `experimental_unconfirmed` |

Los 512 píxeles no añaden detalle: interpolan el crop nativo antes de reducirlo
a 336. El raster representa calles, edificios, usos, agua, símbolos seleccionados
y nombres que sobreviven a zoom, reglas de estilo y colisiones. No dibuja el
centro ni el borde de la celda candidata.

Los nombres no son exhaustivos. Mapnik puede omitirlos por colisión, espacio,
orden de capas o borde del crop. Iconos y texto pequeños sufren dos remuestreos.
Que un elemento esté en los píxeles no demuestra que CT2L lo utilice.

El perfil local tampoco está confirmado como equivalente al entrenamiento: el
script upstream guarda una imagen distinta del crop que calcula, y el renderer
local usa un parche tipográfico que puede modificar extensión y colisiones.

## Información F3

F3 conserva 29.777 objetos OSM y 23.808 asociaciones para las 253 celdas de
50 m. Proporciona:

- identidad `osm_type/osm_id/osm_ref`;
- todos los tags de nodes y ways;
- nombres, aliases y Wikidata cuando existen;
- rol geométrico `point`, `line` o `area`;
- bbox métrica;
- asociación exacta por `intersects` con la celda;
- `within`, `contains`, `crosses`, `overlaps`, `touches`;
- distancia del centro de celda a la geometría completa en EPSG:25830;
- contexto de relations de un salto con roles de members.

No serializa la geometría completa, no expande relations, no calcula visibilidad,
bearing, FOV ni posición del observador. Un objeto puede asociarse a varias
celdas; en 50 m ocurre con 1.349 objetos.

## Mismatch de snapshots

F3 y F4 no usan los mismos bytes.

| Propiedad | F3 | Raster F4 |
|---|---|---|
| Fuente | Overpass XML | Geofabrik PBF |
| Fecha | 6 de octubre de 2026 | 14 de octubre de 2026 |
| Ámbito | D004 más nodes de cierre | Extracto regional Madrid |
| Relations | padres directos, no expandidos | clausura regional y multipolígonos osm2pgsql |
| Política de área | D049 propia | Lua de OSM Carto/osm2pgsql |

La comparación local encontró diferencias de objetos, versiones, tags,
coordenadas y members. Por tanto, una ventaja F3 actual puede deberse al formato
estructurado, pero también a fecha, proveedor, ámbito o clausura. No es válida
una atribución causal limpia.

## Clasificación A–E

| Clase | Información |
|---|---|
| A. Raster y F3 | Trazado vial, edificios, algunos POI, algunos nombres y distribución aproximada |
| B. F3 explícito, no raster explícito | IDs, tags completos, identidad, predicados, distancia, frecuencia entre celdas y roles de relation |
| C. Raster difícil a escala | Nombres pequeños, iconos densos, pasajes, entradas, labels de borde o suprimidos por colisión |
| D. Visual real no OSM | Material/color de fachada, rótulo físico, perspectiva, oclusión, vehículos, obras y condiciones temporales |
| E. Ausente/no determinable | Atención causal, orientación real, visibilidad sin foto, hechos no mapeados y posición continua |

La clase B es la complementariedad potencial de F3. Para demostrarla hay que
alinear primero la fuente y controlar los píxeles.

## Ablación cartográfica alineada

### Viabilidad

El pipeline puede generar cuatro variantes anidadas:

1. `G`: geometría.
2. `GS`: geometría y símbolos.
3. `GSN`: geometría, símbolos y nombres.
4. `FULL`: estilo completo congelado.

La fuente recomendada es derivar localmente un snapshot canónico con buffer a
partir del PBF F4 ya congelado y usar exactamente esos bytes para un nuevo F3 y
los cuatro rasters. El snapshot F2 actual no cubre todos los footprints F4.

Debe mantenerse idéntico: catálogo, centros, zoom, bbox, orientación, renderer,
fuentes, crop, resize, checkpoint y consultas. Hay que registrar qué labels e
iconos se colocan realmente.

### Interpretación

La ablación permite afirmar que añadir una familia controlada de píxeles cambia
el ranking. No permite afirmar automáticamente que el modelo entendió un icono o
que esa familia fue la causa única: las colisiones producen cambios no locales y
las variantes se alejan de la distribución de entrenamiento.

### Presupuesto 50 m

| Recurso | Estimación |
|---|---:|
| Candidatos | 253 |
| Variantes | 4 |
| PNG | 1.012 |
| PNG aproximados | 209 MB |
| Render | 24 min CPU, usando extrapolación histórica |
| Matrices `(253,768)` | 3,1 MB |
| Embeddings | ~66 s GPU estimados |
| PostgreSQL temporal | hasta 12 GB tmpfs configurados |

Antes de la campaña completa se exige un piloto CPU con candidatos
predeclarados por estrato espacial. El piloto solo valida identidad de capas,
diferencias y manifests; no calcula embeddings.

Esta ablación es el estudio mecanístico secundario. Requiere autorización para
render y GPU y no debe ejecutarse sobre la galería 25 m inicialmente.

## Datos independientes

### Inventario local

Los conjuntos humanos H01–H37 ya participaron en decisiones. El material
Street View no conserva píxeles. Panoramax fue revisado y tiene GT insuficiente.
El benchmark OSM es sintético, comparte fuente con la galería y ya se utilizó.

Existe una caché Mapillary amplia, pero su remanente aparente no constituye un
dataset:

- no tiene descripciones humanas nuevas;
- no tiene GT de observador aprobado;
- contiene agrupación por secuencia;
- no puede demostrarse su exclusión respecto al test sellado sin una frontera de
  confianza que emita un ledger no revelador.

**Observaciones independientes locales confirmadas: 0.**

No puede construirse ahora un conjunto defendible sin adquisición/anotación o
sin un mecanismo seguro de exclusión respecto al material reservado.

## Protocolo independiente propuesto

Se proponen 20 observaciones nuevas `I01–I20`, separadas de los identificadores
H, para una validación one-shot de transferencia, no para tuning.

### Selección

- al menos 10 bloques espaciales, máximo dos observaciones por bloque;
- separación mínima objetivo de 75 m;
- selección metadata-only;
- sin rankings, VLM, fuerza OSM, distancia a candidatos ni éxito esperado;
- ledger ciego que solo devuelva elegible/rechazado, razón no reveladora y hash;
- exclusión por image ID, SHA-256, hash perceptual, secuencia y revisión humana
  de solapamiento.

### Anotación

- descripción española humana basada solo en evidencia visible;
- dos revisores ciegos a rankings y modelos;
- posición de cámara y su incertidumbre documentadas;
- roles referencia/verificación globalmente disjuntos;
- descripción congelada antes de retrieval.

### Freeze

1. Congelar selección y roles.
2. Adquirir solo IDs autorizados.
3. Hash y revisión de solapamiento.
4. Congelar descripciones.
5. Congelar políticas y Top-100.
6. Generar rankings sin referencias.
7. Congelar rankings.
8. Cargar referencias una vez y evaluar.

### Políticas y métricas

Primarias: CT2L y Atlas v3. V4/v5 se informan como diagnósticos congelados, no se
recalibran en I01–I20.

Métricas:

- GeoRecall@1/5/10 a 50 y 100 m;
- sensibilidad a 25/50/75/100 m;
- media y mediana Top-1;
- degradaciones individuales y máxima degradación;
- cobertura Top-100;
- tabla por consulta, sin score compuesto.

Éxito mínimo: la mejora debe repetirse en al menos tres consultas, no depender de
un caso, no perder ninguna métrica GeoRecall primaria y no introducir una
regresión individual material. Si quedan menos de 12 observaciones tras controles,
no se ejecuta una comparación de políticas.

H38–H61 permanece cerrado y no se usa para selección, protocolo o calibración.

## Papel del VLM

Qwen3-VL-8B muestra capacidad claim-level:

- reconoce objetos y atributos urbanos visibles;
- a veces emite OCR plausible;
- detectó parte de las contradicciones humanas en fixtures pequeñas.

No ha demostrado:

- correspondencia imagen-candidato fiable;
- razonamiento egocéntrico controlado;
- posición de cámara;
- mejora GeoRecall.

En H26–H37, aproximadamente dos tercios de tareas son `unverifiable`, el soporte
es compartido y suele proceder de una secuencia. Atlas mejora solo 0,37 m sin
nuevos hits; multivista/OCR reproduce sus métricas. Pairwise tuvo 80,3 % de
salidas inválidas/truncadas.

No está justificada una nueva campaña VLM. Una futura comparación de cuatro
brazos solo sería justa con el nuevo conjunto, presupuestos Top-N iguales,
cobertura visual simétrica y tratamientos congelados. Los artefactos actuales
solo permiten una comparación retrospectiva y confusa.

## Alternativas

| Alternativa | Información nueva | Coste | Riesgo | Decisión |
|---|---|---|---|---|
| A. Ablación alineada | Mecanismo raster/F3 | Medio, render+GPU | Alto si vuelve a usar H26–H37 | Secundaria |
| B. Nuevo conjunto independiente | Generalización y fallos nuevos | Medio, datos+anotación+GPU pequeña | Menor con one-shot | **Prioritaria** |
| C. Mejor asociación imagen-candidato | Visibilidad/FOV | Medio-alto, red+GPU | Medio-alto | Posponer |
| D. Recuperación híbrida | Cobertura de unión | Alto | Muy alto ahora | No implementar |
| E. Nueva evidencia visual | Píxeles/fuente nuevos | Máximo, red+GPU | Alto | No continuar ahora |

La incertidumbre dominante es la validez externa. Por eso B tiene prioridad
sobre A aunque A sea más fácil con infraestructura existente.

## Decisión y autorizaciones

### Propuesta única prioritaria

Construir `I01–I20` y ejecutar una validación one-shot de CT2L y Atlas v3, con
v4/v5 solo diagnósticos congelados. Actualmente está bloqueada porque hay cero
observaciones locales elegibles confirmadas.

### Requiere autorización

1. Adquisición de nuevas referencias o recogida humana equivalente.
2. Generación de un ledger ciego de exclusión por una frontera de confianza.
3. Anotación humana y revisión de solapamiento.
4. Tras congelar el dataset, una ejecución GPU pequeña de CT2L/Atlas.

Separadamente, la ablación cartográfica requeriría:

1. autorización de campaña de render controlado;
2. presupuesto temporal de disco/tmpfs;
3. autorización GPU para 1.012 embeddings;
4. aprobación antes de cualquier réplica 25 m.

No se solicita ni recomienda ahora autorización para nuevas inferencias VLM,
recuperación híbrida o apertura del test final.
