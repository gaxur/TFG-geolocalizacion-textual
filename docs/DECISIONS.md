# Decisiones del proyecto

Este documento es el registro permanente de decisiones técnicas y metodológicas
del TFG. No sustituye a la descripción del proyecto ni a la documentación de los
modelos. Conserva el estado y la trazabilidad de cada decisión, incluidas las
alternativas descartadas o sustituidas.

Los estados permitidos son: `ACEPTADA`, `PROPUESTA`,
`PENDIENTE DE VALIDACIÓN`, `PENDIENTE DE AUTORES`,
`PENDIENTE DE PROVEEDOR`, `PENDIENTE DE LICENCIA`,
`PENDIENTE DE EXPERIMENTO`, `BLOQUEADA`, `DESCARTADA` y `SUSTITUIDA`.
Una recomendación no pasa a `ACEPTADA` hasta que el responsable del TFG la
apruebe expresamente o sea consecuencia inequívoca de una decisión ya aceptada.

## Resumen

| ID | Decisión | Estado | Componente |
|---|---|---|---|
| D001 | Identificar cada candidato como una celda y usar su centro como posición | ACEPTADA | Catálogo |
| D002 | Construir una cuadrícula métrica en EPSG:25830 y publicar coordenadas WGS84 | ACEPTADA | Catálogo |
| D003 | Utilizar inicialmente celdas y separación de 25 m | PENDIENTE DE EXPERIMENTO | Catálogo |
| D004 | Usar la bbox acordada de aproximadamente 0,75 km² exclusivamente para el piloto | ACEPTADA | Catálogo piloto |
| D005 | Permitir el solapamiento visual entre candidatos sin deduplicarlos por similitud | ACEPTADA | Catálogo |
| D006 | Precalcular offline las imágenes y embeddings de CrossText2Loc por candidato | ACEPTADA | CrossText2Loc |
| D007 | Fijar el perfil exacto de imagen OSM de CrossText2Loc | PENDIENTE DE AUTORES | CrossText2Loc |
| D008 | Mantener OSM y satélite como modalidades independientes inicialmente | ACEPTADA | Satélite |
| D009 | Determinar experimentalmente una posible fusión de OSM y satélite | PENDIENTE DE EXPERIMENTO | Satélite |
| D010 | Mantener separados `candidate_id` y `scene_id` | ACEPTADA | GOTPR |
| D011 | Definir la relación espacial entre candidatos y scenes de GOTPR | PENDIENTE DE AUTORES | GOTPR |
| D012 | Usar un manifest versionado como relación canónica entre candidatos y artefactos | ACEPTADA | Dataset |
| D013 | Probar el checkpoint OSM de Nueva York como opción del MVP | PENDIENTE DE AUTORES | CrossText2Loc |
| D014 | Posponer satélite y excluirlo del MVP inicial | ACEPTADA | Satélite |
| D015 | Elegir un proveedor y una licencia satelital compatibles | PENDIENTE DE VALIDACIÓN | Satélite |
| D016 | Confirmar la licencia de los pesos y datos publicados por CVG-Text | PENDIENTE DE AUTORES | Licencias |
| D017 | Limitar el LLM a producir una intención geográfica estructurada | ACEPTADA | LLM / preselección |
| D018 | Compilar conceptos a OSM mediante reglas y vocabularios versionados | ACEPTADA | LLM / preselección |
| D019 | Preseleccionar contra el snapshot OSM local del catálogo | ACEPTADA | LLM / preselección |
| D020 | Aplicar filtrado progresivo con fallback dentro de la zona declarada | ACEPTADA | LLM / preselección |
| D021 | Fijar tamaños, radios, umbrales y pesos de preselección | PENDIENTE DE EXPERIMENTO | LLM / preselección |
| D022 | Asociar evidencias OSM y candidatos mediante geometría métrica | ACEPTADA | LLM / preselección |
| D023 | Versionar y registrar toda ejecución de preselección | ACEPTADA | LLM / preselección |
| D024 | Fijar la estrategia multilingüe y de traducción | PENDIENTE DE EXPERIMENTO | LLM / preselección |
| D025 | Evaluar la preselección por retención, reducción, fallback y latencia | ACEPTADA | Evaluación |
| D026 | Mantener el contrato del LLM independiente del proveedor y modelo | ACEPTADA | LLM |
| D027 | Separar catálogo de referencia y dataset de evaluación | ACEPTADA | Dataset / evaluación |
| D028 | Usar descripciones humanas para el test y datos controlados para desarrollo | ACEPTADA | Dataset de evaluación |
| D029 | Fijar tamaño y partición por localizaciones del conjunto de evaluación | PENDIENTE DE EXPERIMENTO | Dataset de evaluación |
| D030 | Conservar la coordenada observada y derivar de ella el candidato correcto | ACEPTADA | Ground truth |
| D031 | Evaluar tanto recuperación exacta como error geográfico | ACEPTADA | Evaluación |
| D032 | Comparar catálogo completo frente a preselección bajo condiciones pareadas | ACEPTADA | Evaluación |
| D033 | Congelar el test y prevenir leakage durante recogida y ajuste | ACEPTADA | Dataset de evaluación |
| D034 | Usar un schema de evaluación versionado y trazable | ACEPTADA | Dataset de evaluación |
| D035 | Evaluar las extensiones mediante ablaciones separadas | ACEPTADA | Evaluación |
| D036 | Mantener GeoBridge exclusivamente como extensión opcional posterior al MVP | ACEPTADA | Alcance / GeoBridge |
| D037 | Estudiar GeoBridge primero como retriever alternativo o reranker tras la preselección | PROPUESTA | GeoBridge |
| D038 | Aclarar las licencias del código, checkpoint y release de GeoLoc | PENDIENTE DE LICENCIA | GeoBridge / licencias |
| D039 | Validar la transferencia zero-shot y el perfil de galería de Madrid | PENDIENTE DE EXPERIMENTO | GeoBridge |
| D040 | Conservar un único monorepo del TFG sin reorganizar material existente | ACEPTADA | Repositorio |
| D041 | Obtener CVG-Text por script en revisión fija y excluir los clones externos de Git | ACEPTADA | Dependencias externas |
| D042 | Preparar la reproducción NewYork-mixed OSM solo para inferencia, con pesos congelados | ACEPTADA | CrossText2Loc |
| D043 | Usar Overpass como fuente primaria controlada del snapshot OSM piloto | ACEPTADA | OSM / adquisición |
| D044 | Conservar cada snapshot como OSM XML raw, inmutable y no sobrescribible | ACEPTADA | OSM / datos raw |
| D045 | Registrar integridad y provenance reproducible de cada snapshot OSM | ACEPTADA | OSM / provenance |
| D046 | Separar raw, derivados, imágenes, embeddings e índices; excluir raw voluminoso de Git | ACEPTADA | OSM / almacenamiento |
| D047 | Vincular catálogo y preselección al snapshot; excluir GT, imágenes e índices de Fase 2 | ACEPTADA | OSM / alcance Fase 2 |
| D048 | Fijar endpoint, consulta, bordes, identidad, reintentos y validación del snapshot | ACEPTADA | OSM / operación |
| D049 | Aplicar una política versionada para interpretar la geometría de OSM ways | ACEPTADA | OSM / catálogo geométrico F3 |
| D050 | Fijar el contrato del dataset de asociaciones geométricas F3 | ACEPTADA | OSM / catálogo geométrico F3 |
| D051 | Limitar la provenance de cada artefacto a sus inputs efectivos | ACEPTADA | Provenance / catálogo F1 |
| D052 | Fijar la serialización, identidad y publicación canónica de F3 | ACEPTADA | OSM / publicación F3 |
| D053 | Usar FastAPI como capa HTTP fina con un único worker y runtime F4.6 residente | ACEPTADA | MVP / backend |
| D054 | Integrar el frontend real con contratos F4.6 y Leaflet, conservando demo explícita | SUSTITUIDA | MVP / frontend |
| D055 | Retirar definitivamente la interfaz sintética del frontend | ACEPTADA | MVP / frontend |
| D056 | Desplegar el MVP integrado con Nginx, proxy interno y una única API GPU | ACEPTADA | MVP / despliegue |
| D057 | Publicar por defecto el frontend MVP en la LAN de confianza | ACEPTADA | MVP / despliegue |
| D058 | Extender F4.3 mediante un sidecar F5.1 para variantes textuales | ACEPTADA | F5 / dataset textual |
| D059 | Mantener la preselección y el reranking OSM en stand-by | ACEPTADA | F5 / alcance |
| D060 | Implementar F5.2 mediante un adaptador textual local-only y desacoplado | ACEPTADA | F5 / transformación textual |
| D061 | Exigir revisión humana antes de comparar variantes generadas por modelo real | ACEPTADA | F5 / validación |
| D062 | Validar Qwen3-8B local exacto antes de rankings F5.2 | ACEPTADA | F5 / ejecución local |
| D063 | Exigir evidencia textual exacta en extracciones F5.3 | ACEPTADA | F5 / extracción estructurada |
| D064 | No integrar F5.3 mientras su calidad contractual sea insuficiente | ACEPTADA | F5 / alcance |
| D065 | Mantener bloqueada la integración automática tras comparar estrategias F5.3b | ACEPTADA | F5 / generación estructurada |
| D066 | Versionar el contrato textual para añadir `en_cartographic` sin reinterpretar v1 | ACEPTADA | F5 / variantes textuales |

## D053 — API HTTP interna del MVP

**Estado:** ACEPTADA
**Componente:** MVP / backend
**Fecha:** 2026-10-16
**Origen:** Implementación solicitada expresamente para MVP.1.

### Decisión

FastAPI actúa únicamente como transporte HTTP sobre `CrossText2LocRetriever`.
El servicio se ejecuta con un solo worker Uvicorn, carga una instancia del modelo
durante lifespan y falla al arrancar si los recursos obligatorios no son válidos.

### Contexto

F4.6 ya proporciona un runtime residente y validado, pero no existe transporte
HTTP ni conexión con el frontend. Ejecutar el runner JSONL como subproceso por
petición recargaría recursos y duplicaría responsabilidades.

### Justificación

FastAPI permite exponer los contratos F4.6 sin modificar el núcleo científico.
Un solo worker evita duplicar el modelo GPU; el fallo rápido de startup permite
que un supervisor reinicie recursos inválidos, y `RUNTIME_BUSY` acota la carga
sin introducir una cola externa.

### Alternativas consideradas

- Flask: viable, pero FastAPI aporta validación y OpenAPI con menos adaptación.
- Subproceso JSONL por petición: descartado porque perdería residencia.
- Varios workers, Redis o Celery: descartados para este MVP por duplicación de
  GPU y complejidad innecesaria.

### Consecuencias

No se duplican tokenización, ranking ni coordenadas. La inferencia síncrona se
ejecuta en un thread y se limita a una petición activa; no se incorporan colas
externas, base de datos, HTTP público ni funcionalidades F5.

### Evidencia

- `backend/atlas_api/`
- `scripts/run_mvp1_api.sh`
- `tests/test_api_mvp1.py`
- `docs/MVP.md`

### Dependencias

F4.6 y sus contratos request/response.

### Pendiente

MVP.2 conectará el frontend; MVP.3 definirá el despliegue conjunto. No se aprueba
exposición pública en Internet mediante esta decisión.

## D054 — Integración web real del MVP

**Estado:** SUSTITUIDA por D055
**Componente:** MVP / frontend
**Fecha:** 2026-10-16
**Origen:** Implementación solicitada expresamente para MVP.2.

### Decisión

El frontend existente conserva JavaScript/Vite y adopta la API MVP.1 como modo
predeterminado. Leaflet representa coordenadas WGS84; la simulación queda
aislada en `?mode=demo` y nunca actúa como fallback de errores.

### Justificación

Evita una migración de framework y reutiliza el diseño responsive existente,
manteniendo separados resultados contractuales y escenarios ficticios.

### Alternativas consideradas

- Migración a React/Vue: descartada por no aportar valor al incremento.
- Mantener el SVG como mapa real: descartado porque no es una proyección
  geográfica.
- Mezclar demo y resultados reales: descartado por riesgo metodológico.

### Dependencias

MVP.1 y contratos F4.6.

### Pendiente

MVP.3 validará despliegue conjunto y navegador en un entorno con Chromium. La
fuente de teselas definitiva y sus condiciones siguen siendo configurables.

## D055 — Frontend exclusivamente conectado al recuperador real

**Estado:** ACEPTADA
**Componente:** MVP / frontend
**Fecha:** 2026-10-16
**Origen:** Petición expresa del responsable del TFG.

### Decisión

Se retira definitivamente del frontend la interfaz sintética, incluidos su
parámetro de activación, fixtures, comparación, diálogo, exportación y tests
específicos. La aplicación presenta únicamente respuestas contractuales de la
API MVP.1. D055 sustituye la parte de D054 que conservaba una interfaz sintética.

### Justificación

Una única experiencia evita confundir escenarios ilustrativos con inferencias
reales y reduce código y navegación que ya no forman parte del MVP operativo.

### Consecuencias

Los fallos del backend se muestran como errores y nunca generan candidatos
alternativos. Los parámetros antiguos de URL no modifican el comportamiento.
Las futuras funciones se incorporarán únicamente cuando exista su integración
real y sus resultados estén correctamente identificados.

## D056 — Despliegue integrado local del MVP

**Estado:** ACEPTADA
**Componente:** MVP / despliegue
**Fecha:** 2026-10-19
**Origen:** Implementación solicitada expresamente para MVP.3.

### Decisión

El despliegue final del MVP utiliza Docker Compose con dos servicios operativos:
Nginx sirve el frontend estático y actúa como proxy del mismo origen, mientras
FastAPI permanece sin puerto publicado y ejecuta un único worker con una sola
instancia residente de CrossText2Loc. El acceso host queda limitado por defecto
a `127.0.0.1:8080`.

Chromium se ejecuta en un contenedor ARM64 aislado detrás de un perfil de prueba;
no se instala en el sistema operativo de la PGX. Checkpoint, CLIP, galerías y
embeddings se montan en solo lectura y no se regeneran durante el arranque.

### Justificación

Esta composición mantiene un único origen HTTP, evita CORS abierto, no expone la
API ni los artefactos y reutiliza la imagen GPU ya validada por MVP.1. Dos
servicios y una red Compose son suficientes; no se incorporan colas, bases de
datos ni orquestadores adicionales.

### Consecuencias

El stack es reproducible en la PGX y dispone de healthchecks, smoke HTTP y prueba
visual real. Continúa siendo un servicio local experimental sin autenticación,
TLS, rate limiting ni endurecimiento para Internet. El cierre técnico no implica
validación de precisión geográfica en Madrid.

## D057 — Acceso LAN predeterminado al frontend

**Estado:** ACEPTADA
**Componente:** MVP / despliegue
**Fecha:** 2026-10-19
**Origen:** Petición expresa para acceder desde un dispositivo móvil.

### Decisión

`compose.mvp.yaml` y `scripts/run_mvp3_stack.sh` publican Nginx en `0.0.0.0:8080`
por defecto. FastAPI sigue sin publicar ningún puerto y solo es accesible por el
proxy `/api` dentro de Compose. `MVP_BIND_HOST=127.0.0.1` permite recuperar el
modo exclusivo de la PGX.

### Consecuencias

Los dispositivos de la misma LAN pueden abrir `http://IP_LOCAL:8080/`. El
operador debe usar una red de confianza y revisar firewall y aislamiento de
clientes. No se habilitan reglas de firewall, TLS ni exposición a Internet.
D057 sustituye únicamente el binding predeterminado de D056; conserva el resto
de su arquitectura y restricciones.

## D058 — Sidecar F5.1 compatible con F4.3

**Estado:** ACEPTADA
**Componente:** F5 / dataset textual
**Fecha:** 2026-10-19
**Origen:** Alcance F5.1 solicitado expresamente por el responsable del TFG.

### Decisión

Topónimos, orientación y variantes textuales se almacenan en un artefacto
content-addressed `f5-textual-variant-dataset-v1` que referencia un dataset F4.3
por `dataset_id`, SHA-256 y `query_id`. F4.3 conserva en exclusiva descripción
original, procedencia, partición y ground truth.

Cada observación F5.1 declara cuatro slots: `es_original`, `es_cartographic`,
`en_conventional` y `en_toponym_preserved`. Los derivados pueden permanecer
pendientes y no se tratan como observaciones independientes.

### Justificación

`f4-query-dataset-v1` tiene campos cerrados e identidad content-addressed.
Añadirle campos rompería los artefactos F4.3 existentes. El sidecar permite
validación cruzada y evolución versionada sin duplicar la infraestructura de
evaluación ni el ground truth.

### Consecuencias

Todas las variantes heredan ubicación, grupo y partición. La orientación es
opcional y solo puede convertirse a cardinal cuando se registra explícitamente.
F5.1 valida y resume completitud, pero no genera textos ni ejecuta inferencia.

## D059 — Preselección OSM en stand-by

**Estado:** ACEPTADA
**Componente:** F5 / alcance
**Fecha:** 2026-10-19
**Origen:** Decisión expresa del responsable pendiente de conversación con el tutor.

### Decisión

F5.1 no implementa filtros, reducción de galerías, etiquetas OSM para priorizar,
reranking, combinación de scores, fusión de coordenadas ni selección automática
entre 25 m y 50 m. El ranking exhaustivo CrossText2Loc permanece intacto.

### Consecuencias

El contrato fija `osm_preselection_status: standby_pending_tutor_decision` y
`fusion_enabled: false`. F3 podrá servir en el futuro para análisis alrededor de
candidatos únicamente tras una nueva decisión metodológica.

## D060 — Adaptador textual local-only desacoplado

**Estado:** ACEPTADA
**Componente:** F5 / transformación textual
**Fecha:** 2026-10-19
**Origen:** Alcance F5.2 solicitado expresamente por el responsable del TFG.

### Decisión

F5.2 utiliza la interfaz `TextTransformer` independiente del modelo concreto.
El adaptador inicial para `Qwen/Qwen3-8B` exige un snapshot local, revisión
explícita, `local_files_only=True`, modo no-thinking y generación sin muestreo.
No se publica un servidor LLM ni se modifica el backend del MVP.

El LLM y CrossText2Loc se ejecutan en procesos separados para no mezclar
dependencias ni cargar ambos modelos de forma permanente en la GPU. Un
`FakeTransformer` determinista queda limitado a tests y smoke técnico.

### Consecuencias

La infraestructura puede cambiar de traductor sin alterar F5.1. La ausencia del
snapshot exacto Qwen3-8B bloquea la validación real, pero no justifica descargar
pesos ni sustituirlos por otro modelo local sin decisión expresa.

## D061 — Revisión humana obligatoria de variantes automáticas

**Estado:** ACEPTADA
**Componente:** F5 / validación
**Fecha:** 2026-10-19
**Origen:** Requisitos de validación semántica F5.2.

### Decisión

Las heurísticas automáticas detectan errores estructurales, pero no garantizan
equivalencia semántica. Toda salida automática queda pendiente de revisión. Los
rankings reales solo consumen variantes `reviewed`; la excepción para variantes
`generated` se restringe a un manifiesto fake técnico.

### Consecuencias

No se incorporan silenciosamente salidas con topónimos, negaciones, números u
orientaciones alterados. Los rankings permanecen independientes y no se fusionan
scores ni coordenadas.

## D062 — Validación real Qwen3-8B en GB10

**Estado:** ACEPTADA
**Componente:** F5 / ejecución local
**Fecha:** 2026-10-19
**Origen:** Autorización expresa F5.2b para descargar y ejecutar el modelo exacto.

### Decisión

F5.2 utiliza `Qwen/Qwen3-8B` exclusivamente en la revisión
`b968826d9c46dd6066d109eabc6255188de91218`, almacenada fuera de Git. La
ejecución usa el adaptador local-only, modo non-thinking, sin muestreo y sin
fine-tuning. Otros modelos Qwen locales no se consideran sustitutos.

Qwen se cierra antes de cargar CrossText2Loc. Las variantes automáticas se
revisan mediante decisiones humanas explícitas antes de rankings reales.

### Evidencia y consecuencias

La carga real en GB10, dos lotes reproducibles de 18 variantes y 48 rankings
CrossText2Loc Top-10 completaron correctamente. Los resultados son sondas
técnicas sin ground truth; no demuestran mejora de precisión. Pesos y resultados
permanecen fuera de Git.

## D063 — Evidencia textual exacta en F5.3

**Estado:** ACEPTADA
**Componente:** F5 / extracción estructurada
**Fecha:** 2026-10-20
**Origen:** Requisitos F5.3 solicitados por el responsable.

### Decisión

Toda entidad, atributo, relación y negación F5.3 debe enlazar un substring exacto
del texto de la variante mediante span Unicode verificable. El extractor no
puede emitir coordenadas, distancias inventadas o referencias inexistentes.
Izquierda/derecha permanecen egocéntricas y una orientación no puede declararse
verificada a partir del texto.

### Consecuencias

Los outputs no se reparan silenciosamente. Un error de span, negación, referencia
o frame rechaza el record y conserva la salida raw para auditoría.

## D064 — F5.3 no apta todavía para integración automática

**Estado:** ACEPTADA
**Componente:** F5 / alcance
**Fecha:** 2026-10-20
**Origen:** Resultado del smoke real Qwen3-8B.

### Decisión

Aunque la infraestructura y la inferencia real F5.3 funcionan, Qwen3-8B no
cumplió de forma fiable el contrato estricto: la mejor campaña obtuvo 1/10
extracciones válidas. Por ello no se conecta a preselección OSM, diálogo, VLM,
API ni ranking.

### Consecuencias

El resultado se documenta como limitación experimental, no se oculta ni se
compensa relajando validadores. Una fase posterior deberá estudiar otra estrategia
de evidencia/offsets y un dataset anotado antes de integrar el componente.

## D065 — F5.3b mantiene bloqueada la integración automática

**Estado:** ACEPTADA
**Componente:** F5 / generación estructurada
**Fecha:** 2026-10-20
**Origen:** Resultado experimental F5.3b solicitado por el responsable.

### Decisión

F5.3b compara baseline, evidencia literal con offsets deterministas y JSON Schema
guiado. Los offsets solo se resuelven cuando la evidencia tiene una aparición
literal única; cero o varias coincidencias se rechazan. El validador final no se
relaja.

LM Format Enforcer 0.11.3 queda aceptado como dependencia opcional y aislada para
el experimento guiado. No se incorpora al MVP ni al entorno CrossText2Loc. La
mejor estrategia produjo 5/10 records contractualmente válidos sobre sondas
development, por lo que F5.3/F5.3b sigue sin conectarse a componentes posteriores.

### Consecuencias

La mejora estructural no se presenta como exactitud semántica. Se mantienen la
revisión humana y D064. Una evaluación futura necesita anotaciones humanas
congeladas y particiones separadas.

## D066 — Contrato textual v2 para `en_cartographic`

**Estado:** ACEPTADA
**Componente:** F5 / variantes textuales
**Fecha:** 2026-10-20
**Origen:** Alcance F5.3b solicitado expresamente.

### Decisión

`f5-textual-variant-dataset-v2` exige cinco variantes y añade
`en_cartographic`. El contrato v1 conserva exactamente cuatro; no se migran ni
reinterpretan artefactos históricos. La nueva tarea usa
`f53b-text-transform-v2`, protección de topónimos y revisión humana obligatoria.

### Consecuencias

Los rankings continúan siendo exhaustivos e independientes, sin fusión. Los
resultados observados son estabilidad sin ground truth y no demuestran que la
variante mejore precisión geográfica o extracción.

## D001 — Identidad del candidato

**Estado:** ACEPTADA  
**Componente:** Catálogo  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1 y aceptación expresa del responsable del TFG.

### Contexto

El catálogo necesita una unidad estable que no dependa del nombre de una imagen,
de una tesela descargada, de un embedding concreto ni de una representación de
un modelo.

### Decisión / propuesta

Cada `candidate_id` representaría una celda de una cuadrícula geográfica. La
posición asociada sería el centro de la celda. El identificador sería
independiente de la imagen OSM, el embedding, las teselas utilizadas para el
renderizado y los Scene Graphs de GOTPR. Todos esos artefactos se relacionarían
mediante `candidate_id`.

Ejemplo de serialización compatible, todavía no fijado:

```text
MADP_G25_R003_C012
```

### Justificación

Separa la identidad geográfica de los artefactos regenerables y permite cambiar
el renderizador o el modelo sin renumerar el catálogo. CrossText2Loc asocia sus
imágenes a coordenadas, pero no define un identificador persistente para una
ciudad nueva.

### Alternativas consideradas

- Usar latitud y longitud como identificador.
- Usar el nombre de la imagen OSM.
- Usar el identificador de una tesela.
- Reutilizar `scene_id` de GOTPR.

### Consecuencias

La coordenada, los artefactos y sus hashes deberán resolverse mediante un
manifest. Cambiar la cuadrícula exigirá una nueva versión del catálogo.

### Evidencia

- [Requisitos de los modelos](DATASET_MODEL_REQUIREMENTS.md#asociación-con-coordenadas):
  CVG-Text obtiene las coordenadas del nombre del archivo y no proporciona
  `candidate_id`.
- [`evaluate.py`](../external/CVG-Text/evaluate.py#L20-L24) extrae latitud y
  longitud del nombre de la imagen.

### Dependencias

D002, D003, D004, D005, D006, D010, D011 y D012.

### Pendiente

Ninguno sobre la semántica. El número de dígitos reservado para fila y columna
se fijará al concretar el esquema físico sin cambiar esta decisión.

## D002 — Unidad métrica y sistemas de coordenadas

**Estado:** ACEPTADA  
**Componente:** Catálogo  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1 y aceptación expresa del responsable del TFG.

### Contexto

Una separación expresada directamente en grados no mantiene una distancia
uniforme. El catálogo también debe interoperar con entradas y salidas en
latitud/longitud.

### Decisión / propuesta

Construir la cuadrícula en EPSG:25830, adecuado para expresar distancias métricas
en Madrid, y transformar los centros a WGS84 (EPSG:4326). La celda sería la unidad
de cobertura del catálogo y su centro la coordenada representativa devuelta por
el recuperador.

### Justificación

Permite fijar en metros el tamaño y la separación, evitando utilizar diferencias
angulares como si fueran distancias constantes.

### Alternativas consideradas

- Generar la cuadrícula directamente en EPSG:4326.
- Tratar cada candidato solamente como un punto sin región de cobertura.
- Adoptar las teselas Web Mercator como unidad del catálogo.

### Consecuencias

El manifest deberá conservar la geometría o índices de la celda, sus coordenadas
proyectadas y el centro transformado a WGS84. El renderizado OSM podrá usar otro
CRS sin cambiar la identidad del candidato.

### Evidencia

Es una decisión de diseño del TFG; no está impuesta por CrossText2Loc ni GOTPR.
CVG-Text transforma sus puntos WGS84 a EPSG:3857 únicamente para descargar la
imagen OSM en [`download_osm_street.py`](../external/CVG-Text/download_osm_street.py#L31-L47).

### Dependencias

D001, D003, D004 y D012.

### Pendiente

Ninguno sobre EPSG:25830, la transformación a WGS84 y el centro de celda como
coordenada representativa.

## D003 — Granularidad inicial de 25 metros

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** Catálogo  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1, «Definición del catálogo de Madrid».

### Contexto

La granularidad controla el número de candidatos, el error de discretización y
el coste de generar imágenes y embeddings. CrossText2Loc no impone en el código
auditado una cuadrícula para ciudades nuevas.

### Decisión / propuesta

Probar como configuración inicial:

```text
cell_size_m = 25
spacing_m = 25
```

Debe compararse al menos con una separación de 50 m antes de adoptarse como
configuración definitiva. Se autoriza su uso provisional en el piloto, pero esa
autorización no constituye validación de que 25 m sea la mejor granularidad.

### Justificación

Una celda cuadrada de 25 m tiene una distancia máxima aproximada de 17,7 m desde
cualquier punto al centro. Ofrece una discretización fina, aunque aumenta el
número de representaciones y el solapamiento.

### Alternativas consideradas

- Cuadrícula de 50 m, de menor coste y mayor error de discretización.
- Puntos muestreados sobre la red peatonal o viaria.
- Densidad adaptativa según la estructura urbana.

### Consecuencias

Combinada con D004 produciría aproximadamente 1.224 candidatos. Esta cifra es
una estimación, no una constante: el total real dependerá de la proyección, la
regla de inclusión de bordes y la cuadrícula finalmente generada.

### Evidencia

Es una propuesta del TFG. La documentación auditada mantiene pendiente definir
qué cuenta como candidato correcto y distingue recuperación por regiones de
precisión métrica en [PROJECT.md](PROJECT.md#evaluación).

### Dependencias

D001, D002, D004, D005 y D012.

### Pendiente

Diseñar y ejecutar un experimento controlado de 25 m frente a 50 m, midiendo
recall, error geográfico, coste y sensibilidad al solapamiento. Este experimento
no debe comenzar hasta validar D007.

## D004 — Bounding box del piloto de Madrid

**Estado:** ACEPTADA  
**Componente:** Catálogo piloto  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1 y aceptación expresa para el piloto.

### Contexto

El piloto debe ser pequeño para validar el proceso sin generar Madrid completo.

### Decisión / propuesta

Utilizar exclusivamente para el piloto:

```yaml
north: 40.4200
south: 40.4120
east: -3.6990
west: -3.7090
```

La extensión aproximada es 0,75 km². No se considera la región definitiva del
TFG.

### Justificación

Permite probar el catálogo en una zona urbana céntrica y mantener limitado el
número de artefactos.

### Alternativas consideradas

- Otra bbox pequeña propuesta por el responsable del TFG.
- Madrid completo, descartado para el piloto inicial por coste y riesgo.

### Consecuencias

Con la granularidad propuesta en D003 se estiman unos 1.224 candidatos. El total
deberá calcularse y registrarse al construir la cuadrícula.

### Evidencia

Es una propuesta de diseño, no un requisito de los modelos. El proyecto ya exige
un catálogo offline limitado a una zona piloto en [PROJECT.md](PROJECT.md#obtención-automática-de-datos-y-papel-del-llm).

### Dependencias

D002, D003 y D012.

### Pendiente

La extensión final de Madrid será otra decisión. La aceptación de esta bbox no
se extiende fuera del piloto.

## D005 — Solapamiento y deduplicación de candidatos

**Estado:** ACEPTADA  
**Componente:** Catálogo  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1, «Definición del catálogo de Madrid».

### Contexto

El tamaño de una celda y el área visible en una imagen OSM son conceptos
distintos. Dos imágenes centradas en celdas vecinas pueden compartir una parte
importante del mapa.

### Decisión / propuesta

Permitir el solapamiento de footprints visuales. No eliminar candidatos por
tener imágenes visualmente similares. Eliminar únicamente duplicados de
identidad o coordenada producidos por errores de generación y registrar el
footprint real de cada imagen.

### Justificación

La similitud visual no implica que dos posiciones sean la misma ubicación. Una
deduplicación por imagen degradaría la cobertura espacial y haría depender la
geometría del catálogo del renderizador.

### Alternativas consideradas

- Eliminar imágenes casi idénticas mediante un umbral visual.
- Igualar el tamaño de celda al footprint de CrossText2Loc.
- Prohibir cualquier solapamiento.

### Consecuencias

Existirán embeddings similares para ubicaciones próximas. La evaluación deberá
usar coordenadas y tolerancias, además del identificador exacto cuando proceda.

### Evidencia

CVG-Text genera cada imagen alrededor de un punto y una ventana espacial en
[`download_osm_street.py`](../external/CVG-Text/download_osm_street.py#L55-L65);
no define una regla de deduplicación geográfica para Madrid.

### Dependencias

D003, D006 y D007.

### Pendiente

Validar el efecto del solapamiento y de la granularidad dentro del experimento
de D003. La regla de no deduplicar por similitud ya está aceptada.

## D006 — Catálogo offline para CrossText2Loc

**Estado:** ACEPTADA  
**Componente:** CrossText2Loc  
**Fecha:** 2026-10-01  
**Origen:** Arquitectura del proyecto solicitada y documentada antes de la
pregunta 1.

### Contexto

Las imágenes y sus embeddings no deben descargarse o recalcularse para cada
consulta.

### Decisión / propuesta

La relación conceptual será:

```text
candidate_id → coordenada central → imagen OSM → embedding CrossText2Loc
```

Las representaciones visuales y sus embeddings se prepararán offline. Durante la
consulta solo se codificará el texto y se comparará con los embeddings de los
candidatos preseleccionados.

### Justificación

Reduce coste y latencia, hace reproducible la galería y coincide con la
arquitectura offline solicitada para el proyecto.

### Alternativas consideradas

- Descargar OSM y recalcular embeddings para cada consulta.
- Generar únicamente representaciones de los candidatos después del filtro.

### Consecuencias

Será necesario versionar imágenes, modelo, checkpoint, preprocesamiento y
embeddings. Esta decisión no confirma todavía ningún perfil concreto de imagen.

### Evidencia

- [PROJECT.md](PROJECT.md#obtención-automática-de-datos-y-papel-del-llm) fija la
  reutilización del catálogo offline.
- [`evaluate.py`](../external/CVG-Text/evaluate.py#L36-L58) muestra
  `encode_image`, `encode_text`, normalización y producto matricial.
- [DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#embeddings-y-retrieval)
  documenta la adaptación de indexación sin modificar los pesos.

### Dependencias

D001, D007 y D012.

### Pendiente

Resolver D007 antes de generar imágenes o embeddings del piloto.

## D007 — Perfil de imagen OSM compatible con CrossText2Loc

**Estado:** PENDIENTE DE AUTORES  
**Componente:** CrossText2Loc  
**Fecha:** 2026-10-01  
**Origen:** Auditoría local de CVG-Text y pregunta 1.

### Contexto

El checkpoint solo debe evaluarse con imágenes cuyo estilo, escala, resolución y
preprocesamiento sean compatibles. El script publicado presenta una
inconsistencia entre el recorte calculado y el archivo guardado.

### Decisión / propuesta

No fijar ni generar masivamente imágenes hasta determinar:

- footprint geográfico efectivo;
- procedimiento de renderizado que produjo los raster de entrenamiento;
- zoom y escala geográfica efectivos;
- comportamiento correcto de `download_osm_street.py`.

El valor aproximado de 51,2 m inferido durante el análisis no es una decisión ni
un hecho confirmado; es una interpretación pendiente de verificar.

### Justificación

El script define `pixel_size = 0.2627`, recorte de 256 píxeles, salida prevista
de 512 píxeles y zoom 18, pero guarda `img` en vez de `img_crop`. El historial
oficial solo contiene un commit para este archivo (`bf348509...`, «Add files via
upload»), por lo que no aporta una versión anterior o una corrección. No se puede
deducir de forma inequívoca la imagen usada para entrenar el checkpoint.

Clasificación de los parámetros reconstruidos:

| Parámetro | Estado | Evidencia y límite |
|---|---|---|
| Tamaño del raster OSM del dataset: 512 × 512 | CONFIRMADO | El artículo lo declara expresamente. El script también calcula esa salida, aunque no guarda la variable redimensionada. |
| Entrada del encoder: 336 × 336 | CONFIRMADO | El artículo fija 336 × 336 y `model_loader.py` carga `ViT-L/14@336px`. |
| Conversión a RGB | CONFIRMADO | `dataset.py` abre cada imagen y aplica `convert("RGB")`. |
| Preprocesamiento del encoder propuesto | CONFIRMADO | Se usa el `preprocess` de OpenAI CLIP: resize bicúbico, center crop a 336, RGB, tensor y normalización CLIP. `requirements.txt` fija el commit de CLIP. |
| Contexto textual de 300 tokens con EPE | CONFIRMADO | Artículo y `model_loader.py:21,112-135`. |
| Zoom 18 | CONFIRMADO solo para el script publicado | `download_osm_street.py:57-65`; no demuestra por sí solo que los raster de entrenamiento se generaran exactamente con esa versión. |
| `pixel_size = 0.2627`, crop 256 y resize 512 | CONFIRMADO solo como operaciones calculadas | `download_osm_street.py:20-23,67-73`. |
| El script publicado guarda `img`, no `img_crop` | CONFIRMADO | `download_osm_street.py:74`. La dimensión efectiva depende del mosaico devuelto por `contextily`. |
| Que los autores pretendían guardar `img_crop` | INFERIBLE | Calcular y redimensionar `img_crop` para no usarlo sugiere un error, pero no prueba la intención. |
| Extensión OSM cercana a la imagen satelital | INFERIBLE | El artículo afirma que ambas extensiones son cercanas; para satélite indica 512 × 512, zoom 20 y alrededor de 0,12 m/píxel. |
| Footprint OSM exacto | NO DETERMINABLE | El artículo no da una medida y el script contradice su recorte con la variable guardada. |
| Escala OSM exacta de entrenamiento | NO DETERMINABLE | `pixel_size`, zoom, bbox, crop y salida guardada no forman un procedimiento inequívoco. |
| Valor de aproximadamente 51,2 m | NO CONFIRMADO | Es una derivación de una interpretación de `dis` en Madrid, no una propiedad publicada del dataset. |

Perfil provisional incompleto: raster OSM centrado en la coordenada, almacenado
en 512 × 512 y transformado después con el preprocesamiento oficial de
CLIP-L/14@336. No se fija todavía el footprint ni se autoriza la generación
masiva. El zoom 18 del script solo puede ensayarse en una fixture y compararse
con una muestra oficial.

### Alternativas consideradas

- Corregir directamente la línea de guardado y asumir que expresa la intención.
- Reproducir la salida literal del script publicado.
- Elegir una escala propia para Madrid.

Ninguna se adopta sin evidencia adicional.

### Consecuencias

D003 y la generación del catálogo visual permanecen condicionadas. Las imágenes
de prueba deberán etiquetarse como no confirmadas hasta resolver esta decisión.

### Evidencia

- [`download_osm_street.py`](../external/CVG-Text/download_osm_street.py#L20-L23)
  declara los tamaños.
- [`download_osm_street.py`](../external/CVG-Text/download_osm_street.py#L57-L74)
  descarga, recorta y redimensiona, pero guarda la variable original.
- [DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#imágenes-osm)
  documenta la discrepancia.
- El [artículo oficial](https://arxiv.org/html/2412.17007v2) declara raster OSM
  de 512 × 512, entrada de modelo de 336 × 336 y contexto de 300 tokens.
- [`requirements.txt`](../external/CVG-Text/requirements.txt) fija OpenAI CLIP
  en el commit `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1`, cuyo preprocesamiento está
  por tanto determinado.
- Repositorio auditado en el commit
  `6910d2747a94fbe985309bde60cd4732bcbbf50f`.

### Dependencias

D003, D005, D006, D012 y D013.

### Pendiente

Comparar con una muestra oficial y preguntar a los autores si los raster de
entrenamiento se generaron guardando `img` o `img_crop`, además de su footprint,
zoom y escala efectivos. No interpretar una respuesta parcial como confirmación
de todos los parámetros.

## D008 — Separación inicial de OSM y satélite

**Estado:** ACEPTADA  
**Componente:** Satélite  
**Fecha:** 2026-10-01  
**Origen:** Arquitectura solicitada y regla expresa al crear este registro.

### Contexto

CVG-Text admite seleccionar distintas fuentes de imagen, pero el código auditado
no demuestra una fusión automática de sus embeddings para la adaptación de
Madrid.

### Decisión / propuesta

OSM y satélite serán modalidades independientes inicialmente:

```text
candidate_id
├── osm_embedding
└── satellite_embedding
```

No se asumirá que se pueden mezclar imágenes o embeddings sin una estrategia
explícita.

CrossText2Loc con OSM será la modalidad inicial del MVP. Satélite queda pospuesto
como extensión experimental y no bloquea el MVP.

### Justificación

Permite evaluar cada modalidad con su configuración y evita atribuir al modelo
una fusión que no aparece en el pipeline auditado.

### Alternativas consideradas

- Concatenar embeddings.
- Promediar embeddings.
- Combinar imágenes antes del encoder.
- Fusionar rankings o puntuaciones.

Estas alternativas pasan a D009.

### Consecuencias

Cada artefacto deberá indicar modalidad, modelo, checkpoint y preprocesamiento.
El MVP puede construirse solo con OSM.

### Evidencia

[`zeroshot.py`](../external/CVG-Text/zeroshot.py#L40-L45) selecciona un directorio
distinto según `img_type` (`sat`, `osm` o `stv`).

### Dependencias

D009, D012 y D014.

### Pendiente

Ninguno para la separación inicial. El proveedor y uso de satélite siguen
pendientes por separado.

## D009 — Estrategia de combinación OSM–satélite

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** Satélite  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1, «Definición del catálogo de Madrid».

### Contexto

Una modalidad adicional solo se justifica si aporta información y puede usarse
con permisos adecuados.

### Decisión / propuesta

No elegir todavía una técnica de fusión. Si se incorpora satélite, comparar sus
resultados independientes con alternativas explícitas de combinación de scores
o rankings.

### Justificación

La fusión no está especificada por el código auditado y puede alterar la escala
de las puntuaciones.

### Alternativas consideradas

- Fusión temprana de imágenes o características.
- Fusión tardía de scores.
- Fusión de rankings.
- Mantener modalidades como baselines independientes.

### Consecuencias

Los índices y resultados de cada modalidad deben poder evaluarse por separado.

### Evidencia

D008 y la selección exclusiva de modalidad en
[`zeroshot.py`](../external/CVG-Text/zeroshot.py#L40-L45).

### Dependencias

D008, D012 y las decisiones de proveedor y permisos.

### Pendiente

Elegir proveedor y perfil permitido; después diseñar el experimento de fusión.

## D010 — Independencia entre candidatos y scenes de GOTPR

**Estado:** ACEPTADA  
**Componente:** GOTPR  
**Fecha:** 2026-10-01  
**Origen:** Evidencia de la auditoría local y regla expresa al crear este
registro.

### Contexto

GOTPR identifica grafos mediante `scene_id`, pero no publica el constructor
geográfico necesario para demostrar que una scene equivale a una celda del
catálogo de Madrid.

### Decisión / propuesta

`candidate_id` y `scene_id` serán identificadores distintos. No se asumirá que
una celda de 25 m equivale a una scene de GOTPR.

### Justificación

Evita fijar una equivalencia espacial no respaldada por código o documentación y
permite mantener estable el catálogo si las scenes tienen otra extensión.

### Alternativas consideradas

- Usar `scene_id` como `candidate_id`.
- Crear exactamente una scene por celda.

Ambas quedan descartadas mientras falte el proceso oficial de generación.

### Consecuencias

La integración, si resulta reproducible, necesitará una relación explícita entre
candidatos y scenes.

### Evidencia

- [`scene_graph.py`](../external/GOTPR/scene_graph.py#L46-L65) conserva
  `scene_id` en cada grafo.
- [DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#datos-publicados-y-límites-de-reproducibilidad)
  documenta que no se encontró el generador OSM→Scene Graph.
- Repositorio auditado en el commit
  `4d6d12582ec51228d0a78438deaa4b1e2b349e52`.

### Dependencias

D001, D011 y D012.

### Pendiente

Ninguno sobre la separación de identificadores. La integración concreta depende
de D011.

## D011 — Asociación entre candidatos y scenes de GOTPR

**Estado:** PENDIENTE DE AUTORES  
**Componente:** GOTPR  
**Fecha:** 2026-10-01  
**Origen:** Auditoría local de GOTPR y pregunta 1.

### Contexto

No se conoce la geometría exacta de las scenes ni su asociación oficial con
coordenadas. Por ello no puede fijarse una correspondencia uno-a-uno.

### Decisión / propuesta

Reservar conceptualmente una relación:

```text
candidate_id ↔ 0..N scene_id
```

La cardinalidad y la regla espacial no quedan decididas. No se generarán Scene
Graphs de Madrid hasta conocer el proceso oficial o adoptar explícitamente una
alternativa experimental incompatible con el checkpoint publicado.

### Justificación

Una scene podría cubrir varias celdas y una celda podría intersectar varias
scenes. Forzar una correspondencia introduciría una geometría inventada.

### Alternativas consideradas

- Contención del centro del candidato.
- Intersección de geometrías.
- Proximidad entre centroides.
- Correspondencia uno-a-uno.

### Consecuencias

Los campos GOTPR permanecerán vacíos o con estado `pending` en el manifest. La
ausencia de GOTPR no bloquea el MVP basado en CrossText2Loc.

### Evidencia

- [`scene_graph.py`](../external/GOTPR/scene_graph.py#L46-L120) consume grafos ya
  estructurados.
- [`scene_graph_candidates_extraction.py`](../external/GOTPR/scene_graph_candidates_extraction.py#L8-L75)
  indexa grafos existentes y devuelve sus identificadores, pero no los construye
  desde OSM.
- [DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#datos-publicados-y-límites-de-reproducibilidad)
  recoge los límites de reproducción.

### Dependencias

D010 y D012.

### Pendiente

Solicitar a los autores la generación de Scene Graphs, geometría de scenes,
asociación `scene_id`–coordenadas y compatibilidad del checkpoint con Madrid.

## D012 — Manifest versionado del catálogo

**Estado:** ACEPTADA  
**Componente:** Dataset  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 1 y aceptación expresa del responsable del TFG.

### Contexto

El catálogo necesita una relación reproducible entre su geometría y artefactos
regenerables o todavía no disponibles.

### Decisión / propuesta

Mantener un manifest versionado con la relación:

```text
candidate_id
→ grid
→ coordenadas
→ imagen OSM
→ embedding OSM
→ imagen/embedding satelital opcional
→ scene/representación GOTPR opcional
```

El manifest registraría como mínimo versión del catálogo, bbox, CRS, versión o
fecha de OSM, modelo, checkpoint, preprocesamiento y hashes cuando corresponda.
Los valores desconocidos usarían `null` y un estado explícito como `pending`, no
valores inferidos.

### Justificación

Separa metadatos e identidad de los ficheros físicos y permite reproducir qué
datos y transformaciones produjeron cada representación.

### Alternativas consideradas

- Codificar todos los metadatos en nombres de archivo.
- Mantener manifests independientes sin una clave común.
- Depender exclusivamente de una base de datos de embeddings.

### Consecuencias

Los índices deberán conservar su correspondencia de filas con `candidate_id`.
Los esquemas concretos y formatos físicos todavía deben decidirse antes de
implementar.

### Evidencia

- [DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#asociación-con-coordenadas)
  ya exige relacionar identificador, coordenadas, imagen y generación.
- [PROJECT.md](PROJECT.md#obtención-automática-de-datos-y-papel-del-llm) exige
  registrar cobertura, fuentes y transformaciones.

### Dependencias

D001–D011.

### Pendiente

Definir el formato físico y cerrar los campos dependientes de los perfiles de
los modelos. El uso del manifest y su contenido mínimo ya están aceptados.

## D013 — Checkpoint CrossText2Loc provisional para el MVP

**Estado:** PENDIENTE DE AUTORES  
**Componente:** CrossText2Loc  
**Fecha:** 2026-10-01  
**Origen:** Revisión del código, artículo y repositorio oficial de checkpoints.

### Contexto

Los autores publican tres checkpoints OSM específicos por ciudad. No publican un
checkpoint conjunto de las tres ciudades ni uno entrenado para Madrid.

### Decisión / propuesta

Usar como primera opción provisional del MVP:

```text
long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

El encoder asociado es OpenAI CLIP `ViT-L/14@336px`, cargado en el repositorio
como `CLIP-L/14@336`, con Expanded Positional Embedding y contexto de 300 tokens
al ejecutar con `--expand`.

### Justificación

Es un checkpoint de la modalidad OSM, está publicado y es directamente cargable
por el pipeline oficial. Entre los tres pesos OSM publicados obtiene el mayor
R@1 en su propia ciudad: Nueva York 59,08, frente a Brisbane 46,08 y Tokio 34,33.
Nueva York es además el dominio publicado más próximo a Madrid por carácter
urbano y uso principal de alfabeto latino. Esta última comparación es una
inferencia de transferencia, no un resultado experimental.

### Alternativas consideradas

- Brisbane OSM: publicado y reproducible, pero entrenado en un entorno descrito
  por el artículo como más suburbano y con menor R@1 OSM.
- Tokio OSM: publicado, pero el artículo identifica el idioma japonés como una
  dificultad para CLIP y presenta el menor R@1 OSM.
- CLIP base sin fine-tuning de CrossText2Loc: más genérico, pero no reproduce el
  método ni sus resultados OSM publicados.

### Consecuencias

Se podrá preparar una validación mínima con el mismo encoder y preprocesamiento,
pero no descargar el peso ni construir el catálogo completo hasta cerrar D007.
El nombre del archivo no demuestra rendimiento fuera de Nueva York.

### Evidencia

- [`scripts/evaluate.sh`](../external/CVG-Text/scripts/evaluate.sh) identifica el
  checkpoint OSM de Nueva York y `CLIP-L/14@336 --expand`.
- [`model_loader.py`](../external/CVG-Text/model_loader.py#L21-L43) carga
  `ViT-L/14@336px` y amplía posteriormente el contexto a 300 tokens.
- El [repositorio oficial de pesos](https://huggingface.co/CVG-Text/CrossText2Loc/tree/main)
  publica los tres checkpoints OSM; el de Nueva York ocupa aproximadamente
  1,71 GB.
- La [Tabla 2 del artículo](https://arxiv.org/html/2412.17007v2) informa R@1 OSM
  59,08 para Nueva York, 46,08 para Brisbane y 34,33 para Tokio sin ERM.

### Dependencias

D006 y D007.

### Pendiente

Esperar la recomendación de los autores sobre el checkpoint más razonable para
transferencia *zero-shot* a Madrid. Después habrá que validar que el peso carga
sin claves incompatibles, reproducir una evaluación oficial pequeña y medir la
transferencia a una muestra de Madrid. Si falla por dominio, se compararán los
tres checkpoints OSM bajo el mismo protocolo. Este pendiente no bloquea el
diseño del catálogo ni de la preselección, pero sí la evaluación definitiva de
CrossText2Loc en el MVP.

## D014 — Satélite pospuesto fuera del MVP

**Estado:** ACEPTADA  
**Componente:** Satélite  
**Fecha:** 2026-10-01  
**Origen:** Decisión expresa de posponer la modalidad satelital.

### Contexto

El proveedor debe permitir uso académico, almacenamiento local, procesamiento
con modelos externos, embeddings derivados, publicación de resultados y
reproducción. No se ha confirmado que Google Satellite permita todo ese flujo.

### Decisión / propuesta

Posponer satélite y no descargar imágenes. Priorizar posteriormente fuentes
abiertas o con condiciones claras para investigación reproducible. Google
Satellite solo podrá considerarse si sus términos autorizan expresamente el flujo
completo.

### Justificación

Satélite no es necesario para el MVP CrossText2Loc+OSM y una elección prematura
podría impedir almacenar o publicar los artefactos experimentales.

### Alternativas consideradas

- Google Satellite.
- Proveedores comerciales con licencia académica.
- Fuentes abiertas de observación terrestre.

No se selecciona todavía ninguna.

### Consecuencias

Los campos satelitales del manifest permanecerán `null` o `pending`. D009 no se
ejecutará hasta resolver proveedor, licencia y perfil de imagen.

### Evidencia

[LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md) ya impide asumir que
Google autoriza caché, embeddings derivados o redistribución para este TFG.

### Dependencias

D008, D009 y D012.

### Pendiente

Ninguno respecto a su exclusión del MVP. La incorporación futura depende de
D015 y D009.

## D015 — Proveedor y licencia para imágenes satelitales

**Estado:** PENDIENTE DE VALIDACIÓN  
**Componente:** Satélite  
**Fecha:** 2026-10-01  
**Origen:** Condición expresa para reconsiderar la modalidad satelital.

### Contexto

La decisión D014 pospone la modalidad, pero una extensión futura necesita
identificar una fuente legal y técnicamente reproducible.

### Decisión / propuesta

No seleccionar proveedor todavía. La futura comparación priorizará fuentes
abiertas y exigirá permisos claros para uso académico, almacenamiento local,
procesamiento mediante modelos externos, embeddings derivados, publicación de
resultados y reproducción. Google Satellite solo podrá utilizarse si sus términos
autorizan expresamente todo ese flujo.

### Justificación

La disponibilidad de una API o de imágenes visibles no implica permiso para
cachearlas, procesarlas y conservar derivados.

### Alternativas consideradas

- Google Satellite.
- Proveedores comerciales con licencia académica.
- Fuentes abiertas de observación terrestre.

### Consecuencias

No se descargarán imágenes satelitales ni se ejecutará D009 hasta resolver esta
decisión. No bloquea el MVP.

### Evidencia

[LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md) documenta que no se
pueden asumir permisos de almacenamiento, procesamiento o redistribución para
Google Satellite.

### Dependencias

D008, D009, D012 y D014.

### Pendiente

Investigar proveedores y verificar sus términos o conseguir autorización
escrita.

## D016 — Licencia de los artefactos publicados por CVG-Text

**Estado:** PENDIENTE DE AUTORES  
**Componente:** Licencias  
**Fecha:** 2026-10-01  
**Origen:** Cierre provisional de la pregunta 2.

### Contexto

La información publicada no permite atribuir inequívocamente una licencia a
todos los checkpoints y datos de CVG-Text que podría utilizar el TFG.

### Decisión / propuesta

Solicitar a los autores las condiciones aplicables a los pesos y datos. Mientras
llega la respuesta, se permite continuar el diseño, pero no se presupone permiso
para redistribuir checkpoints, imágenes o derivados.

### Consecuencias

No bloquea el diseño ni una auditoría local. Debe resolverse antes de publicar o
redistribuir artefactos y antes de afirmar que el experimento es reproducible por
terceros bajo unas condiciones concretas.

### Dependencias

D006, D007 y D013.

### Pendiente

Respuesta de los autores de CVG-Text.

## D017 — Contrato del LLM como parser geográfico

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Contexto

La salida libre de un LLM no es una interfaz segura ni reproducible para
consultar OSM. Tampoco corresponde al LLM conocer el inventario de
`candidate_id` ni producir consultas ejecutables.

### Decisión / propuesta

El LLM solo transformará la descripción y la zona proporcionada en un JSON
validado contra un esquema cerrado y versionado. Extraerá objetos, atributos,
relaciones, distancias, orientación, negación, evidencia textual e
incertidumbre. No emitirá Overpass QL, etiquetas OSM arbitrarias, coordenadas
inventadas ni identificadores de candidatos.

Todos los proveedores y modelos se integrarán detrás de la misma interfaz y
deberán producir este mismo JSON Schema. La zona deberá proceder del usuario o
de la configuración del catálogo. Si no
existe, se usará explícitamente la región configurada; nunca se inferirá una bbox
como hecho sin registrar esa inferencia.

### Justificación

Separa una etapa probabilística de las operaciones geográficas deterministas,
permite validar y repetir cada ejecución y evita ejecutar texto generado como
consulta.

### Evidencia

- SPOT demuestra la utilidad de convertir lenguaje natural en una
  representación geográfica estructurada antes de consultar OSM, pero su YAML,
  su modelo ajustado y su backend PostGIS no son requisitos de CVG-Text ni de
  GOTPR.
- CrossText2Loc recibe directamente la descripción en su encoder de texto; la
  representación estructurada es un componente de integración propio y no
  sustituye ese texto.

### Consecuencias

La descripción original continuará llegando intacta al recuperador. El JSON se
usará exclusivamente para preselección, explicabilidad y fases posteriores.

### Pendiente

La elección posterior de proveedor/modelo LLM se realizará sin cambiar este
contrato y se registra por separado en D026.

## D018 — Compilación controlada de conceptos a OSM

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Decisión / propuesta

Un enriquecedor determinista convertirá los tipos y atributos canónicos del JSON
en alternativas de etiquetas OSM procedentes de un vocabulario permitido,
versionado y revisable. Un compilador posterior generará filtros para el índice
local o una consulta Overpass equivalente. Las alternativas de etiquetado de un
mismo concepto se combinarán como unión; no se confiará en que el LLM conozca el
esquema de etiquetado real de OSM.

Cada pista quedará clasificada como:

- `hard`: explícita, cartografiable, estable y con una relación espacial segura;
- `soft`: útil para puntuar, pero no segura para excluir;
- `visual_only`: color, material visible, estado transitorio u otra información
  que OSM no representa de forma fiable.

La confianza numérica del LLM solo ordenará relajaciones y contribuciones al
score; no bastará por sí sola para convertir una pista en filtro duro. En el MVP,
las negaciones y las relaciones egocéntricas sin orientación conocida nunca
serán filtros duros.

### Justificación

OSM admite múltiples esquemas para conceptos similares y tiene cobertura
incompleta. Esta separación reduce alucinaciones de etiquetas y falsos negativos.

### Evidencia

SPOT utiliza agrupaciones semánticas de etiquetas OSM y documenta la
inconsistencia del etiquetado como dificultad. Overpass combina filtros de
etiqueta y operaciones espaciales, pero no resuelve por sí mismo la equivalencia
semántica entre expresiones y etiquetas.

### Dependencias

D017.

### Pendiente

Construir y revisar el vocabulario inicial del piloto sin pretender cubrir todo
OSM.

## D019 — Fuente reproducible de OSM para la preselección

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3, arquitectura offline y aceptación expresa del
responsable del TFG.

### Decisión / propuesta

La preselección ordinaria consultará el mismo snapshot OSM local y versionado
con el que se creó el catálogo. Overpass se utilizará para adquisición,
prototipado o recuperación controlada y cacheada cuando falte información, no
como dependencia obligatoria en cada consulta de usuario.

El compilador tendrá una representación intermedia común y adaptadores para el
índice geoespacial local y para Overpass QL. Una respuesta de Overpass será
evidencia OSM; los `candidate_id` se obtendrán después al intersectarla con el
manifest del catálogo.

### Justificación

Evita que cambios de OSM, límites de servicio o fallos de red alteren el
experimento. Overpass devuelve elementos y geometrías OSM, no identificadores de
nuestro catálogo.

### Dependencias

D001, D004 y D012.

### Pendiente

Elegir durante la implementación el índice local mínimo compatible con los
volúmenes del piloto.

## D020 — Preselección progresiva y fallback

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Decisión / propuesta

La preselección seguirá niveles reproducibles de estricto a relajado. Empezará
con la zona y las anclas OSM más fiables; incorporará tipos y proximidades como
score; si devuelve menos del mínimo, ensanchará radios y retirará, de menor a
mayor confianza, las condiciones no esenciales. Si todavía no hay resultados,
devolverá todos los candidatos de la zona declarada.

Si hay demasiados resultados, conservará los de mayor score con desempate
estable por `candidate_id`. Nunca ampliará silenciosamente la zona indicada. Una
zona inválida o ajena al catálogo producirá un error explícito, no un fallback
global.

### Justificación

El objetivo prioritario es no eliminar la ubicación correcta por información
OSM ausente, interpretación imperfecta o tolerancias demasiado estrictas.

### Consecuencias

La preselección es un acelerador y una fuente de evidencia, no el localizador
final. CrossText2Loc seguirá puntuando la descripción original frente a los
embeddings de los candidatos retenidos.

### Dependencias

D017–D019.

### Pendiente

Validación experimental de los parámetros de D021.

## D021 — Parámetros cuantitativos de preselección

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3.

### Propuesta inicial

Para el piloto se ensayarán como punto de partida:

- mínimo 100, objetivo 250 y máximo 500 candidatos, acotados siempre por el
  número disponible en la zona;
- radios semánticos iniciales de 25 m para `adjacent`, 100 m para `near` y
  250 m para `nearby`;
- relajación de radios por factores 1, 2 y 4, sin salir de la zona;
- tolerancia inicial de ±50 % para distancias expresadas como aproximadas;
- límites de complejidad del JSON y de la consulta todavía por fijar.

### Justificación

Son valores nuestros, no parámetros oficiales de CrossText2Loc, GOTPR ni OSM.
Sirven para iniciar un barrido que mida conjuntamente retención y reducción.

### Alternativas consideradas

- No preseleccionar en el piloto y recuperar sobre todo el catálogo.
- Aplicar una intersección estricta de todas las pistas.
- Elegir un único radio universal.

La primera será el baseline; las dos últimas elevan el riesgo de falsos
negativos.

### Dependencias

D003, D004 y D020.

### Pendiente

Validar tamaños, radios, tolerancias, pesos, umbrales de confianza, estrategia de
desempate y niveles de relajación con ejemplos que tengan ground truth.

## D022 — Correspondencia geométrica entre OSM y candidatos

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Decisión / propuesta

Los objetos recuperados de OSM se vincularán a candidatos mediante predicados
geométricos sobre el centro y la celda de D001. Las distancias se calcularán en
EPSG:25830 contra la geometría más próxima del objeto, no contra el centro
devuelto por `out center`. Para áreas se admitirán contención e intersección;
para proximidad, distancia mínima. El resultado siempre se intersectará con los
`candidate_id` existentes en el manifest.

### Justificación

El centro de una geometría OSM puede no representar su borde cercano e incluso
quedar fuera de un polígono cóncavo. La métrica proyectada mantiene coherencia
con la cuadrícula aceptada.

### Dependencias

D001, D002, D012 y D019.

### Pendiente

Comparar durante el experimento distancia desde el centro frente a
intersección/buffer de la celda.

## D023 — Trazabilidad de la preselección

**Estado:** ACEPTADA  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Decisión / propuesta

Cada ejecución registrará como mínimo: versión del esquema y prompt; modelo y
configuración del LLM; texto e idioma o su hash cuando proceda; salida original
y validada; versión del vocabulario OSM; snapshot y bbox; consultas o hash de
consulta; caché; niveles y parámetros de relajación; errores; número de
candidatos por nivel; score, razones y lista final de `candidate_id`.

### Consecuencias

Será posible explicar por qué se retuvo o descartó un candidato y repetir la
preselección con el mismo estado de datos.

### Dependencias

D012 y D017–D022.

## D024 — Idioma y traducción

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** LLM / preselección  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3.

### Decisión / propuesta

Conservar siempre la descripción original y su idioma. El LLM producirá
conceptos canónicos independientes del idioma. Cualquier traducción se guardará
como artefacto derivado con modelo y versión, nunca sobrescribirá el original y
se comparará experimentalmente con el uso directo del texto.

La elección del texto que recibe CrossText2Loc es un experimento distinto de la
normalización usada para consultar OSM.

### Pendiente

Comparar español original, traducción al inglés y, si el modelo elegido lo
permite, extracción multilingüe directa.

## D025 — Métricas de la preselección

**Estado:** ACEPTADA  
**Componente:** Evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 3 y aceptación expresa del responsable del TFG.

### Decisión / propuesta

Medir por muestra y de forma agregada:

- retención del candidato ground truth y retención dentro de los umbrales de
  distancia acordados;
- error oráculo antes y después de filtrar;
- tamaño del conjunto y razón de reducción;
- tasa de resultado vacío antes del fallback y tasa/tipo de fallback;
- cobertura de pistas mapeables a OSM;
- latencia, errores y aciertos de caché.

Estas son métricas adicionales del TFG para evaluar la preselección; no se
atribuyen a CrossText2Loc ni a GOTPR.

### Dependencias

D020–D024 y el futuro dataset de evaluación.

### Pendiente

Fijar los umbrales de distancia y el protocolo de agregación junto con el módulo
de evaluación.

## D026 — Independencia del proveedor y modelo LLM

**Estado:** ACEPTADA  
**Componente:** LLM  
**Fecha:** 2026-10-01  
**Origen:** Aceptación expresa al cerrar la pregunta 3.

### Decisión / propuesta

El sistema expondrá una interfaz de LLM independiente del proveedor. Toda
implementación deberá aceptar la misma entrada y producir el JSON Schema de
D017, validado antes de continuar. Ningún identificador, formato o SDK de un
proveedor formará parte del contrato de dominio.

La selección posterior se basará en compatibilidad con salida estructurada o
JSON Schema, calidad de extracción, reproducibilidad, latencia y coste. Cambiar
de modelo no deberá modificar las reglas concepto→OSM de D018.

### Consecuencias

Se podrán comparar proveedores con las mismas muestras y sustituir uno sin
reescribir el compilador geográfico. El nombre, versión, configuración y salida
original del modelo utilizado se registrarán conforme a D023.

### Dependencias

D017, D018 y D023.

### Pendiente

Elegir modelo y proveedor antes de ejecutar el componente, sin acoplar a ellos
el diseño.

## D027 — Separación entre catálogo y dataset de evaluación

**Estado:** ACEPTADA  
**Componente:** Dataset / evaluación  
**Fecha:** 2026-10-01  
**Origen:** Requisito expreso de la pregunta 4 y arquitectura ya documentada.

### Decisión / propuesta

El catálogo de referencia contendrá los candidatos sobre los que se busca y sus
artefactos. El dataset de evaluación contendrá consultas independientes,
coordenadas reales y procedencia. Una ubicación evaluada puede estar cubierta
por el catálogo, pero su descripción y su ground truth no se usarán para crear,
entrenar o ajustar los recuperadores ni para centrar la búsqueda.

### Consecuencias

El dataset de evaluación referenciará versiones del catálogo, pero no duplicará
sus imágenes, embeddings o grafos. Los fallos de cobertura o preselección
contarán en la evaluación y no se corregirán retrospectivamente.

### Dependencias

D001, D004, D006 y D012.

## D028 — Origen de las descripciones del MVP

**Estado:** ACEPTADA  
**Componente:** Dataset de evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

Usar una combinación con funciones separadas:

- descripciones manuales controladas y ejemplos sintéticos, claramente
  etiquetados, solo para smoke tests y desarrollo;
- descripciones humanas recogidas *in situ* como fuente principal del test
  final;
- datasets existentes únicamente para verificar adaptadores o reproducir sus
  protocolos, no como sustituto del test de Madrid;
- descripciones VLM solo como ablación futura, si la fuente de imágenes y sus
  permisos están resueltos.

Las personas describirán lo que observan sin ver OSM, imágenes del catálogo,
`candidate_id`, rankings ni respuestas del sistema. Las instrucciones y el
consentimiento/licencia del texto se versionarán.

### Justificación

La recogida humana es más costosa, pero mide el escenario objetivo y evita que
el generador copie directamente etiquetas OSM. Los ejemplos controlados son
útiles para depurar, pero no estiman por sí solos el rendimiento con usuarios.

### Pendiente

Preparar instrucciones y revisar requisitos éticos, de consentimiento y de
protección de datos antes de recoger observaciones. El origen metodológico está
aceptado; el tamaño y la partición siguen en D029.

## D029 — Tamaño y partición inicial del conjunto

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** Dataset de evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Propuesta inicial

Usar aproximadamente 50 localizaciones y dos descripciones independientes por
localización, es decir, unas 100 consultas:

- desarrollo: 15 localizaciones y unas 30 descripciones;
- test final: 35 localizaciones y unas 70 descripciones.

La partición será por `location_id`, nunca por descripción, para impedir que la
misma localización aparezca en desarrollo y test. La selección será previa a los
resultados y estratificada por subzona, densidad y tipos de entorno.

### Justificación

Es una escala viable para un TFG y permite más de una formulación por ubicación,
pero no garantiza por sí sola potencia estadística suficiente para diferencias
pequeñas.

### Pendiente

Validar esfuerzo de recogida, diversidad, número de participantes y precisión
de los intervalos. Informar intervalos de confianza y evitar conclusiones fuertes
si la muestra resulta pequeña.

## D030 — Ground truth geográfico y asignación a candidato

**Estado:** ACEPTADA  
**Componente:** Ground truth  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

El ground truth primario será la coordenada WGS84 de la posición desde la que se
escribió la descripción. Se conservarán método, instante, precisión reportada y
control de calidad. La coordenada no se ajustará a un objeto OSM.

Después de fijarla se derivará `ground_truth_candidate_id` mediante la versión
de la cuadrícula y el manifest: preferentemente la celda que contiene el punto,
con una regla determinista para bordes. También se almacenarán distancia al
centro, distancia al borde y cualquier ambigüedad. Un caso fuera del catálogo se
rechazará por una regla previa y documentada, nunca según el resultado del
modelo.

### Consecuencias

La coincidencia exacta de celda y el error métrico podrán evaluarse por separado.
Los casos próximos a fronteras no se ocultarán ni se convertirán manualmente en
aciertos.

### Dependencias

D001–D004, D012 y D022.

### Pendiente

Fijar método de captura, umbral de precisión admitido, número de lecturas y regla
exacta de borde antes de recoger datos.

## D031 — Métricas comunes de recuperación y localización

**Estado:** ACEPTADA  
**Componente:** Evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4 y auditoría de los evaluadores oficiales.

### Decisión / propuesta

Informar dos familias sin confundirlas:

- recuperación discreta: Recall@1, Recall@5 y Recall@10 por coincidencia del
  `ground_truth_candidate_id`;
- localización: Haversine del Top-1, media, mediana y percentiles, además del
  porcentaje y GeoRecall@K dentro de umbrales métricos.

Se reproducirán por separado, cuando sean aplicables, las métricas oficiales
observadas: CrossText2Loc usa R@1/5/10 y 50/100/150 m en el evaluador auditado;
GOTPR usa R@1/3/5 por `scene_id`. Los umbrales 25/50/100/500 m serán métricas
adicionales del TFG y su selección final permanecerá experimental.

Las muestras sin candidatos, con fallo del parser o cuyo ground truth fue
filtrado permanecerán en el denominador del resultado extremo a extremo.

### Dependencias

D025 y D030.

### Pendiente

Fijar métricas principales, umbrales finales e intervalos de confianza antes de
abrir el test.

## D032 — Comparación pareada entre baseline y propuesta

**Estado:** ACEPTADA  
**Componente:** Evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

El baseline ejecutará CrossText2Loc sobre todo el catálogo de la región. La
propuesta ejecutará el parser LLM, la preselección OSM y CrossText2Loc sobre el
subconjunto resultante. Ambos usarán exactamente las mismas consultas, catálogo,
imágenes, embeddings, checkpoint, preprocesamiento, Top-K y entorno de medida.

En el experimento principal todas las consultas recibirán la región piloto
completa. No se construirá una zona por consulta a partir del ground truth. Se
informarán métricas de preselección y de extremo a extremo, con resultados
pareados por `sample_id`.

### Consecuencias

La reducción del catálogo no se presentará aisladamente como mejora: deberá
mantener una retención suficiente y mejorar o conservar el resultado final.

### Dependencias

D004, D017–D025 y D027.

## D033 — Prevención de leakage y congelación del test

**Estado:** ACEPTADA  
**Componente:** Dataset de evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

El conjunto de desarrollo podrá usarse para prompts, vocabulario, radios,
thresholds y reglas. Antes de ejecutar el test se congelarán código,
configuración, esquema, vocabulario, catálogo, snapshot OSM y checkpoints. El
texto y los resultados del test no se usarán para ajustes posteriores sin crear
una nueva versión de evaluación.

Se dividirá por localización y se registrará si una descripción es humana,
manual, sintética, VLM o adaptada. Ninguna descripción de evaluación se usará
para entrenamiento o fine-tuning.

### Dependencias

D027–D032.

## D034 — Schema versionado del ejemplo de evaluación

**Estado:** ACEPTADA  
**Componente:** Dataset de evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

Cada ejemplo tendrá identidad y split; texto, idioma, fuente e instrucciones;
zona declarada; ground truth geográfico y asignación al catálogo; procedencia,
licencia/consentimiento y flags de leakage; y versiones del protocolo, catálogo
y snapshot OSM. Los artefactos derivados del LLM o de los recuperadores se
guardarán como resultados de ejecución, no como parte inmutable del ground
truth.

### Dependencias

D012, D023, D027, D030 y D033.

## D035 — Plan de ablaciones

**Estado:** ACEPTADA  
**Componente:** Evaluación  
**Fecha:** 2026-10-01  
**Origen:** Pregunta 4.

### Decisión / propuesta

El experimento mínimo comparará CrossText2Loc con y sin preselección. Las
extensiones se incorporarán como ablaciones independientes: OSM frente a
satélite, CrossText2Loc frente a GOTPR, con/sin VLM y con/sin diálogo. Cada una
mantendrá constantes las consultas, la cobertura candidata y los componentes no
ablacionados, y documentará cuándo esa igualdad no sea posible.

### Dependencias

D008–D011, D014–D015 y D032.

### Pendiente

GOTPR depende de D011; satélite de D009 y D015; VLM de permisos y cobertura de
imágenes; diálogo de una política y presupuesto de turnos todavía no fijados.

## D036 — GeoBridge como extensión opcional

**Estado:** ACEPTADA  
**Componente:** Alcance / GeoBridge  
**Fecha:** 2026-10-02  
**Origen:** instrucción expresa de incorporar GeoBridge al análisis al mismo
nivel conceptual que GOTPR, VLM, DialogueVPR y TOLoc, sin añadirlo al MVP.

### Decisión / propuesta

GeoBridge se documenta y puede evaluarse en una fase posterior, pero no es una
dependencia, entregable ni criterio de finalización del MVP. Su auditoría no
altera el orden vigente de Fases 0–7 ni desbloquea la adquisición de imágenes.

### Consecuencias

No se integra en `src/`, no se modifica el manifest actual y no se descargan
pesos o datos hasta una aprobación específica. Si se utiliza, se evaluará como
ablación independiente de acuerdo con D035.

### Evidencia

[DATASET_MODEL_REQUIREMENTS.md](DATASET_MODEL_REQUIREMENTS.md#7-geobridge-como-extensión-opcional) documenta el repositorio oficial en el
commit `636c413c58615669bb8b95c3eecedf161d3e523f`.

## D037 — Posición inicial de GeoBridge en la arquitectura

**Estado:** PROPUESTA  
**Componente:** GeoBridge  
**Fecha:** 2026-10-02  
**Origen:** auditoría técnica de GeoBridge.

### Decisión / propuesta

Si D038 se resuelve, estudiar primero GeoBridge después de la preselección como:

1. retriever visual alternativo sobre imágenes asociadas a los candidatos; o
2. reranker de un Top-N producido por otro recuperador.

La fusión de scores o embeddings con CrossText2Loc, GOTPR o un VLM sería una
metodología propia posterior y no forma parte de esta propuesta inicial.

### Justificación

El modelo publicado soporta texto→imagen mediante un espacio común. Restringir
la galería a `candidate_id` preseleccionados conserva esa operación. En cambio,
la fusión de recuperadores no está definida por GeoBridge y exige calibración y
ablaciones propias.

### Pendiente

Aprobación del responsable del TFG, D038 y D039. Elegir calle, satélite, *drone*
o más de una modalidad no queda decidido.

## D038 — Licencias y permisos de GeoBridge

**Estado:** PENDIENTE DE LICENCIA  
**Componente:** GeoBridge / licencias  
**Fecha:** 2026-10-02  
**Origen:** auditoría del repositorio, Hugging Face y términos de proveedores.

### Contexto

El repositorio no incluye licencia. Los metadatos del modelo y dataset en
Hugging Face tampoco declaran licencia. El artículo anuncia CC BY-NC-SA 4.0 para
GeoLoc, pero el release no contiene una card que delimite los archivos cubiertos
y las imágenes de Google conservan condiciones independientes.

### Decisión / propuesta

No integrar, modificar o redistribuir el código ni descargar/usar el checkpoint
como componente del TFG hasta recibir una licencia o autorización aplicable. No
generar galerías ni embeddings desde Google Street View/Maps mientras el
proveedor no confirme que el flujo concreto está permitido; para una cuenta EEE
los términos vigentes prohíben asumir caché, creación de contenido derivado o
uso para probar/validar modelos.

### Dependencias

D015 y cualquier decisión futura sobre Street View/VLM. No bloquea el MVP.

### Pendiente

Respuesta de los autores sobre código, pesos y archivos GeoLoc; respuesta del
proveedor o elección de una fuente visual alternativa con licencia compatible.

## D039 — Transferencia zero-shot y galería de Madrid para GeoBridge

**Estado:** PENDIENTE DE EXPERIMENTO  
**Componente:** GeoBridge  
**Fecha:** 2026-10-02  
**Origen:** auditoría técnica de GeoBridge.

### Contexto

El código puede codificar nuevas imágenes y textos, pero las fuentes públicas no
demuestran rendimiento en Madrid ni fijan un único footprint para una galería
nueva. GeoLoc contiene footprints de 80–180 m y descripciones controladas, no el
protocolo humano del TFG.

### Decisión / propuesta

Antes de considerar viable la extensión, ejecutar una fixture legalmente
obtenida y luego una ablación pequeña que compare modalidades, footprint,
orientación, idioma y política de imágenes por candidato. No realizar
fine-tuning dentro del alcance actual.

### Pendiente

Resolver D038, reproducir de forma controlada la carga del checkpoint y fijar
las variables experimentales sin convertir los valores de GeoLoc en requisitos
del catálogo principal.

## D040 — Monorepo propio del TFG

**Estado:** ACEPTADA  
**Componente:** Repositorio  
**Fecha:** 2026-10-02  
**Origen:** Petición expresa de preparar un único repositorio GitHub principal.

Se mantiene la estructura útil existente: `BASELINE.md` en raíz, `docs/`,
`config/`, `schemas/`, `src/tfg_phase0/`, `tests/`, `frontend/` y
`latex-memory/`. No se mueven documentos ni se crean directorios vacíos de
aplicación o ML. `data/`, `checkpoints/` y `results/` tienen documentación
rastreable, mientras sus artefactos voluminosos quedan fuera de Git. Los
manifests y resultados pequeños se podrán versionar tras inspeccionar su
contenido y permisos.

Esta decisión organiza el trabajo; no afirma que se hayan ejecutado modelos
ni que exista ya un backend.

## D041 — Procedencia y obtención de CVG-Text

**Estado:** ACEPTADA  
**Componente:** Dependencias externas  
**Fecha:** 2026-10-02  
**Origen:** Petición expresa de reutilizar el repositorio oficial sin copiar
código de terceros cuando su redistribución no esté aclarada.

`external/` se ignora íntegramente. El script propio
[`scripts/setup_external.sh`](../scripts/setup_external.sh) clona
<https://github.com/yejy53/CVG-Text.git> y fija
`6910d2747a94fbe985309bde60cd4732bcbbf50f`; si ya existe un clon,
verifica origen, limpieza y commit sin modificarlo. No se usa submódulo ni se
redistribuye una copia del código oficial dentro de este monorepo. El código
pertenece a los autores de CVG-Text.

La ausencia de una licencia inequívoca para el código y los pesos sigue
pendiente en D016. Este método de obtención no concede permisos de ejecución,
adaptación ni redistribución que no se hayan confirmado.

## D042 — Alcance del próximo experimento CrossText2Loc

**Estado:** ACEPTADA  
**Componente:** CrossText2Loc  
**Fecha:** 2026-10-02  
**Origen:** Petición expresa de preparar reproducción de Nueva York con pesos
preentrenados congelados antes de estudiar Madrid.

El primer experimento planificado es texto NewYork-mixed contra candidatos OSM
de Nueva York, utilizando el checkpoint OSM publicado por los autores y solo
inferencia. No se entrena, ajusta ni cambia la arquitectura. La selección
definitiva del peso para transferencia a Madrid sigue pendiente de D013 y el
perfil OSM de una galería nueva sigue pendiente de D007. La evaluación oficial
utiliza 100 vecinos centrados con el ground truth; en Madrid no se usará la
coordenada real para construir la galería de búsqueda.

## D043 — Fuente primaria y uso offline del snapshot OSM piloto

**Estado:** ACEPTADA
**Componente:** OSM / adquisición
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para la Fase 2.

### Contexto

La bbox D004 es pequeña y necesita una adquisición vectorial controlada. D019
ya exige que el catálogo y la preselección ordinaria trabajen contra un snapshot
OSM local y versionado, evitando depender del estado cambiante de un servicio
remoto durante cada consulta.

### Decisión / propuesta

Usar Overpass como fuente primaria para una adquisición controlada del piloto
D004. Overpass se utilizará para obtener el snapshot, no como dependencia
obligatoria en tiempo de consulta. Después de adquirirlo, las etapas ordinarias
del pipeline trabajarán sobre la copia local identificada.

La adquisición no utilizará ground truth, descripciones de evaluación ni
resultados de modelos. Su ámbito será exclusivamente la bbox configurada del
piloto.

### Justificación

La extensión reducida del piloto permite una consulta acotada y facilita
conservar exactamente la respuesta usada. Separar adquisición y consulta evita
que cambios de OSM, límites de servicio o fallos de red alteren un experimento.

### Consecuencias

La implementación deberá permitir cache hit sin red y registrar el endpoint y
la consulta exacta. Geofabrik permanece como alternativa futura si se necesita
un extracto regional fechado o una reconstrucción histórica más fuerte.

### Dependencias

D004, D012 y D019.

### Pendiente

Ninguno sobre la fuente primaria y el uso offline. Los parámetros operativos se
fijan en D048.

## D044 — Formato y ciclo de vida del snapshot OSM raw

**Estado:** ACEPTADA
**Componente:** OSM / datos raw
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para la Fase 2.

### Contexto

El raw debe conservar la semántica propia de OSM antes de aplicar decisiones de
normalización, extracción de geometrías o vocabulario semántico.

### Decisión / propuesta

Conservar la respuesta primaria en OSM XML (`.osm`). La adquisición inicial
preservará los objetos, miembros y tags necesarios para reconstruir nodes, ways
y relations sin introducir filtrado semántico prematuro. Los filtros de
conceptos y atributos pertenecen al procesamiento posterior, no al raw.

Cada snapshot será inmutable. Nunca se sobrescribirá uno existente: una nueva
adquisición o estado de OSM producirá otro snapshot identificable. El fichero
raw no se normalizará ni modificará in place.

### Justificación

OSM XML conserva IDs, versiones, timestamps, tags, members y estructura de los
objetos. La inmutabilidad permite verificar resultados y regenerar derivados
sin depender de una nueva descarga.

### Consecuencias

Las respuestas procesadas, recortes normalizados o índices no se tratarán como
raw. El tratamiento exacto de elementos que atraviesan la bbox deberá quedar
expresado por la consulta D048 y validarse con fixtures.

### Alternativas consideradas

- JSON de Overpass como raw canónico.
- GeoJSON como único artefacto de entrada.
- Sobrescribir un fichero fijo en cada actualización.

JSON puede reconsiderarse si aporta una ventaja comprobable; GeoJSON se
descarta como único raw porque ya implica transformación y puede perder
semántica OSM. La sobrescritura se descarta por falta de trazabilidad.

### Dependencias

D004 y D043.

## D045 — Integridad y provenance del snapshot OSM

**Estado:** ACEPTADA
**Componente:** OSM / provenance
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para la Fase 2.

### Contexto

Una fecha o un nombre de archivo no bastan para demostrar qué respuesta se usó
ni para detectar descargas truncadas o cambios de contenido.

### Decisión / propuesta

Registrar para cada snapshot, como mínimo:

- fuente y endpoint;
- fecha y hora UTC de adquisición;
- bbox y consulta exactas;
- formato raw;
- tamaño en bytes y SHA-256;
- versión del mecanismo o código de adquisición;
- conteos de nodes, ways y relations;
- licencia y atribución ODbL;
- resultado de la adquisición y metadatos necesarios para repetirla.

El identificador y los metadatos no incluirán secretos. El hash se calculará
sobre el raw exacto persistido después de una escritura atómica y validación
estructural.

### Justificación

El hash identifica el contenido realmente utilizado; la consulta y el endpoint
explican cómo se obtuvo; los conteos ayudan a detectar respuestas vacías o
incompletas.

### Consecuencias

La provenance pequeña podrá revisarse para versionado, pero su presencia no
autoriza por sí sola la redistribución del raw. El formato del
`osm_snapshot_id` se fija en D048.

### Dependencias

D012, D019, D043 y D044.

## D046 — Separación de artefactos OSM y política de Git

**Estado:** ACEPTADA
**Componente:** OSM / almacenamiento
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para la Fase 2.

### Decisión / propuesta

Mantener físicamente separados:

```text
raw OSM
→ derivados OSM
→ imágenes OSM
→ embeddings
→ índices
```

El raw será inmutable y los derivados regenerables conservarán la referencia y
hash de su snapshot de origen. Los datos raw voluminosos no se versionarán en
Git. La metadata o provenance pequeña solo se versionará después de revisar su
contenido, licencia y ausencia de datos privados o secretos.

### Justificación

La separación evita confundir datos adquiridos con transformaciones propias,
permite invalidar derivados cuando cambia el snapshot y reduce el riesgo de
incorporar datos externos o resultados voluminosos al repositorio.

### Consecuencias

Fase 2 solo podrá crear raw y metadata de adquisición. Las imágenes,
representaciones e índices pertenecen a fases posteriores.

### Dependencias

D006, D012, D019, D040, D043, D044 y D045.

## D047 — Relación del snapshot con el catálogo y límites de Fase 2

**Estado:** ACEPTADA
**Componente:** OSM / alcance Fase 2
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para la Fase 2.

### Decisión / propuesta

El catálogo, sus derivados y la futura preselección deberán poder referenciar
inequívocamente el `osm_snapshot_id` utilizado. La adquisición y construcción
del snapshot no usarán ground truth.

Fase 2 no generará imágenes OSM, tiles, embeddings, índices, vocabularios de
preselección ni consultas de usuario. El índice geoespacial y la preselección se
posponen. D007 permanece pendiente y no se considera resuelta por adquirir datos
vectoriales OSM.

### Justificación

Un snapshot vectorial no determina el footprint, estilo, zoom o
preprocesamiento visual requerido por CrossText2Loc. Separar estas etapas evita
atribuir a Fase 2 decisiones metodológicas todavía abiertas.

### Consecuencias

`osm_snapshot_id` permanecerá `null` en manifests que no se hayan vinculado a
una adquisición concreta. Una vinculación futura deberá comprobar el ID y hash,
no inferirlos por ruta o fecha.

### Dependencias

D007, D012, D019, D027, D032 y D046.

## D048 — Parámetros operativos de adquisición OSM

**Estado:** ACEPTADA
**Componente:** OSM / operación
**Fecha:** 2026-10-06
**Origen:** aprobación expresa del responsable del TFG para cerrar el diseño de
Fase 2 antes de implementar o adquirir datos.

### Contexto

Las decisiones de fuente, formato, inmutabilidad y provenance están aceptadas.
Falta fijar de forma canónica la operación exacta para que endpoint, consulta,
bordes, identidad, reintentos y validación no queden implícitos en código.

### Decisión / propuesta

Usar por defecto el endpoint configurable:

```text
https://overpass-api.de/api/interpreter
```

El endpoint real se configurará y registrará en provenance, pero no formará
parte de la identidad del snapshot: dos endpoints que devuelvan exactamente los
mismos bytes producirán el mismo identificador.

La primera consulta aprobada fue:

```overpass
[out:xml][timeout:60];
(
  node(40.4120,-3.7090,40.4200,-3.6990);
  way(40.4120,-3.7090,40.4200,-3.6990);
  relation(40.4120,-3.7090,40.4200,-3.6990);
)->.seed;
(
  .seed;
  .seed >>;
);
out meta qt;
```

Su SHA-256 era
`bb2c5f7beb208f9a898bede9f4eb890df12a4c490ffd000ccd527eb42f4d25e2`.

Era semánticamente válida: `>>` calcula la clausura descendente transitiva y
reflexiva, incluyendo subrelations y todos sus miembros. Sin embargo, una
relation seleccionada por tocar D004 podía extender el resultado muy lejos del
piloto. El primer intento real terminó en HTTP 429 y el segundo en HTTP 504,
aunque el preflight del segundo anunciaba slots disponibles. Esto no demuestra
que `>>` causara el 504, pero la expansión de relations grandes es un factor
técnicamente plausible documentado por Overpass. Ningún intento produjo un
snapshot válido. Por ello esta consulta queda **SUSTITUIDA antes del primer
snapshot real**.

La consulta canónica corregida es:

```overpass
[out:xml][timeout:60];
(
  node(40.4120,-3.7090,40.4200,-3.6990);
  way(40.4120,-3.7090,40.4200,-3.6990);
)->.local;
(
  .local;
  node(w.local);
  rel(bn.local);
  rel(bw.local);
);
out meta qt;
```

El SHA-256 de los bytes UTF-8 exactos de la consulta corregida, incluido el
salto de línea final, es
`11b8fe8f8b781c2fbceb1e24def956321ff141ffe1e5b09ffa14d0ff4df36145`.

`.local` contiene nodes seleccionados por bbox y ways cuya geometría intersecta
D004 según Overpass. `node(w.local)` completa todos los `nd ref` de esos ways,
incluidos nodes exteriores. `rel(bn.local)` y `rel(bw.local)` añaden relations
que referencian directamente nodes o ways locales, pero no expanden sus members
ni siguen subrelations. `out meta qt` conserva tags, referencias, roles y
metadata OSM.

La provenance declarará:

```text
selection.nodes = bbox
selection.ways = bbox_intersection
selection.relations = direct_parent_of_local_node_or_way
closure.ways = all_referenced_nodes
closure.relations = not_expanded
```

Todos los `nd ref` de ways deberán resolverse. Los members de relations deberán
tener tipo, ref y role sintácticamente válidos; si el objeto referenciado no
está presente, no invalidará el snapshot y se contabilizará por tipo en
`unresolved_relation_members`. Una relation devuelta es contexto OSM relacionado
con D004, no una promesa de clausura completa.

Los conteos derivados distinguirán `selected_objects.node_bbox`,
`selected_objects.way_bbox_intersection` y
`selected_objects.relation_context`, además de `added_way_nodes`. No se
atribuirá a una relation contextual la condición de objeto local.

Fijar `[timeout:60]` como timeout del servidor Overpass. El cliente tendrá
timeout de conexión de 10 segundos y timeout HTTP total de 120 segundos. Se
permitirán como máximo dos reintentos después del intento inicial, es decir,
tres intentos totales. Solo se reintentará ante timeout, fallo de conexión, HTTP
429, 502, 503 o 504. El backoff será 5 segundos antes del segundo intento y 15
segundos antes del tercero; si existe `Retry-After` válido, se respetará con un
máximo de 60 segundos. No se reintentará un error sintáctico o HTTP 4xx distinto
de 429.

El identificador será content-addressed:

```text
osm-madrid-pilot-osmxml-sha256-<SHA256_RAW_COMPLETO>
```

Participan en la identidad el nombre estable de la región, el formato raw y el
SHA-256 completo de `source.osm`. Fecha UTC, endpoint, consulta, hash de la
consulta, versión del adquirente, respuesta HTTP y número de intento son metadata
de adquisición, no identidad. Dos adquisiciones byte a byte idénticas tendrán el
mismo ID aunque cambien la hora o el endpoint; cualquier diferencia de bytes
producirá otro ID.

La publicación seguirá este procedimiento en el mismo filesystem:

1. crear un directorio temporal único y abrir `source.osm.part` sin sobrescribir;
2. descargar en streaming, limitar tamaño y sincronizar el fichero;
3. validar XML y estructura; rechazar respuestas de error o incompletas;
4. calcular tamaño y SHA-256 sobre el raw exacto;
5. construir y validar `provenance.json` en el directorio temporal;
6. sincronizar ficheros y directorio;
7. publicar el directorio temporal mediante una operación atómica
   **no-replace** al directorio final cuyo nombre es `osm_snapshot_id`.

Un fallo de red, interrupción o validación dejará como máximo un temporal que no
se tratará como snapshot y podrá limpiarse de forma explícita en otra ejecución.
La implementación deberá usar una primitiva no-replace o un lock exclusivo con
recomprobación para impedir sustituciones y carreras entre procesos. Si el
destino final ya existe y su raw tiene el SHA-256 esperado, se considera cache
hit y no se sobrescribe. Si el directorio existe pero falta un artefacto, no
valida o su hash difiere del ID, se clasifica como conflicto/corrupción y se
detiene sin reparar ni sobrescribir automáticamente.

Antes de aceptar `source.osm` se comprobará:

- tamaño mayor que cero y dentro del límite configurado;
- XML bien formado, sin entidades externas, con raíz `osm` y versión compatible;
- ausencia de elementos `remark` o respuestas HTML/error de Overpass;
- IDs enteros positivos y no duplicados por tipo;
- latitud/longitud válidas en nodes;
- conteos no vacíos de node, way y relation registrados en provenance;
- cada `nd ref` de way resuelto por un node presente;
- cada member de relation con tipo, referencia positiva y role válidos;
- todos los `nd ref` de ways resueltos; los members ausentes de relations
  contextuales se contabilizan sin exigir clausura de relations.

Estas comprobaciones distinguen validación sintáctica, estructura interna y
completitud respecto a la consulta. No garantizan que una ejecución futura de la
misma consulta devuelva el mismo estado OSM, ni aplican semántica CrossText2Loc.

### Reproducibilidad

El artefacto congelado es reproducible byte a byte mediante su raw y SHA-256, y
los experimentos posteriores pueden referenciar exactamente su
`osm_snapshot_id`. La adquisición online solo es repetible como procedimiento:
la misma consulta en otra fecha puede devolver contenido distinto y, por tanto,
otro ID. Conservar raw, consulta, endpoint, UTC, versión del adquirente y
provenance permite auditar ambas dimensiones sin confundirlas.

### Justificación

Estos parámetros limitan la carga sobre el servicio, evitan snapshots ambiguos
y permiten detectar truncamiento, referencias ausentes y conflictos de caché.
Separar identidad de contenido y metadata temporal evita duplicar identidades
por descargas idénticas.

### Pendiente

Ninguno sobre estos parámetros. La primera adquisición real autorizada validó
D048 el `2026-10-06T08:52:43.930134Z`, en un intento HTTP 200, y produjo
`osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141`.
Este hecho operacional no crea una nueva decisión. Cualquier adquisición futura
requiere otra autorización y deberá respetar la política vigente del endpoint.

## D049 — Política versionada de interpretación geométrica de OSM ways

**Estado:** ACEPTADA

**Componente:** OSM / catálogo geométrico F3

**Fecha:** 2026-10-06

**Origen:** Auditoría de `osm-polygon-features` y aprobación expresa del
responsable del TFG.

### Contexto

D022 exige asociar los objetos OSM mediante su geometría real, pero un way cuyo
primer y último node coinciden no representa necesariamente un área. Puede ser
un Polygon, una línea cerrada o un caso ambiguo. F2 conserva todos los `nd ref`
de los ways, mientras que sus relations son contexto no expandido.

### Decisión

F3 aplicará la política determinista `way_is_area-v1`. La fuente de reglas será
una copia exacta e inmutable de:

```text
repository: https://github.com/tyrasd/osm-polygon-features
release: v0.9.2
commit: 069a46416629ddbe84390c7a3ccc600fe73ee706
file: polygon-features.json
size: 2753 bytes
sha256: cf81018ba820557c59c2c27de7ea6b314009abed040cd11249e94ed1a3a10583
license: CC0-1.0
```

La copia se conservará sin modificar junto con su licencia. F3 verificará su
SHA-256 y la consumirá offline, sin descargar reglas ni consultar servicios
externos durante la ejecución.

La clasificación seguirá estas reglas:

1. Validar las referencias y la estructura del way.
2. `area=no` produce `line`.
3. `area=yes` declara intención areal; en un way abierto produce
   `invalid_area` y en un closed way exige construir y validar un Polygon.
4. Un way abierto sin `area=yes` produce `line`.
5. Un closed way sin `area=*` se evalúa contra la tabla fijada.
6. `polygon=all` produce voto `area` para un valor distinto de `no`.
7. `polygon=whitelist` produce voto `area` para un valor incluido y voto
   `line` para un valor no incluido y distinto de `no`.
8. `polygon=blacklist` produce voto `line` para un valor excluido y voto
   `area` para el resto de valores distintos de `no`.
9. Una clave no incluida en la tabla no produce voto.
10. Solo votos `area` producen intención areal; solo votos `line` producen
    `line`; la ausencia de votos produce `unknown_closed_way`.
11. La coexistencia de votos `area` y `line` produce `unknown_closed_way` con
    conflicto explícito. El orden de los tags nunca resuelve conflictos.

Toda intención areal requiere un Polygon cerrado, válido, no vacío y con área
positiva. Si falla alguna condición, el resultado será `invalid_area`. F3 v1 no
aplicará `buffer(0)`, `make_valid`, simplificación ni fallback automático.
`unknown_closed_way` e `invalid_area` no producirán asociaciones geométricas
base.

F3 no construirá geometrías de las relations parciales de F2 ni heredará sus
tags o semántica a los member ways. Un member sin tags continuará siendo
`unknown_closed_way`, aunque su role sea `outer` o `inner`.

### Limitación metodológica

`osm-polygon-features` v0.9.2 es una heurística comunitaria histórica congelada,
no una norma oficial de OpenStreetMap, una definición universal de áreas ni una
representación necesariamente actual de toda su semántica. La release es de
2016, su mantenimiento actual es limitado, la tabla es incompleta y algunas
reglas, como `barrier=wall`, fueron cuestionadas posteriormente en upstream.

La resolución conservadora de conflictos es una adaptación propia del TFG. No
se corregirá silenciosamente la tabla upstream. Una versión futura de la tabla
o de la política podrá producir clasificaciones y asociaciones distintas y
exigirá otra versión del derivado.

### Justificación

La política evita equiparar cierre topológico con semántica areal, conserva la
trazabilidad hasta una fuente pública fijada y permite regenerar el derivado sin
red. Tratar la ausencia y los conflictos como desconocidos evita convertir una
tabla incompleta en una clasificación exhaustiva.

### Consecuencias

La implementación deberá conservar el resultado y la razón de clasificación,
validar la geometría con la dependencia geométrica que se adopte y registrar en
provenance la versión `way_is_area-v1`, el commit y el hash de la tabla. Cambiar
la fuente o cualquiera de estas reglas invalida el derivado previo.

### Dependencias

D002, D018, D019, D022 y D043-D048.

### Pendiente

Ninguno sobre la política `way_is_area-v1`. El contrato global de F3 se
estudiará por separado antes de implementarlo, sin asignarle todavía una nueva
decisión.

## D050 — Contrato del dataset de asociaciones geométricas F3

**Estado:** ACEPTADA

**Componente:** OSM / catálogo geométrico F3

**Fecha:** 2026-10-07

**Origen:** Diseño del contrato global de Fase 3 y aprobación expresa del
responsable del TFG.

### Contexto

F1 produce un manifest geométrico materializado de `candidate_id` y F2 un
snapshot OSM local, inmutable y validado. D022 fija la correspondencia
geométrica métrica y D049 la interpretación de los OSM ways. Falta definir el
dataset derivado que vinculará ambos inputs sin modificarlos ni incorporar
preselección semántica.

### Decisión

F3 será un dataset derivado, reproducible e inmutable. Consumirá un manifest F1
ya materializado y exclusivamente un snapshot F2 local validado. Comprobará sus
schemas, identidades, hashes, regiones, bbox, CRS, conteos y políticas de
clausura. No regenerará ni modificará F1, no adquirirá ni modificará F2 y no
utilizará red.

La identidad OSM será `(osm_type, osm_id)` y `osm_ref` se derivará como
`<osm_type>/<osm_id>`. Los nodes `node_bbox` serán Point asociables. Los
`added_way_node` se conservarán para reconstrucción y trazabilidad, pero no
producirán asociaciones Point directas.

Los ways usarán su geometría completa y D049/`way_is_area-v1`: `line` se
representará como LineString y `area` como Polygon. `unknown_closed_way`,
`invalid_area` e `invalid_way_geometry` no producirán asociaciones. No se usarán
centroides ni reparaciones automáticas.

Las celdas se reconstruirán en EPSG:25830 desde `center_easting_m`,
`center_northing_m` y `cell_size_m` de F1. Las coordenadas OSM se proyectarán
mediante la misma transformación usada por F1. Predicados y distancias se
calcularán en EPSG:25830.

La asociación base será muchos-a-muchos y existirá si
`osm_geometry.intersects(candidate_cell)` es verdadero. No habrá nearest-only,
ganador, desempate, buffer, radio, scoring ni semántica de consulta. La dirección
formal de los predicados será `osm_geometry <predicate> candidate_cell`. Cada
asociación registrará `intersects`, `contains`, `within`, `crosses`, `touches`,
`overlaps`, `boundary_contact_only` y `center_distance_m`. En F3 v1,
`boundary_contact_only == touches`; la distancia se medirá desde el centro F1
hasta la geometría OSM completa.

Las relations no recibirán geometría, no se reconstruirán como multipolygons,
no se completarán con red y no transmitirán tags o semántica a sus members. El
contexto se propagará un solo nivel desde members presentes directamente
asociados. `relation_context.jsonl` solo contendrá relations con al menos uno de
esos members; las restantes se contabilizarán en provenance.

El dataset canónico será:

```text
data/processed/osm/<osm_snapshot_id>/<f3_dataset_id>/
  osm_objects.jsonl
  candidate_osm_associations.jsonl
  relation_context.jsonl
  provenance.json
  sha256.txt
```

No se enriquecerá el manifest F1. SQLite y los índices persistentes solo podrán
ser derivados regenerables, no fuentes canónicas.

Shapely 2.x y GEOS serán la única capa geométrica nueva y STRtree el índice
espacial temporal. El índice solo acelerará la búsqueda: sus resultados se
deduplicarán y ordenarán por identidad OSM antes de evaluar predicados y nunca
determinarán el orden del output. Antes de implementar geometría se realizará un
preflight para Python 3.12/Linux `aarch64` y se fijarán versiones exactas de
Shapely y GEOS.

Los JSONL usarán UTF-8 sin BOM, claves ordenadas, formato compacto,
`allow_nan=false`, orden de filas explícito y newline final. Las magnitudes
métricas se redondearán a seis decimales y `-0.0` se normalizará a `0.0`. El
bundle canónico no incluirá un timestamp de ejecución variable.

`f3_dataset_id` será content-addressed a partir del manifest F1 exacto, su
`manifest_id`, el snapshot ID y hash F2, la configuración canónica, D049 y el
hash de sus reglas, el CRS y la transformación, las políticas geométricas, el
código generador relevante, las versiones exactas de Python, Shapely y GEOS y
la versión de serialización. No participarán rutas absolutas, hostname, usuario,
timestamp, duración, orden de STRtree, número de cores, `platform_system` ni
`platform_machine`. Los dos últimos se registrarán únicamente en
`provenance.software`.

El contrato exige determinismo para una identidad algorítmica fijada, pero no
promete igualdad byte a byte universal entre plataformas. Cualquier divergencia
con los mismos inputs, reglas y software deberá ser visible en los hashes de
outputs y la provenance e investigarse como cuestión de reproducibilidad.

La generación usará un directorio temporal, validará outputs y hashes y
publicará de forma atómica sin sobrescribir. Un ID existente y válido será cache
hit; un ID existente incompleto o inconsistente producirá un error.

### Fuera de alcance

F3 no generará candidatos, consultará Overpass, interpretará lenguaje natural,
aplicará vocabularios de consulta, radios, buffers, fallback, scoring o
restricciones hard/soft. Tampoco usará ground truth, generará imágenes,
embeddings o scene graphs ni ejecutará CrossText2Loc o GOTPR.

### Justificación

El contrato separa los datos fuente de un derivado regenerable, materializa
D022 y D049 sin introducir semántica de consulta y permite auditar exactamente
qué inputs, reglas y software produjeron cada asociación. Excluir la plataforma
física de la identidad evita fragmentarla sin ocultar posibles diferencias,
porque sistema y arquitectura permanecen registrados en provenance.

### Consecuencias

Cada combinación de manifest, snapshot, reglas y software algorítmico producirá
un dataset identificable. Los manifests de 25 m y 50 m podrán generar datasets
F3 separados sin resolver D003. Los parámetros de D021 permanecerán fuera de
F3. La publicación de los derivados deberá revisarse conforme a ODbL.

### Dependencias

D001-D005, D012, D019, D022 y D043-D049.

### Pendiente

Fijar mediante preflight la versión exacta de Shapely y GEOS compatible con
Python 3.12/Linux `aarch64` antes de implementar la geometría. D003 y D021
continúan pendientes de experimento.

## D051 — Limitar la provenance de cada artefacto a sus inputs efectivos

**Estado:** ACEPTADA

**Componente:** Provenance / catálogo F1

**Fecha:** 2026-10-07

**Origen:** Auditoría histórica de los manifests F1 y aprobación expresa del
responsable del TFG.

### Contexto

F1 registraba `sha256_json(config)` sobre todo `config/madrid.yaml` como
`provenance.input_hashes.region_config`. Cuando F2 añadió posteriormente el
bloque `osm_acquisition` al mismo fichero, cambió el hash completo de los
manifests F1 sin cambiar la cuadrícula, sus candidatos, IDs, coordenadas ni
geometrías.

La reproducción del commit histórico
`a526a585ae35736248bb90ac8eaa6e671e61589c` confirmó que los hashes publicados
de 25 m y 50 m son correctos para la política de provenance v1. La comparación
estructural encontró una única diferencia con los manifests actuales:
`provenance.input_hashes.region_config`. No existió una regresión geométrica.

### Decisión

Cada artefacto identificará criptográficamente todos los inputs que puedan
modificar su contenido o interpretación y excluirá configuración perteneciente
a fases independientes que no influya en ese artefacto.

Como primera aplicación, F1 sustituye `provenance.input_hashes.region_config`
por `provenance.input_hashes.f1_config`. Este valor es el SHA-256 del JSON
canónico compuesto exactamente por:

```text
schema_version
region.name
region.bbox.north
region.bbox.south
region.bbox.east
region.bbox.west
region.crs
catalog.projected_crs
catalog.catalog_version
catalog.candidate_id_prefix
catalog.candidate_generation
catalog.border_policy
```

No participan `osm_acquisition`, `artifacts`,
`catalog.candidate_spacing_m` ni `catalog.cell_size_m`. Los valores efectivos de
spacing y tamaño siguen registrados en `generation` y cubiertos por
`provenance.parameters_hash`.

La versión de construcción y provenance del manifest pasa a
`provenance.code_version = phase1-manifest-v2`. La versión del algoritmo
geométrico permanece `generation.generator_version = phase1-grid-v1`.

Los nuevos manifests destinados a F3 deberán declarar exclusivamente
`input_hashes.f1_config` y `phase1-manifest-v2`; no habrá fallback silencioso a
la política v1.

### Alternativas consideradas

- Mantener el hash de la configuración completa, descartado por acoplar F1 a
  cambios de F2, F3 o modelos.
- Registrar hashes separados de región, catálogo y argumentos, descartado por
  duplicar información ya cubierta por `parameters_hash` y complicar el
  contrato sin cambiar su capacidad de detección.

### Consecuencias

No cambian `schema_version`, `catalog_version`, `manifest_id`, `grid_hash`,
`candidate_id`, `parameters_hash`, geometría, orden ni serialización general.
Los hashes completos de los nuevos manifests sí cambian porque cambia su
provenance. Los manifests históricos y sus hashes siguen siendo resultados
válidos y reproducibles de F1 v1, pero no serán inputs del primer F3 real.

Los futuros campos de configuración que afecten a F1 deberán incorporarse de
forma explícita al subconjunto canónico. Los campos de otras fases no lo
invalidarán.

### Evidencia

- Commit histórico: `a526a585ae35736248bb90ac8eaa6e671e61589c`.
- El commit F2 `6a17a81b754b5aaf0e134699ab55a964537a08d0`
  añadió `osm_acquisition` sin modificar los parámetros geométricos F1.
- La reproducción histórica produjo los hashes documentados y la comparación
  mostró candidatos y geometrías idénticos.

### Dependencias

D001-D004, D012 y D050.

### Pendiente

Ninguno sobre la política. D003 continúa pendiente de experimento y se aplicará
mediante manifests separados de 25 m y 50 m.

## D052 — Serialización, identidad y publicación canónica de F3

**Estado:** ACEPTADA

**Componente:** OSM / serialización y publicación F3

**Fecha:** 2026-10-14

**Origen:** Revisión de diseño previa a F3.6 y aprobación expresa del
responsable del TFG.

### Contexto

D050 fija el contenido lógico, los outputs y el carácter reproducible e
inmutable de F3. D051 exige que cada artefacto identifique todos y solo sus
inputs efectivos. Faltaba cerrar el preimage exacto de `f3_dataset_id`, los
hashes de código y configuración, la representación numérica, el JSONL vacío y
la publicación sin reemplazo.

### Decisión

El digest de `f3_dataset_id` será SHA-256 de los bytes UTF-8, sin newline, del
JSON canónico (`ensure_ascii=false`, claves ordenadas, separadores `,` y `:`,
`allow_nan=false`) del siguiente objeto anidado exacto:

```json
{
  "contract_version": "f3-associations-v1",
  "generator_version": "phase3-geometric-associations-v1",
  "catalog": {"manifest_sha256": "<sha256>", "manifest_id": "<id>"},
  "osm": {"osm_snapshot_id": "<id>", "raw_sha256": "<sha256>"},
  "rules": {"policy": "way_is_area-v1", "sha256": "<sha256>"},
  "config": {"policy": "f3-config-v1", "canonical_sha256": "<sha256>"},
  "geometry": {
    "projected_crs": "EPSG:25830",
    "transform_version": "phase1-crs-v1",
    "transform_source_sha256": "<sha256>",
    "association_predicate": "intersects",
    "predicate_direction": "osm_geometry_to_candidate_cell",
    "boundary_contact_policy": "touches",
    "relation_policy": "present_associated_members_one_hop",
    "invalid_geometry_policy": "reject_without_repair",
    "direct_node_policy": "node_bbox_only"
  },
  "software": {
    "generator_source_sha256": "<sha256>",
    "python_version": "<versión>",
    "numpy_version": "<versión>",
    "shapely_version": "<versión>",
    "geos_version": "<versión>"
  },
  "serialization_version": "f3-jsonl-v1"
}
```

El ID completo será
`f3-madrid-pilot-associations-sha256-<digest>`. No participarán hashes de
outputs, paths, hostname, usuario, PID, timestamps, duración, cores, orden de
STRtree, implementación de Python, sistema o arquitectura.

`generator_source_sha256` será el SHA-256 del JSON canónico, sin newline, de un
objeto `{"version":"f3-generator-source-v1","files":[...]}`. Cada entrada
contendrá `path` lógico y SHA-256 de bytes exactos, ordenada por path. La lista
cerrada será:

```text
schemas/f3_association.schema.json
schemas/f3_osm_object.schema.json
schemas/f3_provenance.schema.json
schemas/f3_relation_context.schema.json
src/tfg_phase0/catalog.py
src/tfg_phase0/config.py
src/tfg_phase0/crs.py
src/tfg_phase0/f3_associations.py
src/tfg_phase0/f3_contracts.py
src/tfg_phase0/f3_geometry.py
src/tfg_phase0/f3_identity.py
src/tfg_phase0/f3_inputs.py
src/tfg_phase0/f3_relations.py
src/tfg_phase0/f3_serialization.py
src/tfg_phase0/f3_validation.py
src/tfg_phase0/osm_snapshot.py
src/tfg_phase0/provenance.py
src/tfg_phase0/validation.py
```

Esta lista cubre la transformación desde los inputs verificados hasta los bytes
canónicos, incluida la carga y validación que construye la frontera F3.2. El
código puramente operativo de publicación no determina los bytes y no participa.
Cambiar estas fronteras exige una nueva versión del manifiesto de código o del
generador.

`transform_source_sha256` será SHA-256 de los bytes exactos de
`src/tfg_phase0/crs.py`.

La proyección `f3-config-v1` contendrá exactamente `schema_version`,
`region.name`, los cuatro valores de `region.bbox`, `region.crs`,
`catalog.projected_crs`, `catalog.catalog_version`,
`catalog.candidate_id_prefix`, `catalog.candidate_generation` y
`catalog.border_policy`. Excluirá `osm_acquisition`, `artifacts` y los valores
configurables de spacing y tamaño. El hash del fichero completo será solo
informativo; la identidad utilizará la política y el hash de esta proyección.

La identidad y la provenance registrarán las versiones exactas de Python,
NumPy, Shapely y GEOS. `python_implementation`, `platform_system` y
`platform_machine` serán solo informativos.

Las magnitudes métricas persistidas (`center_distance_m` y los cuatro campos de
`metric_bbox`) se convertirán mediante `Decimal(str(value))`, cuantización a
seis decimales y `ROUND_HALF_EVEN`, y después a número JSON. Se rechazará todo
valor no finito y todo cero se normalizará a `0.0`. Esta canonicalización se
aplica únicamente al construir los documentos persistidos: no modifica
geometrías ni predicados. F3.4 ya entrega `center_distance_m` redondeado a seis
decimales conforme a D050; F3.6 no recalcula la distancia y la cuantización
decimal de ese valor debe ser idempotente.

Los JSONL vacíos tendrán cero bytes. Con una o más filas, cada JSON compacto
terminará en un único `\n`. `provenance.json` será JSON canónico con newline
final. `sha256.txt` tendrá exactamente estas cuatro líneas, en este orden y con
dos espacios entre hash y nombre:

```text
<SHA256>  osm_objects.jsonl
<SHA256>  candidate_osm_associations.jsonl
<SHA256>  relation_context.jsonl
<SHA256>  provenance.json
```

Terminará en newline y no incluirá su propio hash.

La publicación será exclusiva para Linux y usará un temporal privado en el
mismo filesystem, `fsync` de archivos y directorios, lock exclusivo por ID y
`renameat2(RENAME_NOREPLACE)`. No habrá fallback a `rename`; la falta de soporte
producirá error explícito. Los locks abandonados no se romperán automáticamente
y solo se limpiarán recursos propios.

Un bundle existente será cache hit únicamente si supera la validación integral,
reproduce su ID y coincide en inputs efectivos. Un bundle válido de otra
plataforma será cache hit y conservará su provenance. Un destino incompleto o
incoherente será conflicto y nunca se reparará o sobrescribirá.

### Justificación

La decisión convierte D050 en una representación ejecutable y aplica D051 sin
acoplar la identidad a cambios ajenos. Separa identidad algorítmica, provenance
informativa e integridad de los bytes, evitando dependencias circulares.

### Consecuencias

El schema de provenance exigirá `inputs.config.canonical_policy` y
`software.numpy_version`; `F3_IDENTITY_SOFTWARE_FIELDS` incluirá también
`numpy_version`. F3.6 implementará identidad, serialización, provenance,
checksums, validación integral y publicación. F3.7 realizará la campaña
exhaustiva de concurrencia, fallos y corrupción; F3.8 generará los bundles
reales y F3.9 realizará su auditoría final.

La publicación requiere Linux y un filesystem compatible con
`renameat2(RENAME_NOREPLACE)`. El bundle no contendrá tiempos ni metadata
operativa del lock.

### Alternativas descartadas

- Hash del commit Git completo, por incluir cambios ajenos.
- Hash del bundle como ID, por introducir ciclos con provenance.
- Configuración completa, por vulnerar D051.
- `Path.rename()` como fallback, por no garantizar no-replace.
- Plataforma en identidad, por fragmentar resultados equivalentes.
- Rotura automática de locks por antigüedad, por riesgo de carrera.

### Pendiente

Ninguno sobre el diseño F3.6. La publicación de derivados continúa sujeta a la
revisión ODbL prevista en D045-D046 y F3.9.

# Decisiones pendientes

Esta sección es una vista operativa. Cuando un pendiente se resuelva, se
actualizará su DXXX y se retirará de esta vista sin borrar el historial de la
decisión.

## MVP

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Cerrar el perfil compatible de CrossText2Loc | Sin él no se deben generar imágenes ni embeddings definitivos | Autores y verificación local | No bloquea el diseño; sí la generación definitiva | D007 |
| Confirmar el checkpoint OSM propuesto | Determina si el peso oficial es la opción razonable para Madrid | Autores y experimento | No bloquea el diseño; sí la evaluación definitiva | D013 |
| Concretar únicamente los parámetros experimentales del dataset y evaluación | Fija tamaño, captura y análisis sin convertir hipótesis en hechos | Nosotros y experimento | Sí antes de generar el test final | D029–D031 |

## OSM / Fase 2

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea Fase 2? | Decisión |
|---|---|---|---|---|
| Revisar la política vigente y disponibilidad del endpoint antes de una adquisición real | Los límites del servicio pueden cambiar aunque el diseño esté fijado | Responsable del TFG y ejecución | No para implementar; sí antes de llamar a red | D043, D048 |
| Revisar qué metadata pequeña puede publicarse bajo ODbL | Evita redistribuir datos o derivados sin revisar obligaciones | Responsable del TFG | No para una adquisición local; sí para publicar | D045-D046 |

## CrossText2Loc

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Validar o sustituir el checkpoint provisional de Nueva York | Fija arquitectura, dimensión y pesos del MVP | Verificación local y experimento | Sí antes de evaluar el MVP | D013 |
| Perfil exacto de imagen OSM: footprint, zoom, escala y resolución | Determina compatibilidad con el entrenamiento | Autores y verificación local | Sí | D007 |
| Resolver la inconsistencia de `download_osm_street.py` | El script calcula un recorte pero guarda otra variable | Autores y verificación local | Sí | D007 |

## LLM / preselección

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Revisar el vocabulario concepto–OSM | Determina qué pistas son realmente consultables | Nosotros | Sí para las pistas soportadas; puede empezarse con vocabulario mínimo | D018 |
| Elegir el índice geoespacial local | Permite consultar el mismo snapshot que generó el catálogo | Nosotros | Sí antes de implementar la consulta local | D019 |
| Validar tamaños, radios, tolerancias, pesos y umbrales | Controla el compromiso retención–reducción | Experimento | No para una primera prueba; sí para fijar configuración final | D021 |
| Validar centro frente a celda/buffer | Afecta la asociación de evidencias OSM con candidatos | Experimento | No para una primera prueba | D022 |
| Fijar proveedor/modelo LLM y límites operativos | Afecta coste, latencia y calidad del parsing sin cambiar el contrato | Nosotros y experimento | Sí antes de ejecutar el componente; no para su diseño | D021, D026 |
| Comparar extracción y recuperación multilingüe | Puede cambiar el parsing y el embedding textual | Experimento | No para una primera prueba en un idioma | D024 |

## Dataset / evaluación

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Validar 25 m frente a 50 m u otras granularidades | Cambia coste y error de discretización | Experimento | Sí para fijar la configuración final; no para una prueba mínima | D003 |
| Definir posteriormente la extensión final de Madrid | Determina cobertura y coste final | Nosotros | No para el piloto | D004 |
| Elegir formato físico y completar el esquema del manifest | Afecta loaders e índices; el manifest como fuente canónica ya está aceptado | Nosotros | Sí antes de implementar | D012 |
| Determinar tamaño, participantes y partición | Determina precisión estadística y esfuerzo | Experimento y nosotros | Sí antes de cerrar la recogida | D029 |
| Determinar captura, precisión y regla de bordes | Determina la validez de las métricas | Experimento y nosotros | Sí antes de recoger datos | D030 |
| Determinar métricas principales, thresholds e intervalos | Evita seleccionar métricas después de ver resultados | Experimento de desarrollo | Sí antes de abrir el test | D031 |

## GOTPR

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Obtener el procedimiento de generación de Scene Graphs | Sin él no puede reproducirse Madrid de forma compatible | Autores | No para MVP CrossText2Loc; sí para GOTPR | D011 |
| Determinar la geometría de las scenes | Fija la correspondencia espacial | Autores | No para MVP CrossText2Loc; sí para GOTPR | D011 |
| Definir la relación `candidate_id`–`scene_id` | Conecta GOTPR con el catálogo común | Autores y nosotros | No para MVP CrossText2Loc; sí para GOTPR | D011 |
| Verificar compatibilidad del checkpoint con Madrid | Evita presentar una adaptación incompatible como reproducción | Autores y experimento | No para MVP CrossText2Loc; sí para GOTPR | D011 |

## Satélite

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Elegir proveedor y comprobar permisos | Condiciona descarga, caché y derivados | Proveedor y nosotros | No | D015 |
| Fijar perfil de imagen | Determina comparabilidad con el checkpoint | Código oficial, autores y nosotros | No | D015 |
| Elegir estrategia de utilización o fusión | Puede cambiar el ranking y debe evaluarse | Experimento | No | D009 |

## Street View / VLM

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| No se registran nuevas decisiones de este componente en la pregunta 1 | Se abordará en una decisión específica | Nosotros y proveedor | No | — |

## DialogueVPR

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| No se registran nuevas decisiones de este componente en la pregunta 1 | Se abordará en una decisión específica | Nosotros | No | — |

## TOLoc

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| No se registran nuevas decisiones de este componente en la pregunta 1 | Se abordará en una decisión específica | Nosotros y experimento | No | — |

## GeoBridge

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Aprobar o rechazar su posición como retriever/reranker experimental | Determina la primera ablación y evita una fusión no justificada | Responsable del TFG | No | D037 |
| Obtener licencias de código, checkpoint y release GeoLoc | La disponibilidad pública no concede derechos de uso o redistribución | Autores | No; sí bloquea GeoBridge | D038 |
| Elegir una fuente de imágenes y confirmar almacenamiento/embeddings | La galería visual es imprescindible para el retrieval | Proveedor y nosotros | No; sí bloquea GeoBridge | D038 |
| Validar carga, zero-shot, modalidad y footprint en Madrid | El paper no demuestra nuestro dominio ni nuestras descripciones | Autores y experimento | No; sí para concluir sobre GeoBridge | D039 |

## Licencias/permisos

| Qué hay que decidir | Por qué importa | Quién lo resuelve | ¿Bloquea el MVP? | Decisión |
|---|---|---|---|---|
| Confirmar condiciones del checkpoint y de las imágenes CrossText2Loc | Condiciona uso y publicación de artefactos | Autores y proveedor | No bloquea el diseño; sí antes de distribuir | D007, D013, D016 |
| Confirmar permisos del proveedor satelital | Condiciona almacenamiento y embeddings derivados | Proveedor | No | D015 |
| Confirmar licencias y permisos de GeoBridge/GeoLoc y de la galería visual | Condiciona ejecución, almacenamiento de embeddings y publicación | Autores y proveedor | No para el MVP; sí para la extensión | D038 |
