# Exploratory-v5: reranking fiable con evidencia OSM/F3 y visual

## Alcance

Exploratory-v5 investiga por qué el ranking OSM estructurado v4 mejoró unas
consultas y degradó otras. Reutiliza únicamente artefactos locales H26–H37. No
ejecuta GPU, red, descargas, adquisición de imágenes ni inferencia VLM nueva.

Los rankings se congelaron sin referencias geográficas. El GT se cargó después
en un proceso separado para evaluación y diagnóstico post-hoc. H26–H37 continúa
siendo desarrollo reutilizado; la confianza descrita aquí es heurística, no una
probabilidad calibrada.

## Mecanismos de v4

### H28

La promoción v4 combinó una farmacia y dos pasos de peatones: tres objetos OSM
distintos y dos familias semánticas. El candidato pasó de rank CT2L 13 a Top-1 y
redujo el error en 333,84 m, aunque quedó a 182,52 m. El candidato realmente
cercano pasó de rank 30 a 3. La evidencia visual existente confirma el paso, no
la farmacia; la conjunción completa no está corroborada.

### H30

Ocho nodos de bolardo forman una hilera físicamente correlacionada. V4 conservó
solo el máximo por categoría para el score, pero la explicación aparentaba más
evidencia de la realmente independiente. Varias vistas existentes confirman
bolardos, aunque siguen siendo una sola familia. El Top-1 mejoró solo 31,72 m y
el candidato cercano pasó de rank 69 a 8.

### H36

`El Escarpín` es un nombre exacto asociado a una sola celda del catálogo y el
candidato ya estaba en rank CT2L 10. Al promoverlo a Top-1 pasó de 62,17 a
32,79 m y creó un acierto a 50 m. Existe OCR histórico con ese texto, pero la
vista comparte secuencia con la referencia y el contrato la dejó
`unverifiable`; no se trata como corroboración independiente.

### H31

V4 sumó nombre y categoría del mismo `node/3644961945`: `Starbucks Coffee` y
`amenity=cafe` no son dos evidencias independientes. La rareza se calculó dentro
del Top-100, donde aparecía en tres celdas, pero en el catálogo completo hay
cinco objetos normalizados como Starbucks Coffee asociados a cuatro celdas.
El candidato procedía del rank 53 y no tenía soporte visual específico del
rótulo o de la cafetería. La promoción degradó Top-1 en 281,30 m.

### H32

La descripción dice `Alonzo`, pero F3 no contiene esa identidad. V4 promocionó
una peluquería llamada `Luis` junto con un bolardo y dos ways peatonales. La
ausencia nominal era neutral y la conjunción sustituyó silenciosamente el
atributo más distintivo. La evidencia visual existente solo soporta edificios y
comercio genérico. El ranking estructurado degradó Top-1 en 233,30 m y RRF en
524,12 m.

## Complementariedad con CrossText2Loc

Las imágenes CT2L son mapas OSM Carto norte-arriba a zoom 18. El recorte nativo
es 256 px, se publica a 512 px y CLIP recibe 336 px. Cubre aproximadamente
152,87 m proyectados por lado. Puede representar geometría de calles y edificios,
colores de usos, iconos seleccionados y nombres sujetos a reglas de estilo y
colisiones. No recibe tags, IDs OSM, borde de la celda, predicados F3 ni
distancias métricas explícitas.

| Clase | Evidencia |
|---|---|
| A. Cartografía visible para CT2L | Geometría urbana, símbolos, usos y nombres que sobreviven al render y preprocesamiento |
| B. F3 estructurado adicional | Tags completos, identidad de objeto, intersección celda-objeto, predicados, distancia y contexto parcial de relations |
| C. Fotografía de calle | Apariencia, materiales, fachada, rótulos reales, perspectiva, oclusión y condiciones temporales |
| D. No disponible | Atención causal del modelo, visibilidad exacta, hechos ausentes y geometría relation completa F3 |

F3 y el raster CT2L no proceden exactamente de los mismos bytes: F3 usa el
snapshot XML F2 y F4 renderiza un PBF Geofabrik mediante osm2pgsql/OSM Carto.
Por tanto, una diferencia entre ambos no demuestra por sí sola que F3 aporte
información nueva al modelo. Tampoco se afirma que CT2L interprete una etiqueta
solo porque aparezca en píxeles.

## Confianza v5

La confianza usa únicamente señales disponibles durante inferencia:

- unicidad de nombres en las 253 celdas, no solo en el Top-100;
- agrupación por identidad OSM y familia semántica;
- coincidencia o ausencia de nombres distintivos;
- dos familias específicas realmente distintas;
- rank CT2L como señal de acuerdo;
- soporte visual específico ya congelado;
- fallback Atlas v3.

Alta confianza exige nombre exacto globalmente único y candidato CT2L Top-10.
Confianza media exige candidato Top-20 y dos familias específicas distintas, o
soporte visual específico de una familia. Un nombre distintivo de la consulta no
coincidente bloquea la confianza. Las etiquetas del mismo objeto y los objetos
repetidos de una categoría no cuentan como familias independientes.

La política actúa en tres consultas:

- H28: confianza media, farmacia+paso y soporte visual del paso, rank 11 según
  el baseline empleado por v5;
- H29: confianza media, pero ya estaba por encima del destino y no produce cambio;
- H36: confianza alta, nombre globalmente único y rank 10.

Se abstiene en 9/12, incluidos H30, H31 y H32.

## Políticas

| Política | Regla |
|---|---|
| Top-1 protegido | Promoción media/alta como máximo a rank 5; conserva Top-1 Atlas |
| Top-1 condicionado | Solo confianza alta puede ascender a rank 1 |
| Promoción con abstención | Alta a rank 1, media a rank 5, resto fallback Atlas |

Las ablaciones retiran una condición por vez: nombres, categorías, ambigüedad
global, coherencia nominal, agrupación de objetos o soporte visual. No se realizó
una búsqueda combinatoria ni selección de umbrales por GT.

## Resultados

| Variante | 50 m @1/@5/@10 | 100 m @1/@5/@10 | Top-1 media | Degradaciones vs Atlas | Abstenciones |
|---|---:|---:|---:|---:|---:|
| CT2L | 0/0/3 | 1/4/5 | 382,76 m | 1 | — |
| Atlas v3 | 0/0/3 | 1/4/5 | 382,39 m | 0 | — |
| OSM estructurado v4 | 1/2/6 | 1/4/7 | 355,34 m | 3 | — |
| Top-1 protegido | 0/1/3 | 1/4/5 | 382,39 m | 0 | 9/12 |
| Top-1 condicionado | 1/1/3 | 1/4/5 | 379,94 m | 0 | 9/12 |
| Confianza+abstención | 1/1/3 | 1/4/5 | 379,94 m | 0 | 9/12 |

Top-1 protegido aplica dos operaciones, una desde ranks 11–100, pero solo H36
crea un nuevo acierto @5 a 50 m. Top-1 condicionado cambia exclusivamente H36 y
crea el nuevo acierto @1 a 50 m. H28 no crea ningún hit nuevo y H29 no cambia el
orden efectivo. Ninguna política v5 conserva las ganancias @10 de v4.

Las ablaciones no aportan evidencia robusta adicional. Nombres solos reproducen
la mejora de H36; categorías solas no mejoran GeoRecall. Retirar restricciones
puede aumentar operaciones, pero no produce nuevos aciertos agregados en esta
muestra. Esto no valida causalmente cada restricción: doce consultas reutilizadas
son insuficientes para calibrarlas.

## Sensibilidad

Toda mejora de GeoRecall v5 depende de H36. Al omitir H36, desaparecen el nuevo
hit @1 y @5 a 50 m y la reducción media Top-1. El leave-one-out se usa únicamente
como diagnóstico de sensibilidad; no crea un test independiente ni se utilizó
para seleccionar reglas.

## Decisión

V5 supera a v4 en seguridad, no en cobertura. Bloquea sin GT las degradaciones
conocidas de H31 y H32 y no introduce degradaciones Top-1 en H26–H37. Sin embargo,
el beneficio procede de una sola consulta ya observada en varias iteraciones.

No existe una política suficientemente robusta para justificar abrir una
evaluación independiente. Atlas v3 se conserva. Se recomienda detener nuevas
iteraciones de reglas sobre H26–H37: continuar ajustando confianza sobre estas
doce consultas aumentaría el riesgo de sobreajuste.

Tampoco se justifica implementar todavía un recuperador OSM independiente. H33
sigue siendo un fallo de recuperación Top-100, pero un único caso no determina
la arquitectura completa.

El siguiente paso mínimo requiere información nueva, no otra regla sobre los
mismos resultados: un pequeño conjunto de desarrollo independiente, o una
ablación cartográfica alineada por fuente que compare nombres, iconos y geometría
en los mismos rasters. Cualquier implementación extensa o apertura de test
requiere autorización separada.

## Reproducibilidad

El lineage está en
`results/generated/mapillary/h26-h37-exploratory-v5/`:

- `mechanism-diagnostic.json`;
- `promotion-confidence.json`;
- `reliable-rankings.frozen.json`;
- `evaluation.json`;
- `analysis.json`;
- `manifest.json`.

Atlas v3 y exploratory-v2/v3/v4 permanecen intactos.
