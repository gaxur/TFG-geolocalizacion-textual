# Estado del arte: geolocalización a partir de descripciones en lenguaje natural

## 1. Alcance y base documental

Este documento desarrolla el estado del arte que fundamenta el proyecto de geolocalización mediante descripciones y diálogo. Su objetivo es explicar los enfoques recogidos en la investigación inicial, comparar sus aportaciones y limitaciones e identificar las cuestiones que motivan la propuesta del TFG. El alcance y la arquitectura del proyecto se describen en [PROJECT.md](PROJECT.md).

La revisión se basa exclusivamente en [BASELINE.md](../BASELINE.md), fechado el 24 de septiembre de 2026. Los nombres de trabajos, fechas, características y disponibilidades de recursos se recogen según esa fuente; no se han verificado de forma independiente los artículos ni sus repositorios. Por tanto, este texto constituye una revisión documental preliminar, no una revisión sistemática ni una bibliografía académica ya validada. Las referencias identificables se conservan en el apartado 11.

Se distingue entre los métodos descritos en la fuente y las posibilidades de integración planteadas para el TFG. Las mejoras publicadas que menciona BASELINE.md pertenecen a los experimentos de sus autores y no acreditan el rendimiento del sistema propuesto.

### Definición vigente del proyecto

La revisión conserva las afirmaciones atribuidas a BASELINE.md como contexto de investigación. El alcance vigente se establece en [PROJECT.md](PROJECT.md): el MVP utiliza catálogo OSM, LLM/preselección, CrossText2Loc y evaluación reproducible. GOTPR, la verificación mediante Street View/VLM, el diálogo y TOLoc quedan como extensiones condicionadas a sus dependencias, permisos y viabilidad. Un mapa renderizado de OSM no sustituye la observación fotográfica de una fachada. Las condiciones de reutilización se documentan en [LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md).

## 2. Definición del problema

La geolocalización a partir de lenguaje natural consiste en relacionar una descripción del entorno con lugares geográficos compatibles. La entrada puede incluir objetos, atributos visuales, texto visible y relaciones espaciales: por ejemplo, una plaza, un edificio con reloj a la derecha del observador y una torre de ladrillo al fondo. Una región aproximada conocida permite acotar la búsqueda.

En BASELINE.md se recogen denominaciones como *natural-language guided geo-localization*, *text-to-OSM localization* y *text-based place recognition*. Los trabajos considerados comparten el uso del texto como pista de localización, pero difieren en la representación del entorno, las fuentes geográficas y el resultado que producen.

Conviene distinguir tres resultados posibles. La búsqueda geográfica devuelve lugares que cumplen restricciones. La recuperación de ubicaciones ordena lugares o porciones de mapa según su compatibilidad con una descripción. La localización métrica intenta estimar la posición del observador dentro de una zona. Recuperar correctamente un lugar no implica conocer con precisión dónde está la persona.

El problema combina varias fuentes de incertidumbre. Las descripciones pueden omitir elementos relevantes, los mapas pueden carecer de atributos visuales y diferentes lugares pueden compartir una apariencia semejante. Además, expresiones como «a mi derecha» dependen de la orientación del observador y no equivalen por sí mismas a una dirección cardinal. Estas dificultades motivan enfoques cartográficos, visuales y conversacionales.

## 3. Del lenguaje natural a la búsqueda cartográfica: SPOT

Según la fuente de partida, SPOT es una herramienta de código abierto de Deutsche Welle presentada en ACL 2025, cuya evolución se identifica como SPOT v2.0. Su función es transformar descripciones en lenguaje natural en consultas geoespaciales sobre OpenStreetMap (OSM), para mostrar lugares candidatos en un mapa [R1].

El enfoque utiliza modelos de lenguaje para interpretar la consulta y un sistema semántico de etiquetas de OSM para relacionarla con la información cartográfica. Su interés reside en conectar expresiones del usuario con restricciones que pueden comprobarse sobre una base geográfica. Dentro del TFG, constituye una referencia para la generación inicial de candidatos.

Su principal limitación es la dependencia de lo que contiene OSM. La descripción puede mencionar materiales, colores o detalles de una fachada que no estén registrados. La cobertura y la consistencia de las etiquetas condicionan la búsqueda; la ausencia de un atributo en el mapa no demuestra su ausencia en el lugar. Por ello, la consulta cartográfica ofrece una base para recuperar candidatos, pero puede ser insuficiente para contrastar toda la descripción visual.

## 4. Recuperación de lugares mediante texto y relaciones espaciales

### 4.1. CrossText2Loc y CVG-Text

El trabajo *Where am I? Cross-View Geo-localization with Natural Language Descriptions*, identificado como ICCV 2025 en BASELINE.md, aborda la recuperación de ubicaciones a partir de descripciones de lo que observa una persona. Su modelo, CrossText2Loc, está diseñado para descripciones largas y utiliza OSM o imágenes satelitales como información de búsqueda [R2].

La fuente destaca que el método contempla conocer aproximadamente la región del usuario. Esta condición es relevante para el proyecto: una búsqueda limitada a un distrito reduce el conjunto de alternativas, aunque no elimina la ambigüedad entre lugares cercanos.

El dataset asociado, CVG-Text, se describe como un conjunto de más de 30.000 posiciones en Nueva York, Brisbane y Tokio, con imágenes de Street View, imágenes satelitales, OSM y textos asociados. Una limitación central es que sus descripciones no proceden principalmente de usuarios escribiendo de manera espontánea. Según BASELINE.md, se generan mediante GPT-4o, reconocimiento de texto en imágenes y segmentación de mundo abierto, con control de calidad posterior.

CrossText2Loc aporta una referencia para recuperar porciones de mapa o ubicaciones compatibles con una descripción extensa. Sin embargo, la diferencia entre textos generados y descripciones humanas exige evaluar su transferencia al escenario del TFG. Tampoco se puede presuponer que los resultados en las ciudades del dataset se reproduzcan en Madrid.

### 4.2. GOTPR y los grafos de escena

*General Outdoor Text-Based Place Recognition Using Scene Graph Retrieval with OpenStreetMap* (GOTPR) se identifica en la fuente como un trabajo de IEEE Robotics and Automation Letters de 2025 [R3]. Su enfoque representa el contenido de la descripción mediante un grafo de escena y lo compara con grafos derivados de OSM.

Un grafo permite expresar entidades y relaciones entre ellas. En el ejemplo del proyecto, una plaza, un edificio y una torre pueden conectarse mediante relaciones espaciales, además de describirse individualmente. Esta representación ofrece una forma de considerar la disposición de los elementos al buscar lugares compatibles. El ejemplo es conceptual y no especifica el formato interno de GOTPR.

BASELINE.md indica que los autores también experimentaron con descripciones de usuarios, utilizando un modelo de lenguaje para adaptarlas al formato requerido. Esto resulta relevante para estudiar cómo conectar lenguaje libre y representaciones estructuradas.

La calidad del contraste sigue dependiendo de la información cartográfica y de la interpretación de las relaciones. Si un atributo no está representado en OSM, introducirlo en el grafo textual no garantiza que pueda verificarse. Las relaciones relativas al observador también requieren considerar su orientación.

### 4.3. Comparación entre recuperación semántica y estructural

CrossText2Loc y GOTPR representan dos énfasis distintos en los trabajos revisados: la compatibilidad de descripciones extensas con información geográfica y la comparación de estructuras espaciales. Esta diferencia motiva estudiar ambas opciones, pero no demuestra que su combinación produzca mejores resultados.

El TFG comparará ambos como variantes. Una cascada que recupere zonas con CrossText2Loc y contraste relaciones con GOTPR sería un experimento adicional, no un requisito. La fuente no establece una interfaz común, un orden obligatorio ni una regla para fusionar sus puntuaciones, de modo que la integración permanece como una hipótesis de trabajo.

## 5. De la recuperación a la localización métrica: TOL/TOLoc

La fuente presenta *TOL: Textual Localization with OpenStreetMap* como un trabajo de IEEE RA-L 2026. Su modelo, TOLoc, busca estimar una posición geográfica 2D sin una posición GNSS inicial. Para ello, recupera primero una zona de OSM y después alinea texto y mapa para estimar una posición dentro de ella [R4].

BASELINE.md describe aproximadamente 121.000 consultas textuales y 316 km de trayectorias en Boston, Karlsruhe y Singapur. Las consultas se generan desde OSM mediante reglas y plantillas. Este origen permite construir ejemplos ligados al mapa, pero no equivale a recibir descripciones espontáneas ni conversaciones humanas.

La aportación conceptual de TOLoc es distinguir la selección de una zona de la estimación de una posición dentro de ella. Las tasas de éxito a distancias reducidas citadas en la fuente también advierten de que esta segunda tarea continúa siendo difícil en la configuración descrita. Esos resultados no deben compararse directamente con métricas de recuperación de un lugar o de una porción de mapa.

Para el TFG, TOLoc constituye una referencia de posible refinamiento espacial. Su incorporación no está decidida y no es necesaria para ofrecer una primera lista de candidatos con coordenadas asociadas.

## 6. Desambiguación mediante diálogo: DialogueVPR

DialogueVPR, identificado como un trabajo de CVPR 2026 en BASELINE.md, aborda la insuficiencia de una descripción inicial mediante una interacción progresiva. La fuente describe un componente denominado DQ-pilot que aprende a seleccionar preguntas para distinguir candidatos [R5].

Este enfoque introduce una diferencia relevante respecto a la consulta única: la información disponible puede ampliarse durante la búsqueda. Si varias ubicaciones encajan con la descripción, una pregunta sobre un elemento que las diferencia puede aportar una restricción adicional.

En el escenario del TFG, podría preguntarse por la forma de una torre o por la disposición relativa de dos edificios. Se trata de ejemplos de aplicación de la idea, no de resultados observados. También podría explorarse el diálogo para aclarar la orientación del usuario.

El interés de DialogueVPR es fundamentar el uso de preguntas como parte de la localización. Inspirarse en este paradigma no implica adoptar su componente entrenado ni haber resuelto la política de preguntas. El proyecto tendría que comprobar si el diálogo mejora el acierto y cuántos turnos requiere respecto a una sola descripción.

## 7. Recuperación multimodal y combinación de vistas

BASELINE.md recoge dos referencias adicionales que amplían las fuentes y representaciones utilizadas para recuperar lugares.

*Turning Generators into Retrievers*, identificado como CVPR Findings 2026 en el texto de la fuente, adapta modelos multimodales de gran tamaño para recuperar imágenes satelitales a partir de lenguaje natural [R6]. Su interés para esta revisión es la posibilidad de emplear estos modelos como recuperadores, además de utilizarlos para interpretar entradas o generar respuestas.

GeoBridge, presentado en CVPR 2026, propone un espacio contrastivo común para
texto, panoramas de calle, imágenes satelitales y vistas de *drone* [R7]. El
artículo documenta 52.679 ubicaciones alineadas de 36 países y encoders
CLIP-L/14 específicos por vista, con embeddings normalizados y similitud coseno.
La auditoría del commit `636c413c...` confirma esas cuatro ramas y un flujo
texto→satélite en el script publicado, aunque la CLI contiene inconsistencias y
no se publica un entorno reproducible. El release de GeoLoc solo contiene el
subconjunto *drone*; las vistas de Google no se redistribuyen.

GeoBridge original no usa imágenes OSM. GeoBridge++ amplía el trabajo con mapas
estáticos y hechos geográficos extraídos de OSM, pero no se ha identificado en
el repositorio auditado código, configuración o checkpoint específico para esa
variante. El detalle técnico y de permisos está en
[requisitos auditados de GeoBridge](DATASET_MODEL_REQUIREMENTS.md#7-geobridge-como-extensión-opcional).

Estas referencias apoyan el interés de combinar información visual y geográfica, pero no validan por sí mismas un verificador de candidatos basado en Street View y un modelo de visión y lenguaje (VLM). Esa etapa pertenece a la arquitectura propuesta para el TFG. Su utilidad dependería de la disponibilidad, orientación y contenido de los panoramas, así como de la capacidad del modelo para contrastar las pistas descritas.

## 8. Comparación global y límites de la evidencia

La tabla sintetiza los enfoques según BASELINE.md. Expresa sus diferencias funcionales; no establece una clasificación de rendimiento.

| Enfoque | Entrada y fuente de contraste | Resultado descrito | Aportación para el TFG | Limitación o cuestión pendiente |
| --- | --- | --- | --- | --- |
| SPOT | Lenguaje natural y OSM | Candidatos en un mapa | Transformación de texto en búsqueda geográfica | Cobertura y consistencia de etiquetas |
| CrossText2Loc | Descripciones largas; OSM o satélite | Porción de mapa o ubicación candidata | Recuperación semántica | Transferencia desde textos generados y otras ciudades |
| GOTPR | Descripción estructurada y grafos de OSM | Lugar candidato | Comparación de relaciones espaciales | Información cartográfica disponible y orientación |
| TOLoc | Texto y OSM | Posición 2D dentro de una zona recuperada | Posible refinamiento de posición | Textos basados en plantillas y dificultad métrica |
| DialogueVPR | Conversación y galería geográfica | Localización progresiva | Preguntas para distinguir candidatos | Adaptación y evaluación de la política de diálogo |
| Turning Generators into Retrievers | Texto e imágenes satelitales | Recuperación de imágenes asociadas a lugares | Alternativa de recuperación multimodal | Aplicabilidad al escenario concreto del TFG |
| GeoBridge | Texto, calle, satélite y *drone*; no OSM raster en la versión original | Recuperación por embeddings compartidos | Retriever/reranker visual opcional tras preselección | Licencias ausentes, script incompleto y zero-shot Madrid no demostrado |

No procede comparar directamente las cifras de estos trabajos como si midieran la misma tarea. Difieren en datasets, ciudades, generación de descripciones, fuentes de búsqueda y significado del resultado correcto. El acierto al recuperar una porción de mapa, por ejemplo, no equivale a localizar al observador con un error inferior a unos metros.

La revisión permite identificar capacidades y limitaciones, pero su base documental no basta para seleccionar un método por superioridad experimental. Para ello sería necesario consultar las fuentes originales y definir condiciones de comparación adecuadas al proyecto.

## 9. Síntesis: cuestiones abiertas y posición del TFG

Los trabajos recogidos muestran diferentes maneras de conectar texto y localización: consultas sobre OSM, recuperación semántica, grafos de escena, estimación métrica y diálogo. La información disponible no demuestra que una integración de todos ellos resuelva de forma fiable cualquier descripción ni que se transfiera directamente al escenario propuesto.

De esta revisión se desprenden cuatro cuestiones relevantes para el TFG:

1. **Descripciones humanas frente a textos generados.** El uso de descripciones automáticas en los datasets plantea la necesidad de comprobar el comportamiento con lenguaje espontáneo, incompleto o ambiguo.
2. **Información cartográfica frente a apariencia visible.** Los atributos ausentes en OSM motivan estudiar una comprobación visual, sin asumir que todos puedan observarse en un panorama disponible.
3. **Ambigüedad y orientación.** La coexistencia de candidatos compatibles y las relaciones dependientes del observador motivan explorar preguntas de aclaración.
4. **Recuperación frente a precisión espacial.** Es necesario definir si la salida representa un lugar, una porción de mapa o la posición de la persona, y evaluarla de acuerdo con ese significado.

Estas cuestiones justifican investigar una arquitectura híbrida, acotada geográficamente, que interprete el lenguaje, recupere candidatos, contraste evidencias visuales y dialogue cuando falte información. La propuesta concreta se desarrolla en [PROJECT.md](PROJECT.md#5-arquitectura-híbrida-propuesta).

La contribución prevista se sitúa en la integración y evaluación de esas capacidades para el escenario del proyecto. No se afirma que tal combinación sea inédita ni que mejore los métodos existentes sin experimentación. La delimitación de Madrid centro, la selección de modelos, el acceso a imágenes y el protocolo de evaluación continúan abiertos.

Una evaluación coherente debería estudiar la recuperación inicial, el cambio producido por la verificación visual y el efecto del diálogo. Así se podría determinar qué aporta cada etapa, manteniendo separado el acierto de recuperación de cualquier eventual precisión métrica. Este planteamiento es una propuesta de evaluación del TFG, no un resultado del estado del arte.

### 9.1. Estado actual del proyecto y relación con la revisión

La revisión del estado del arte no define por sí sola el pipeline de Madrid. Las
decisiones vigentes se mantienen en [DECISIONS.md](DECISIONS.md) y el alcance
operativo en [PROJECT.md](PROJECT.md). En particular, el proyecto ha cerrado
conceptualmente las siguientes decisiones de integración:

- el LLM produce una intención geográfica JSON independiente del proveedor y
  no genera directamente Overpass QL, coordenadas ni `candidate_id`;
- la traducción concepto→OSM es determinista, controlada y versionada;
- la preselección consulta un snapshot OSM local, con relajación progresiva y
  fallback dentro de la región declarada;
- el catálogo de referencia y el dataset de evaluación son recursos distintos;
- el test final utilizará descripciones humanas *in situ*, mientras que las
  descripciones manuales o sintéticas quedan limitadas a desarrollo y smoke
  tests;
- se compararán recuperación exacta por `candidate_id` y error geográfico, sin
  confundir una celda recuperada con una estimación GPS continua.

La Fase 0 de implementación está completada: contratos, schemas, configuración,
validadores y provenance. También se ha reproducido la evaluación oficial de
CrossText2Loc NewYork-mixed OSM en la GB10; esta comprobación técnica no forma
parte todavía del pipeline de Madrid. No se ha generado el catálogo de Madrid
ni se ha ejecutado GOTPR.

El roadmap no es completamente secuencial. Las fases de LLM/preselección y de
infraestructura de evaluación pueden avanzar mientras D007, D013 y D016 siguen
pendientes para CrossText2Loc. GOTPR continúa condicionado por D011; satélite,
VLM, diálogo y TOLoc permanecen como extensiones posteriores.
GeoBridge también queda como extensión opcional por D036; su posición concreta
es una propuesta (D037) y depende de licencias/permisos y validación zero-shot
(D038–D039).

## 10. Resumen de pasos para alcanzar el objetivo del proyecto

El objetivo final es construir y evaluar una prueba de concepto que, a partir de una descripción en lenguaje natural y una zona aproximada, devuelva una lista ordenada de ubicaciones candidatas con coordenadas y evidencias, y utilice preguntas de aclaración cuando persista la ambigüedad. La siguiente secuencia resume el desarrollo propuesto en [PROJECT.md](PROJECT.md#9-prioridades-de-desarrollo-y-criterios-de-avance); no describe etapas ya implementadas ni fija las decisiones técnicas pendientes.

| Paso | Trabajo que se propone realizar | Resultado esperado de la etapa |
| --- | --- | --- |
| 1. Delimitar el escenario y el criterio de éxito | Concretar la región de búsqueda, tomando Madrid centro como escenario sugerido, el tipo de descripciones y qué se considerará una ubicación correcta. Definir el significado de las coordenadas devueltas. | Alcance y criterios de evaluación explícitos, sin confundir recuperación de lugares con precisión de tipo GPS. |
| 2. Verificar las referencias y los recursos | Consultar los artículos originales y comprobar código, modelos, datos y condiciones de acceso a OSM y panoramas. Valorar qué recursos pueden reutilizarse. | Referencias verificadas y opciones técnicas viables para el escenario elegido. |
| 3. Preparar el conjunto de evaluación | Seleccionar ubicaciones con posición conocida y recoger descripciones humanas. Definir las métricas y separar los ejemplos usados para ajustar el sistema de los destinados a la evaluación final. | Casos de prueba y un protocolo común para comparar las etapas. El tamaño del conjunto sigue pendiente. |
| 4. Interpretar la descripción | Utilizar un LLM para extraer la zona, los objetos, sus atributos, las relaciones espaciales y el texto visible. Registrar ambigüedades, incluida la orientación del observador. | Una representación estructurada de la consulta que permita buscar evidencias geográficas. |
| 5. Construir una búsqueda inicial sobre OSM | Explorar un enfoque tipo SPOT para generar candidatos dentro de la región. Valorar el enriquecimiento con Wikidata/Wikipedia si aporta información necesaria. | Una primera versión evaluable de búsqueda y una medida de referencia de su capacidad de recuperación. |
| 6. Evaluar la recuperación especializada | Integrar CrossText2Loc para el MVP cuando se resuelvan D007, D013 y D016. Comparar con GOTPR solo como extensión si se resuelve D011. | Candidatos ordenados y una comparación reproducible entre baseline y preselección. |
| 7. Incorporar verificación visual como extensión | Obtener fotografías reales cercanas a los candidatos, tras confirmar el uso permitido, y usar un VLM para contrastar las pistas descritas. | Una ablación con/sin verificación visual, separada del núcleo MVP. |
| 8. Incorporar diálogo como extensión | Formular preguntas sobre diferencias entre candidatos, siguiendo la idea de DialogueVPR. Actualizar la consulta con las respuestas y definir cuándo dejar de preguntar. | Una ablación con/sin diálogo, con coste y número de turnos registrados. |
| 9. Integrar la salida Top-K | Presentar las K mejores alternativas con sus coordenadas, coincidencias, discrepancias e información no comprobada. Definir K y cómo comunicar la incertidumbre. | Un recorrido completo desde la descripción hasta una respuesta geográfica explicada. Los porcentajes de confianza requerirían calibración. |
| 10. Evaluar el sistema completo y documentar los límites | Comparar la búsqueda inicial, la recuperación especializada, la verificación visual y el diálogo con el protocolo definido. Analizar fallos y medir error en metros únicamente si la salida permite esa comparación. | Resultados propios del TFG que permitan valorar qué aporta cada bloque y en qué condiciones funciona la prueba de concepto. |

Durante el uso del sistema, el recorrido previsto sería: **descripción y zona aproximada → interpretación → preselección sobre el catálogo offline mediante OSM/Overpass → recuperación de los candidatos seleccionados → verificación visual → aclaración mediante diálogo, si hace falta → salida Top-K con evidencias**. CrossText2Loc usaría embeddings de imágenes OSM o satelitales; GOTPR usaría un Text Scene Graph y OSM Scene Graphs. Las respuestas del usuario volverían a la etapa de interpretación para actualizar la búsqueda.

El refinamiento métrico inspirado en TOLoc y las alternativas multimodales como MLLM Retriever o GeoBridge se valorarían como extensiones posteriores, si el alcance y los resultados lo justifican. El cumplimiento del objetivo se determinaría mediante la evaluación de la prueba de concepto, sin presuponer una mejora por añadir componentes.

## 11. Referencias identificadas y pendientes de normalización

Los identificadores de este documento remiten a los trabajos mencionados en BASELINE.md. El archivo original no conserva URL explícitas ni destinos recuperables de los enlaces. El inventario [TFG_COMPONENTS.md](../TFG_COMPONENTS.md#7-referencias-conservadas) conserva los enlaces incorporados posteriormente. Completar y verificar las citas académicas sigue pendiente.

| Identificador | Trabajo o recurso identificado | Atribución conservada de la fuente |
| --- | --- | --- |
| R1 | SPOT / FindThatSpot | Deutsche Welle; ACL 2025; SPOT v2.0; ACL Anthology. Rótulos: «Probar SPOT / FindThatSpot» y «Código de SPOT». |
| R2 | *Where am I? Cross-View Geo-localization with Natural Language Descriptions*; CrossText2Loc / CVG-Text | ICCV 2025; Open Access CVF; Junyan Ye. Rótulo: «CrossText2Loc / CVG-Text en GitHub». |
| R3 | *General Outdoor Text-Based Place Recognition Using Scene Graph Retrieval with OpenStreetMap*; GOTPR | IEEE RA-L 2025; Seoul National University. Rótulo: «Proyecto GOTPR». |
| R4 | *TOL: Textual Localization with OpenStreetMap*; TOL/TOLoc | IEEE RA-L 2026; arXiv; GitHub. Rótulo: «TOL / TOLoc en GitHub». |
| R5 | DialogueVPR; componente DQ-pilot | CVPR 2026; Open Access CVF. |
| R6 | *Turning Generators into Retrievers*; «MLLM Retriever» | CVPR Findings 2026 en el texto, CVPR 2026 en la tabla inicial; arXiv. La identificación de la publicación debe verificarse. |
| R7 | GeoBridge | CVPR 2026; Open Access CVF. |

Para una versión académica definitiva queda pendiente recuperar y consultar las publicaciones originales, comprobar las afirmaciones atribuidas a cada trabajo y completar las referencias bibliográficas. Esta limitación afecta a la verificación de la revisión; no convierte las propuestas de integración en resultados demostrados.
