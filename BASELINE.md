Os comparto sencilla investigación del estado del arte:

A 24 de septiembre de 2026 esto ya es un área de investigación bastante definida, normalmente bajo nombres como natural-language guided geo-localization, text-to-OSM localization o text-based place recognition. Ya existen modelos que reciben una descripción del entorno y buscan una posición en OpenStreetMap, imágenes satelitales o una galería de ubicaciones.
La parte importante es esta: todavía no hay un “ChatGPT de geolocalización” generalista al que le escribas cualquier descripción en lenguaje natural y te devuelva coordenadas fiables en cualquier ciudad. Pero para un escenario acotado como “sé que estoy en el centro de Madrid”, lo que propones es ya perfectamente razonable como proyecto experimental. De hecho, varios trabajos recientes parten explícitamente de que el usuario conoce aproximadamente la ciudad o distrito. (Open Access CVF)
El estado del arte que más encaja






Sistema
Año
Entrada
Contra qué busca
Resultado
Encaje con tu idea
SPOT
2025/26
Lenguaje natural
OpenStreetMap
Candidatos en mapa
⭐⭐⭐⭐⭐
CrossText2Loc / CVG-Text
ICCV 2025
Descripción larga de lo que ves
OSM / satélite
Tile/localización candidata
⭐⭐⭐⭐⭐
GOTPR
IEEE RA-L 2025
Descripción del entorno
OSM + scene graphs
Lugar candidato
⭐⭐⭐⭐⭐
TOLoc / TOL
IEEE RA-L 2026
Texto + relaciones espaciales
OSM
Posición 2D
⭐⭐⭐⭐⭐
DialogueVPR
CVPR 2026
Conversación
Galería geográfica
Localización progresiva
⭐⭐⭐⭐⭐ para chatbot
MLLM Retriever
CVPR 2026
Lenguaje natural
Satélite
Lugar candidato
⭐⭐⭐⭐
GeoBridge
CVPR 2026
Texto / imágenes
Street View + satélite + dron
Lugar candidato
⭐⭐⭐⭐
1. SPOT: probablemente lo primero que probaría
SPOT es especialmente interesante porque no es solo un paper. Es una herramienta open-source de Deutsche Welle diseñada precisamente para escribir descripciones en lenguaje natural y buscar ubicaciones que las cumplan en OpenStreetMap.
Por ejemplo, conceptualmente acepta cosas del estilo:
building next to a square, close to a tower, with a church nearby...
y transforma el texto en una consulta geoespacial estructurada sobre OSM. Utiliza modelos como Mistral/Llama para interpretar las descripciones, un sistema semántico de etiquetas OSM y devuelve candidatos en un mapa. Fue presentado en ACL 2025 y el proyecto sigue disponible actualmente como SPOT v2.0. (ACL Anthology)
Probar SPOT / FindThatSpot
Código de SPOT
Problema: OSM no contiene necesariamente detalles como “fachada de ladrillo”, “edificio con reloj”, “edificio de color rojo”, etc. Depende muchísimo de cómo esté etiquetado el lugar. Los propios autores señalan las inconsistencias de etiquetado de OSM y el ruido de las descripciones humanas como problemas centrales. (ACL Anthology)
Así que SPOT se parece muchísimo a tu idea, pero solo OSM probablemente no sería suficiente.
2. CrossText2Loc: prácticamente tu problema formulado como paper
El paper “Where am I? Cross-View Geo-localization with Natural Language Descriptions”, presentado en ICCV 2025, formaliza exactamente esta tarea:
Texto describiendo lo que ve una persona → recuperar la ubicación correspondiente utilizando OSM o imágenes satelitales.
Su dataset, CVG-Text, contiene más de 30.000 posiciones en Nueva York, Brisbane y Tokio, con Street View, satélite, OSM y descripción textual asociada. El modelo CrossText2Loc está especialmente diseñado para descripciones largas y mejora en más de 10 puntos el Top-1 Recall respecto a los métodos que comparan. Código y checkpoints están publicados. (Open Access CVF)
Además, el paper plantea exactamente el escenario que tú describes: normalmente el usuario conoce una región aproximada —por ejemplo, un distrito de Nueva York— y el modelo utiliza ese conocimiento para reducir el espacio de búsqueda. Por tanto, decir “estoy en el centro de Madrid” es una ventaja enorme, no un detalle menor. (Open Access CVF)
Hay, eso sí, una limitación importante: sus textos no proceden principalmente de personas escribiendo espontáneamente. Generan descripciones “user-like” a partir de Street View utilizando GPT-4o + OCR + segmentación open-world, aunque hacen control de calidad posterior. (Junyan Ye)
CrossText2Loc / CVG-Text en GitHub
Para mí, es una de las referencias fundamentales para tu caso de uso.
3. GOTPR: especialmente bueno para relaciones entre objetos
Otro trabajo que me parece incluso más interesante para una frase como:
“Tengo una plaza delante, un edificio con reloj a mi derecha y detrás veo una torre.”
es GOTPR — General Outdoor Text-Based Place Recognition Using Scene Graph Retrieval with OpenStreetMap.
En lugar de tratar todo el texto como un único embedding, transforma la descripción en un grafo de escena:
              plaza
                |
             delante
                |
              YO
             /  \
        derecha  detrás
          |        |
       edificio   torre
          |
        reloj
Y genera también grafos equivalentes a partir de OpenStreetMap para comparar sus estructuras.
Eso me parece conceptualmente muy apropiado para tu problema, porque las relaciones espaciales son mucho más discriminativas que simplemente buscar similitud semántica. El trabajo utiliza OSM, está publicado en IEEE Robotics and Automation Letters y dispone de implementación MIT. También realizaron experimentos con descripciones generadas directamente por usuarios, utilizando un LLM para convertir el lenguaje libre al formato que necesita GOTPR. (Seoul National University)
Proyecto GOTPR
4. TOLoc: el que más se acerca a “dame las coordenadas”
Este es probablemente el avance de 2026 que más merece la pena seguir.
TOL: Textual Localization with OpenStreetMap plantea explícitamente:
Texto → OSM → posición geográfica 2D
sin disponer de una posición GNSS inicial.
Han creado aproximadamente 121.000 consultas textuales, cubriendo unos 316 km de trayectorias en Boston, Karlsruhe y Singapur. El modelo TOLoc funciona en dos etapas:
Texto → recuperar la zona de OSM más probable → alinear texto y mapa → estimar la posición dentro del mapa.
Es decir, ya no se limita a decir “creo que es este tile”; intenta devolver una posición métrica. (arXiv)
Código, datos y modelos están publicados desde julio de 2026:
TOL / TOLoc en GitHub
Pero aquí aparece una advertencia muy importante para valorar la madurez real. Los textos del dataset se generan automáticamente a partir del propio OSM con reglas y plantillas, no son verdaderas conversaciones humanas:
posición al este de edificio, posición al norte de parque...
El propio repositorio permite regenerar esas descripciones rule-based. (GitHub)
Y aunque TOLoc mejora claramente a los baselines, los checkpoints publicados siguen mostrando que la localización métrica precisa es difícil: según el repositorio, los distintos modelos obtienen aproximadamente 3,5–4,4 % de éxito a 5 m y, dependiendo del modelo, alrededor de 15,8–26,4 % a 25 m en su configuración publicada. Es decir: esto es investigación puntera, no todavía un GPS textual fiable. (GitHub)
5. DialogueVPR: aquí aparece realmente el “chatbot”
Y hay un paper CVPR 2026 que introduce la pieza que yo añadiría sí o sí: DialogueVPR.
Los autores parten exactamente de un problema que tú vas a tener:
Las descripciones humanas son incompletas y ambiguas.
En vez de intentar resolver todo con una única frase, el sistema puede hacer preguntas al usuario para reducir la incertidumbre. Lo llaman Dialogue Place Recognition y entrenan un componente llamado DQ-pilot para elegir preguntas que permitan separar mejor los candidatos. (Open Access CVF)
Esto permitiría una conversación así:
Usuario
Estoy en el centro de Madrid. A mi derecha veo un edificio con reloj, estoy en una plaza y veo una torre alta de ladrillo.
Sistema
Tengo cuatro zonas compatibles. ¿La torre termina en una aguja o tiene una parte superior rectangular?
Usuario
Rectangular.
Sistema
¿Ves una calle amplia con varios carriles saliendo de la plaza?
Usuario
Sí.
Y después:
“Ubicación más probable: X. Confianza 73%. Alternativas: Y y Z.”
En mi opinión, esta UX tiene muchísimo más sentido que obligar al usuario a escribir una descripción perfecta de una sola vez.
6. Los modelos multimodales están empezando a sustituir a CLIP
Otra tendencia fuerte de 2026 es dejar atrás arquitecturas exclusivamente tipo CLIP.
El trabajo “Turning Generators into Retrievers”, CVPR Findings 2026, adapta directamente Multimodal Large Language Models para recuperar imágenes satelitales a partir de lenguaje natural. Consigue una mejora de 12,2 puntos en Recall@1 en GeoText-1652 y resultados punteros en varios subtasks de CVG-Text. (arXiv)
Es importante porque indica que un sistema futuro probablemente no tendrá un modelo diferente para “entender la frase” y otro para “comparar imágenes”: un MLLM puede empezar a compartir ambas representaciones.
Y GeoBridge, CVPR 2026, va todavía más lejos: crea representaciones comunes para texto, Street View, satélite y dron, con un dataset de más de 50.000 conjuntos alineados procedentes de 36 países. Código, modelo y dataset ya están publicados. (Open Access CVF)
Lo que yo haría para tu caso
Yo no entrenaría un modelo desde cero y tampoco confiaría directamente en GPT, Gemini o Claude para que “adivinen” la ubicación. Haría un sistema híbrido:
LLM como intérprete. Convierte la frase libre en información estructurada: zona aproximada, objetos, atributos, relaciones espaciales, texto visible, tipo de calle, arquitectura, etc.
Tu ejemplo se convertiría conceptualmente en algo como:
search_area: Madrid Centro

objects:
- square
- building
    attribute: clock
- tower
    height: tall
    material: brick

spatial:
- building: right_of_observer
- tower: visible
- observer: inside_square
Generación de candidatos geográficos. Usaría un enfoque tipo SPOT + GOTPR, consultando OSM y posiblemente Wikidata/Wikipedia para obtener candidatos dentro de Madrid.
Retriever semántico. CrossText2Loc o un modelo moderno MLLM recuperaría los tiles de OSM/satélite más compatibles.
Verificación mediante Street View. Aquí creo que está la clave para que funcione de verdad: para cada uno de los 20-50 candidatos finales, recuperar panoramas cercanos y utilizar un VLM para comprobar si desde ese punto realmente se ve “una torre alta de ladrillo + una plaza + un edificio con reloj”. GeoBridge demuestra precisamente el potencial de combinar lenguaje con Street View y vistas aéreas. (Open Access CVF)
Diálogo para desempatar. Si quedan cinco candidatos similares, seguir el paradigma DialogueVPR y preguntar aquello que más información aporte.
Devolver Top-K, no una coordenada única. Por ejemplo:
1. 40.41xxxx, -3.70xxxx — confianza 68 %
   ✓ plaza
   ✓ edificio con reloj
   ✓ torre de ladrillo visible hacia el NE

2. 40.42xxxx, -3.69xxxx — confianza 21 %
   ✓ plaza
   ✓ torre
   ✗ no se identifica reloj

3. ...
Hay un detalle importante en tu ejemplo
La frase “a mi derecha” por sí sola no especifica una dirección geográfica.
Necesitaríamos saber hacia dónde mira la persona, o probar distintas orientaciones posibles. Esto es justo el tipo de dato que un chatbot puede solucionar preguntando:
“¿Hacia dónde estás mirando/caminando?”
o:
“¿La torre queda al otro lado de la plaza respecto al edificio del reloj?”
TOLoc trata explícitamente la información direccional y GOTPR las relaciones espaciales, por lo que ambas ideas serían aprovechables. (arXiv)
Mi conclusión
Tu idea es técnicamente viable hoy como PoC, especialmente porque puedes tener una pista inicial como “Madrid centro”.
Pero distinguiría tres niveles:
✅ Ya existe:
texto → consulta geográfica → candidatos OSM. SPOT.
✅ Estado del arte funcional de investigación:
texto → OSM/satélite → ubicación probable. CrossText2Loc, GOTPR.
🧪 Frontera actual:
texto → coordenadas métricas. TOLoc.
🚀 Donde creo que debería construirse tu solución:
LLM + OSM/Wikidata + CrossText2Loc/GOTPR + Street View/VLM + diálogo tipo DialogueVPR.
No intentaría resolverlo con un único modelo. El sistema híbrido tiene una ventaja enorme: puedes saber por qué piensa que una ubicación es candidata y puedes utilizar cada interacción con la persona para eliminar posiciones.
Y hay un descubrimiento especialmente interesante para vuestro caso: SPOT ya nos da una base open-source que evita tener que construir desde cero toda la capa lenguaje natural → OSM. CrossText2Loc, GOTPR y TOLoc también tienen código publicado. Por tanto, hay material suficiente para montar un PoC real sobre Madrid sin tener que iniciar una investigación de entrenamiento desde cero. (GitHub)
Si quieres, en el siguiente paso puedo ir un nivel más práctico y diseñarte la arquitectura exacta del PoC para Madrid, incluyendo qué repositorios reutilizaría, APIs/datasets, qué modelo usaría en cada bloque y cómo probaría con, por ejemplo, 100 ubicaciones reales para saber rápidamente si merece la pena seguir invirtiendo en ello.
Además, este campo está moviéndose bastante rápido en 2026; puedo monitorizar nuevos papers sobre text-to-location / text-to-OSM / conversational geolocation y avisarte cuando aparezca algo relevante.

