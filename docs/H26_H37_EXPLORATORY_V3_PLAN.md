# Exploratory-v3: evidencia visual discriminativa

## Diagnóstico

Atlas v3 y exploratory-v2 permanecen congelados. Top-100 contiene candidatos
geográficamente próximos, pero la evidencia visual no los promociona. Las causas
principales son una vista por candidato, soporte urbano compartido, rótulos no
visibles, asociaciones ambiguas y claims compuestos.

La matriz `diagnostic-matrix.json` etiqueta causas posibles por consulta sin
convertirlas en ground truth causal. Usa distancias solo post hoc y nunca para
seleccionar imágenes o targets.

## Selector Mapillary v3

El selector metadata-only propone hasta tres secuencias y bandas de orientación
por candidato en ranks 1–20. Frente al plan anterior:

- cubre 227 frente a 226 slots;
- usa 151 frente a 65 assets;
- aumenta secuencias de 38 a 59;
- reduce candidatos competidores medios de 6,82 a 4,03;
- aumenta la fracción `spatially_ambiguous` de 44,2 % a 53,4 %.

El resultado es un trade-off, no una mejora geográfica demostrada. No se adquiere
ni se infiere con este selector en exploratory-v3.

## Commons metadata-only

Se planifican 33 targets, máximo tres por consulta, derivados del Top-20 CT2L y
de nombres/categorías OSM distintivos. El cliente usa la API oficial, namespace
File, máximo diez registros por target y no descarga imágenes.

Todo registro conserva licencia, autor, atribución, procedencia y
`location.kind=camera|object|unknown`. Una coordenada de objeto nunca es posición
de cámara. El inventario empieza conservadoramente en `unknown` y exige revisión.

### Criterios de avance

Solo se propondrá un piloto de imágenes si existen al menos tres consultas con
registros complementarios, licencia/autor completos y enlaces OSM de alta
confianza. Se detiene si no hay cobertura, las licencias son incompletas o solo
hay localizaciones desconocidas.

## OSM/F3

OSM guía qué evidencia buscar: nombres exactos, museos, monumentos, farmacias,
torres o edificios históricos. No se usa como prueba de visibilidad ni se repite
la fusión lineal descartada.

## Estado

Se autorizaron y ejecutaron 33 consultas metadata-only Commons, sin descargar
imágenes. Produjeron 73 registros en ocho consultas; una revisión determinista
P180↔Wikidata OSM dejó 32 registros semánticos elegibles en cuatro consultas y
cero posiciones de cámara. El piloto propuesto selecciona ocho ficheros, dos por
consulta, y como máximo 16 llamadas 8B. Requiere una autorización independiente
para píxeles; la autorización metadata-only no la concede. H38–H61 sigue sellado.

La autorización posterior permitió descargar los ocho ficheros (28,10 MB) y
ejecutar ocho llamadas 8B. Los ocho outputs fueron válidos, pero ninguno mostró
el objeto target ni soporte específico para la descripción. Se activa el criterio
de parada `pixels_do_not_show_target`: no se genera reranking y no se amplía
Commons. El resultado confirma sesgo semántico/temático en la búsqueda metadata,
no utilidad geográfica para estas consultas.
