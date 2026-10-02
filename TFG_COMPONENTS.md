# Componentes necesarios para el TFG

Actualizado el 2 de octubre de 2026. Este inventario aplica el alcance de [PROJECT.md](docs/PROJECT.md), que es la definición principal. El contexto original se conserva en [BASELINE.md](BASELINE.md). No describe componentes ya implementados.

## 1. Sistema acordado

Descripción y zona aproximada → LLM → consulta estructurada y preselección geográfica → recuperación sobre el catálogo offline con CrossText2Loc o GOTPR → fotografías de Street View y VLM → diálogo cuando exista ambigüedad → Top-K con coordenadas y evidencias.

Se compararán CrossText2Loc y GOTPR como variantes con pesos fijos, sin entrenamiento ni fine-tuning. Empezar con uno permite validar el recorrido; no elimina la comparación prevista. No se exige encadenarlos. La integración de Google Street View está condicionada a confirmar el uso permitido; sigue siendo la fuente fotográfica prevista.

## 2. Componentes y responsabilidades

| Componente | Función | Alcance |
| --- | --- | --- |
| LLM | Extraer objetos, atributos, relaciones, zona e incertidumbres; interpretar respuestas | Núcleo |
| OSM y Overpass o fuente local | Obtener geometrías y etiquetas; generar o filtrar ubicaciones | Núcleo |
| Herramientas propias de preparación | Normalizar OSM, renderizar mapas, construir grafos e índices compatibles | Núcleo; reutilizar código cuando sus permisos y formatos lo permitan |
| CrossText2Loc / CVG-Text | Recuperar imágenes cartográficas a partir de texto | Variante de recuperación para comparar |
| GOTPR | Recuperar grafos de entornos a partir de un grafo textual | Variante de recuperación para comparar |
| Google Street View | Obtener fotografías geolocalizadas cercanas a los candidatos | Verificación del sistema final, condicionada a términos y cobertura |
| VLM | Contrastar pistas visibles y aportar evidencias para reordenar | Verificación del sistema final |
| Diálogo inspirado en DialogueVPR | Formular preguntas sustentadas en diferencias entre candidatos | Sistema final; sin adoptar DQ-pilot por defecto |
| Top-K | Mostrar alternativas, coordenadas asociadas e incertidumbre | Núcleo |
| TOL/TOLoc | Explorar refinamiento métrico dentro de una zona | Opcional |
| GeoBridge | Retrieval/reranking texto–imagen sobre calle, satélite o *drone* asociados al candidato | Extensión opcional; no pertenece al MVP y depende de D038–D039 |
| Wikidata/Wikipedia, satélite y MLLM Retriever | Enriquecimiento o investigación posterior | Opcional |
| SPOT | Referencia de lenguaje a consultas geográficas | Reutilización directa opcional; no genera automáticamente el dataset de Madrid |

## 3. Herramientas que hay que construir o adaptar

### Datos y galería

Definir el límite de Madrid y la unidad candidata; adquirir datos OSM offline, registrar su versión y gestionar errores y caché. Construir un catálogo de referencia con alternativas suficientes, independiente de las posiciones reales reservadas para evaluación. Durante cada consulta se preseleccionarán identificadores del catálogo; no se volverá a descargar OSM ni a calcular embeddings.

Cada candidato necesita un identificador y coordenadas cuyo significado sea explícito. Para comparar modelos, asociar mapas y grafos a ubicaciones comunes cuando sea posible y documentar diferencias de cobertura.

### CrossText2Loc

Preparar offline texto e imágenes OSM compatibles con el checkpoint seleccionado. Las imágenes se obtienen mediante el mecanismo de teselas/renderizado correspondiente, no mediante Overpass. Comprobar estilo, escala, orientación, dimensiones, normalización e idioma antes de producir el catálogo. El modelo recupera imágenes; el adaptador resuelve sus coordenadas mediante metadatos.

### GOTPR

Preparar offline OSM Scene Graphs con categorías, relaciones, embeddings y dimensiones compatibles, y construir durante la inferencia el Text Scene Graph de la descripción mediante un adaptador compatible. Las clases de representación de grafos no equivalen a un conversor completo desde Overpass ni desde lenguaje natural. Auditar los scripts disponibles antes de decidir qué desarrollar. En inferencia, GOTPR solo recibirá los candidatos preseleccionados del catálogo.

GOTPR puede seleccionar candidatos entre los grafos disponibles mediante embeddings de grafos. Su extracción de candidatos es distinta del filtrado geográfico previo inspirado en SPOT. Milvus depende de la configuración elegida; no es un requisito universal de la primera prueba.

### Fotografías y VLM

Seleccionar fotografías reales según proximidad, orientación, fecha y cobertura. Registrar coincidencias, contradicciones y detalles no verificables. Una fachada oculta o fuera de encuadre no constituye evidencia negativa.

Los mapas renderizados desde OSM no sustituyen fotografías de calle para comprobar ladrillo visible, colores o relojes. Las etiquetas OSM aportan evidencia cartográfica. Verificar el candidato no equivale a estimar una posición continua nueva.

### GeoBridge

GeoBridge original codifica texto, calle, satélite y *drone* en un espacio
compartido; no convierte OSM en imágenes ni consume el mapa raster de
CrossText2Loc. Podría precalcular embeddings por `candidate_id` y actuar como
retriever alternativo o reranker después de la preselección. La persistencia de
la galería, su unión al manifest y cualquier fusión de scores serían adaptadores
propios.

No se implementará en las fases del MVP. Antes se requieren licencia del código
y checkpoint, una fuente visual compatible, carga reproducible y un experimento
zero-shot en Madrid. Véase
[requisitos auditados de GeoBridge](docs/DATASET_MODEL_REQUIREMENTS.md#7-geobridge-como-extensión-opcional).

### Diálogo y evaluación

Conservar el estado de consulta, actualizar restricciones con respuestas y establecer reglas de parada. Medir recuperación antes y después del filtrado, VLM y diálogo. Registrar también los casos sin resultados.

## 4. Recursos de ejecución

La selección y las versiones de paquetes siguen pendientes de una prueba de compatibilidad. Las familias previstas son procesamiento geoespacial, consultas HTTP, renderizado, grafos, inferencia y evaluación. Los entornos de los recuperadores pueden mantenerse separados si sus dependencias lo exigen.

El LLM y el VLM podrán consumirse mediante API o ejecutarse localmente según recursos y permisos. Microsoft Foundry es una posibilidad, no una selección definitiva. El LLM y VLM pueden compartir modelo si se comprueba que cumple ambas tareas.

Los checkpoints, datasets, imágenes y dependencias se revisarán por separado del código. Véase [LICENSES_AND_PERMISSIONS.md](docs/LICENSES_AND_PERMISSIONS.md).

## 5. Orden y paralelismo de implementación

Las fases son hitos de dependencias, no una secuencia completamente rígida.
Fases 5 y 6 pueden avanzar parcialmente en paralelo con la espera de la Fase 4,
siempre que no consuman los artefactos o parámetros aún pendientes de
CrossText2Loc. La Fase 7 requiere la integración completa del recuperador que se
vaya a evaluar.

| Hito | Entregable |
| --- | --- |
| P0 | Alcance experimental, permisos aclarados, muestras y prueba de inferencia compatible |
| P1 | Modelo geográfico, manifest, adquisición/cache OSM y catálogo geométrico |
| P2a | Integración completa de CrossText2Loc cuando se resuelvan D007, D013 y D016 |
| P2b | LLM estructurado, preselección e infraestructura de evaluación; puede avanzar en paralelo con P2a |
| P3 | Baseline y propuesta evaluables bajo condiciones comunes |
| P4 | GOTPR, si D011 y la compatibilidad de sus scenes se resuelven |
| P5 | Verificación con fotografías reales, VLM y diálogo, cuando el uso esté confirmado |
| P6 | Extensiones justificadas: GeoBridge y, en su caso, refinamiento con TOLoc |

No se fija una cascada CrossText2Loc → GOTPR. Una eventual combinación requiere un experimento propio. Si un recurso no está disponible o autorizado, se documenta el bloqueo y se avanza en las partes independientes.

## 6. Dataset y protocolo

La organización concreta del catálogo de referencia, el dataset de evaluación
y sus flujos offline/online se documenta en [MADRID_DATASET.md](docs/MADRID_DATASET.md).

El catálogo de referencia contiene candidatos y sus representaciones precalculadas; el conjunto de evaluación contiene descripciones y posiciones reales. Durante la consulta, la preselección elige `candidate_id` del catálogo antes de ejecutar el recuperador. El segundo conjunto no sustituye la preparación del primero.

El protocolo debe fijar región, muestreo, origen de descripciones, idioma, orientación, separación desarrollo/prueba, significado de acierto y K. Las coordenadas reales no pueden centrar la búsqueda ni insertar la respuesta correcta. Se mantendrán alternativas cercanas y casos ambiguos.

Comparaciones previstas: búsqueda OSM sola; CrossText2Loc y GOTPR por separado; texto original frente a preparación del LLM cuando corresponda; con/sin filtrado; con/sin VLM; consulta única frente a diálogo. Medir cobertura, Recall@K según criterio explícito, error geográfico, latencia y coste. La puntuación del recuperador no es una probabilidad calibrada.

## 7. Referencias conservadas

Los siguientes enlaces proceden del inventario anterior. Se conservan como recursos de consulta; su presencia no acredita permisos ni compatibilidad. Las cifras de los artículos y las referencias académicas se desarrollan en [STATE_OF_THE_ART.md](docs/STATE_OF_THE_ART.md).

- <https://learn.microsoft.com/en-us/azure/foundry/>
- <https://learn.microsoft.com/en-us/azure/foundry/concepts/foundry-models-overview>
- <https://www.openstreetmap.org/>
- <https://wiki.openstreetmap.org/wiki/Overpass_API>
- <https://overpass-turbo.eu/>
- <https://github.com/dw-innovation/SPOT>
- <https://www.findthatspot.io/>
- <https://github.com/yejy53/CVG-Text>
- <https://huggingface.co/CVG-Text/CrossText2Loc>
- <https://openaccess.thecvf.com/content/ICCV2025/html/Ye_Where_am_I_Cross-View_Geo-localization_with_Natural_Language_Descriptions_ICCV_2025_paper.html>
- <https://github.com/donghwijung/GOTPR>
- <https://developers.google.com/maps/documentation/streetview/overview>
- <https://developers.google.com/maps/documentation/streetview/metadata>
- <https://developers.google.com/maps/billing-and-pricing/pricing>
- <https://openaccess.thecvf.com/content/CVPR2026/html/Song_DialogueVPR_Towards_Conversational_Visual_Place_Recognition_CVPR_2026_paper.html>
- <https://github.com/WHU-USI3DV/TOL>
- <https://arxiv.org/abs/2604.01644>
- <https://github.com/MiliLab/GeoBridge>
- <https://huggingface.co/Son12s/GeoBridge>
- <https://openaccess.thecvf.com/content/CVPR2026/html/Song_GeoBridge_A_Semantic-Anchored_Multi-View_Foundation_Model_Bridging_Images_and_Text_CVPR_2026_paper.html>
- <https://www.wikidata.org/>
- <https://query.wikidata.org/>
- <https://www.mediawiki.org/wiki/API:Main_page>
