# F5.8: auditoría y decisión orientada a GeoRecall@10

## Decisión funcional

D075 fija como objetivo principal que al menos una ubicación geográficamente
próxima aparezca entre las diez primeras candidatas. El análisis conserva este
orden, sin combinar métricas mediante pesos arbitrarios:

1. GeoRecall@10 a 50 m.
2. GeoRecall@10 a 100 m.
3. Recall@10 exacto.
4. Error Haversine mínimo Top-10: media, mediana y distribución.

Recall@1/5, error Top-1, latencias, coste y complejidad son secundarios.
GeoRecall@10 a 100 m indica que al menos una candidata del Top-10 cae dentro de
100 m para una fracción de las consultas. No implica que las diez estén dentro
del radio, no es confianza calibrada y no garantiza precisión futura.

D075 no elige idioma ni variante y no aprueba el uso de Qwen. D076 conserva esa
decisión como `PENDIENTE DE EXPERIMENTO` y de aprobación expresa.

## Fuentes auditadas

Se recalcularon los agregados desde las filas `per_observation`, no desde las
tablas documentales:

- F5.7: `results/generated/f5/f57-final-v3/evaluation.json`.
- F5.5c: `results/generated/f5/f55c-exploratory-real/final-complete/evaluation.json`.
- Variantes y auditorías enlazadas por sus respectivos `manifest.json`.

Los ocho artefactos de F5.7 y los nueve de F5.5c existen y coinciden con tamaño y
SHA-256 declarados. F5.7 contiene 40 filas y F5.5c 350. Cada fila conserva
GeoRecall, error mínimo por K, rango exacto e IDs Top-10. No se ejecutaron nuevos
modelos para F5.8 ni se sobrescribieron artefactos.

## F5.7: cuatro referencias Street View aproximadas

Las cuatro observaciones son development y ya se usaron para formular una
preferencia Top-1; no constituyen una validación independiente. Un acierto cambia
la tasa en 0,25.

| Galería | Variante | R@10 aprox. | Geo@10 50 m | Geo@10 100 m | Mín. Top-10 media | Mediana | Rango |
|---|---|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 0,00 | 0,00 | 0,75 | 84,53 m | 56,13 m | 50,02–175,83 m |
| 25 m | `es_cartographic` | 0,00 | 0,00 | 0,75 | 84,53 m | 56,13 m | 50,02–175,83 m |
| 25 m | `en_conventional` | 0,00 | 0,00 | 0,50 | 189,82 m | 150,91 m | 50,36–407,11 m |
| 25 m | `en_toponym_preserved` | 0,00 | 0,00 | 0,50 | 180,30 m | 131,87 m | 50,36–407,11 m |
| 25 m | `en_cartographic` | 0,00 | 0,25 | 0,50 | 171,33 m | 150,91 m | 26,41–357,09 m |
| 50 m | `es_original` | 0,00 | 0,25 | 0,75 | 89,57 m | 72,90 m | 41,71–170,77 m |
| 50 m | `es_cartographic` | 0,00 | 0,50 | 0,75 | 79,99 m | 53,75 m | 41,71–170,77 m |
| 50 m | `en_conventional` | 0,00 | 0,50 | 0,75 | 96,79 m | 53,03 m | 41,71–239,40 m |
| 50 m | `en_toponym_preserved` | 0,00 | 0,25 | 0,50 | 133,82 m | 126,30 m | 43,27–239,40 m |
| 50 m | `en_cartographic` | 0,00 | 0,50 | 0,75 | 100,67 m | 53,03 m | 41,71–254,92 m |

Bajo D075, la anterior preferencia por `en_toponym_preserved` deja de estar
respaldada por la métrica principal. `es_cartographic` alcanza 0,75 a 100 m en
ambas galerías, 0,50 a 50 m en 50 m y el menor mínimo Top-10 medio de esa galería.
`en_cartographic` lidera a 50 m si se resume descriptivamente entre galerías,
pero solo por un acierto adicional en esta muestra mínima. Los radios de 50 m no
son sólidos porque la incertidumbre de las coordenadas de enlace es desconocida.

## F5.5c development: 24 referencias sintéticas

Un acierto cambia la tasa en aproximadamente 0,0417. Son posiciones geométricas
conocidas, pero no observaciones visuales humanas.

| Galería | Variante | R@10 | Geo@10 50 m | Geo@10 100 m | Mín. Top-10 media | Mediana | Rango |
|---|---|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 0,042 | 0,292 | 0,417 | 193,29 m | 180,91 m | 17,67–565,79 m |
| 25 m | `es_cartographic` | 0,042 | 0,208 | 0,333 | 199,78 m | 189,17 m | 17,67–565,79 m |
| 25 m | `en_conventional` | 0,042 | 0,125 | 0,167 | 200,65 m | 194,29 m | 17,67–489,37 m |
| 25 m | `en_toponym_preserved` | 0,042 | 0,125 | 0,208 | 219,74 m | 192,62 m | 17,67–489,37 m |
| 25 m | `en_cartographic` | 0,042 | 0,125 | 0,208 | 233,91 m | 177,34 m | 17,67–779,68 m |
| 50 m | `es_original` | 0,125 | 0,292 | 0,542 | 142,26 m | 99,78 m | 0,00–412,92 m |
| 50 m | `es_cartographic` | 0,083 | 0,292 | 0,625 | 124,77 m | 99,78 m | 0,00–354,13 m |
| 50 m | `en_conventional` | 0,125 | 0,125 | 0,292 | 148,95 m | 157,83 m | 0,00–349,24 m |
| 50 m | `en_toponym_preserved` | 0,125 | 0,125 | 0,250 | 151,45 m | 134,87 m | 0,00–349,24 m |
| 50 m | `en_cartographic` | 0,125 | 0,125 | 0,208 | 184,24 m | 190,36 m | 0,00–399,13 m |

`es_original` lidera GeoRecall@10 a 50 m en 25 m y empata con
`es_cartographic` en 50 m. A 100 m, `es_original` lidera en 25 m y
`es_cartographic` en 50 m. La elección depende de galería y radio; no se agregan
las dos galerías como muestras independientes.

## F5.5c evaluation: 11 referencias sintéticas

Esta partición no se usa para ajustar prompts ni escoger retrospectivamente una
variante. Se presenta como contraste; un acierto cambia la tasa en 0,0909.

| Galería | Variante | R@10 | Geo@10 50 m | Geo@10 100 m | Mín. Top-10 media | Mediana | Rango |
|---|---|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 0,00 | 0,091 | 0,364 | 170,73 m | 177,68 m | 39,46–389,14 m |
| 25 m | `es_cartographic` | 0,00 | 0,091 | 0,364 | 170,73 m | 177,68 m | 39,46–389,14 m |
| 25 m | `en_conventional` | 0,00 | 0,091 | 0,091 | 202,52 m | 162,81 m | 39,46–459,91 m |
| 25 m | `en_toponym_preserved` | 0,00 | 0,091 | 0,091 | 269,41 m | 212,41 m | 39,46–603,02 m |
| 25 m | `en_cartographic` | 0,00 | 0,091 | 0,091 | 270,20 m | 191,52 m | 17,67–603,02 m |
| 50 m | `es_original` | 0,00 | 0,182 | 0,182 | 186,27 m | 157,84 m | 49,89–353,47 m |
| 50 m | `es_cartographic` | 0,00 | 0,182 | 0,182 | 183,23 m | 157,84 m | 49,89–319,96 m |
| 50 m | `en_conventional` | 0,00 | 0,091 | 0,273 | 175,58 m | 150,26 m | 49,89–427,73 m |
| 50 m | `en_toponym_preserved` | 0,00 | 0,091 | 0,273 | 178,55 m | 150,26 m | 49,89–300,52 m |
| 50 m | `en_cartographic` | 0,00 | 0,000 | 0,364 | 168,31 m | 157,83 m | 50,09–300,52 m |

Evaluation no distingue `es_original` de `es_cartographic` en GeoRecall dentro
de cada galería. En 50 m, el radio de 100 m favorece variantes inglesas, mientras
50 m favorece las españolas. Esta contradicción confirma sensibilidad al radio,
no una ganadora.

## Auditoría de calidad

### Naturaleza de las consultas

F5.5c describe literalmente «la cartografía de esta zona urbana» y relaciones
F3 como `inside_cell`, `crosses_cell` y `overlaps_cell`. No describe lo que ve
una persona. El texto y las imágenes candidatas derivan de OSM, de modo que existe
solapamiento de fuente y sesgo hacia lenguaje cartográfico. No contiene nombres,
visibilidad, orientación, materiales ni carteles; por ello tampoco prueba la
ventaja nominal de `en_toponym_preserved`.

F5.7 sí contiene detalles visuales, algunos sin representación esperable en OSM
Carto: relojes, fachadas, estatuas, farolas, colores o apariencia. Esos detalles
pueden actuar como ruido para CrossText2Loc OSM. Sus coordenadas proceden de
enlaces Street View y no tienen incertidumbre verificada; no permiten defender
GeoRecall a 50 m como métrica precisa.

### Transformación y recuperación

Las auditorías no detectaron coordenadas, IDs, topónimos inventados ni pérdida
heurística de relaciones. En F5.5c no se introdujo ningún nombre OSM oculto. Sin
embargo, las 16 salidas Qwen F5.7 y las 140 F5.5c siguen pendientes de revisión
semántica humana. Una equivalencia heurística no garantiza que alcance,
naturalidad o importancia de cada entidad se conserven.

Los fallos observados pueden proceder de cuatro fuentes distintas:

- recuperación zero-shot con checkpoint entrenado en Nueva York;
- transformación, traducción o filtrado del texto;
- referencia aproximada o asignación espacial;
- desajuste entre pistas visuales y contenido del raster OSM.

Los artefactos actuales no aíslan causalmente esas fuentes. No se atribuyen todos
los errores al checkpoint.

### Suficiencia

Los experimentos no son suficientes para elegir una variante definitiva
orientada a GeoRecall@10. F5.7 tiene cuatro casos y referencias imprecisas;
F5.5c es mayor, pero sintético y contaminado por fuente OSM. El orden cambia con
galería, radio y observación, y los rangos de error son amplios. Tampoco existe
una muestra humana reservada que no haya participado en selección.

## Evaluación de los dos ejemplos propuestos

Las versiones inglesas aportadas por el responsable se conservan conceptualmente
como traducciones humanas de referencia, no como salidas Qwen.

### Ejemplo 1: plaza, Cercanías y torre con reloj

- Plaza, estación ferroviaria y torre son entidades distintivas en conjunto.
- El snapshot congelado contiene infraestructura de Cercanías dentro de D004,
  pero eso no identifica la posición del observador.
- OSM Carto puede representar plaza y estación; no se garantiza que represente
  una torre ni un reloj con suficiente prominencia.
- «A mi derecha» y «detrás» dependen del rumbo de la persona o cámara.
- La descripción por sí sola no demuestra que la observación esté en D004.
- Sin fotografía/documento, coordenada de observación, precisión y orientación,
  solo es apta para análisis cualitativo y transformación textual.

### Ejemplo 2: Pans & Company y cartel Schweppes

- Los dos nombres comerciales son pistas muy distintivas y pueden inducir
  coincidencia nominal sin comprensión de relaciones espaciales.
- El snapshot congelado contiene un POI `Pans & Company` dentro de D004. No se
  usa su coordenada para inferir la del observador ni para enriquecer Qwen.
- No se encontró `Schweppes` en los objetos OSM normalizados congelados. Un
  cartel de fachada es evidencia visual y normalmente no forma parte del raster.
- Edificio grande, cartel, izquierda y derecha requieren evidencia visual y
  orientación.
- El texto no demuestra por sí solo que el punto del observador esté dentro de
  D004. La posición del comercio no puede sustituirlo.
- También queda limitado a análisis cualitativo hasta aportar referencia
  independiente.

Ninguno se incorpora automáticamente a evaluación ni recibe coordenadas por
intuición o reconocimiento del lugar.

## Experimento humano mínimo propuesto

Se recomienda una campaña pequeña de **8–12 localizaciones humanas**, no más
texto sintético OSM. Debe cubrir:

| Perfil | Casos orientativos |
|---|---:|
| Monumentos o edificios reconocibles | 2 |
| Plazas e intersecciones | 2 |
| Establecimientos o nombres comerciales | 2 |
| Relaciones entre varios objetos con orientación | 2 |
| Pistas visuales presentes y ausentes en OSM | transversal |

Cada observación exige descripción española original, evidencia visual o
documental, coordenada del observador verificable, incertidumbre, rumbo cuando
haya relaciones egocéntricas, pertenencia comprobada a D004, estado de revisión,
ID estable y procedencia. La referencia se captura antes de ver rankings.

Se propone usar 6–8 casos para selección y conservar 2–4 localizaciones como
validación posterior sin abrir. Las cinco variantes se congelan y revisan antes
del retrieval. Las traducciones inglesas humanas se identifican en un brazo
separado y no sustituyen las salidas Qwen. Con muestras tan pequeñas se informan
conteos por observación y no se declara superioridad estadística fuerte.

Para incorporar los dos ejemplos hacen falta, como mínimo:

- fotografía o evidencia documental original;
- coordenada del observador y método de captura;
- precisión o incertidumbre estimada;
- rumbo/heading y su incertidumbre;
- confirmación de fecha y pertenencia a D004;
- autorización y estado de revisión.

## Alternativas pendientes

| Opción | Evidencia GeoRecall@10 | Riesgo y coste | Valoración provisional |
|---|---|---|---|
| A. `es_original`, sin Qwen | Lidera development F5.5c a 50 m; empata a 100 m al resumir galerías | Sin pérdida de transformación, sin carga Qwen | Candidata operacional más simple; falta evidencia humana |
| B. Qwen → `es_cartographic` | Empata/lidera varias métricas a 100 m y mínimo Top-10, especialmente en 50 m | Puede eliminar pistas visuales útiles; carga cercana a 90 s y generación de varios segundos | Candidata seria si se prioriza ajuste cartográfico a 100 m |
| C. Qwen → `en_toponym_preserved` | No lidera GeoRecall actual; F5.5c no contiene topónimos para probar su ventaja | Traducción, revisión y runtime Qwen; protege nombres explícitos | No respaldada como default por D075, pero útil en futura muestra nominal |
| D. Otra variante | `en_cartographic` destaca solo en algunas celdas/radios, no de forma estable | Mayor filtrado y riesgo semántico | Evidencia insuficiente |
| E. Posponer y evaluar humanos | Resuelve la principal carencia de validez externa | Requiere recogida y revisión, no nuevos modelos | **Recomendación F5.8** |

Qwen observó aproximadamente 90 s de carga. La generación media fue 7,05 s por
salida en F5.7 y 4,47 s en F5.5c; CrossText2Loc opera en milisegundos con el
runtime residente. `es_original` evita modelo adicional, memoria GPU, revisión
de salida y un nuevo punto de fallo.

## Recomendación y aprobaciones pendientes

Con el orden fijado por D075, **las variantes españolas son las candidatas más
razonables**, pero no existe base suficiente para elegir definitivamente entre
`es_original` y `es_cartographic`. Si fuera necesario congelar una candidata
solo para diseñar el siguiente experimento, development F5.5c favorece
`es_original` en la prioridad primera de 50 m. Esto no es una selección para la
aplicación.

La recomendación es la opción E: recoger y revisar una muestra humana pequeña,
comparar A y B como alternativas principales y mantener C para los casos con
topónimos explícitos. El responsable debe decidir:

1. si autoriza el protocolo de 8–12 observaciones;
2. qué radio operativo debe resolver el compromiso si 50 m y 100 m discrepan;
3. si aporta evidencia, coordenada, precisión y orientación de los dos ejemplos;
4. después del experimento, si aprueba A, B, C u otra opción.

No se modifica la variante predeterminada del frontend o backend.
