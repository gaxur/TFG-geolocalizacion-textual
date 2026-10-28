# Evaluación geográfica VLM H01-H25 con artefactos existentes

## Alcance ejecutado

Esta fase auditó H01-H25 y ejecutó todos los análisis geográficos que permiten
los bytes y runs ya autorizados. No abrió H26-H61, no descargó imágenes, no
regeneró rankings y no ejecutó modelos sobre inputs nuevos.

H01-H25 son datos históricos de desarrollo. Sus coordenadas proceden de enlaces
o panoramas con incertidumbre desconocida. Los resultados son exploratorios y
no sustituyen una validación independiente.

## Inventario real

| Grupo | Consultas | Ranking | Referencia | Fixture Mapillary/VLM |
|---|---:|---|---|---|
| H01-H02 | 2 | Top-10, 6 variantes, 25/50 m | enlace Google; H01 sin asignación exacta | ninguna |
| H03-H10 | 8 | Top-10, 5 variantes, 25/50 m | enlace Google | ninguna |
| H11 | 1 | Top-10 y Top-100 congelados | enlace Google | 10 candidatos, 44 imágenes, runs 2B/8B |
| H12/H14/H16/H19 | 4 | Top-10/Top-100 | enlace/foto Google | un candidato por consulta, 3 imágenes, 60 pares humanos |
| H18/H22/H23/H25 | 4 | Top-10/Top-100 | enlace Google | un candidato por consulta, 3 imágenes, 72 pares humanos asistidos |
| H13/H15/H17/H20/H21/H24 | 6 | Top-10/Top-100 | enlace Google | ninguna fixture VLM |

Total: 25 consultas; nueve con alguna fixture visual emparejada 2B/8B; solo H11
con varios candidatos de la misma consulta. El inventario por consulta se
materializó en `results/generated/mapillary/h01-h25-vlm-geographic-v1/h01-h25-audit.json`.

Las fotografías Google que originaron las descripciones no están disponibles
localmente. Mapillary es otro proveedor y otros IDs, pero no puede ejecutarse una
comparación perceptual fuente-verificación. H10 reutiliza el panorama histórico
SV-02; H03 y H02 están próximos a SV-03/SV-01. No son muestras independientes.

## Calidad visual 2B frente a 8B

Los modelos recibieron exactamente las mismas imágenes, consultas y claims en
cada fixture.

| Fixture | Pares | 2B accuracy | 8B accuracy | 2B macro-F1 | 8B macro-F1 | McNemar |
|---|---:|---:|---:|---:|---:|---:|
| H12/H14/H16/H19 | 60 | 0,850 | 0,867 | 0,557 | 0,570 | p=1,000 |
| H18/H22/H23/H25 | 72 | 0,750 | 0,833 | 0,477 | 0,810 | p=0,146 |

En la fixture ampliada, 8B detectó 3/4 contradicciones y 2B 0/4. La anotación de
72 pares fue revisada por una persona pero asistida por propuestas Codex. Ninguna
comparación es confirmatoria. La mejor clasificación visual de 8B no demuestra
por sí misma mejor geolocalización.

## Evaluación geográfica completa: H11

H11 es la única consulta con un Top-10 completo fotografiado y runs pareados para
todos los candidatos. La fixture histórica contiene 48 asociaciones: nueve
candidatos con cinco vistas y uno con tres. Se evaluó una selección anidada y
determinista de 1, 3 y hasta 5 imágenes por candidato, `lambda_pos=0,2`, sin
evidencia negativa.

| Modelo | Imágenes solicitadas | Asociaciones | Distancia Top-1 baseline | Distancia Top-1 visual | GeoRecall@1/5/10 50 m |
|---|---:|---:|---:|---:|---|
| 2B | 1 | 10 | 415,48 m | 415,48 m | 0/0/0 |
| 2B | 3 | 30 | 415,48 m | 415,48 m | 0/0/0 |
| 2B | 5 | 48 | 415,48 m | 415,48 m | 0/0/0 |
| 8B | 1 | 10 | 415,48 m | 415,48 m | 0/0/0 |
| 8B | 3 | 30 | 415,48 m | 415,48 m | 0/0/0 |
| 8B | 5 | 48 | 415,48 m | 415,48 m | 0/0/0 |

El candidato más cercano permanece a 237,26 m. H11 no puede convertirse en un
acierto a 50 m reordenando este Top-10. Cinco imágenes no mejoran GeoRecall frente
a una o tres. Ocho imágenes no se evaluaron porque no existen aún bytes/runs para
el lote incremental.

Esta fixture visual histórica no corresponde al ranking `en_cartographic`
Top-100 cuyo H11 contiene un candidato a 14,27 m. Mezclar ambos artefactos sería
una comparación inválida.

## Evaluación parcial de candidatos aislados

Las fixtures de 60/72 pares fotografían un único candidato por consulta. Al
enlazarlas con `es_original + madrid-50m`, solo H12, H16 y H19 pertenecen al
Top-10 seleccionado. H14/H18/H22/H23/H25 pertenecen a otro ranking o variante y
se excluyeron, no se trasladaron artificialmente.

Con candidatos no fotografiados neutrales y `lambda_pos=0,2`:

| Modelo | Consultas | Mejoran | Empeoran | Empatan | Geo@1/5/10 baseline | Geo@1/5/10 visual |
|---|---:|---:|---:|---:|---|---|
| 2B | 3 | 0 | 0 | 3 | 0/0/1 | 0/0/1 |
| 8B | 3 | 0 | 0 | 3 | 0/0/1 | 0/0/1 |

Media Top-1: 271,38 m antes y después. Mediana: 156,96 m antes y después. H12 y
H16 suben una posición el candidato fotografiado, pero no cambian la primera
posición ni ninguna métrica geográfica solicitada.

Este análisis es una simulación parcial, no un reranking visual completo.

## Promoción desde reserva

No pudo ejecutarse promoción empírica Top-20/50/100: no existen fotografías y
veredictos para los candidatos adicionales. El techo geográfico Top-100 indica:

- H16 podría recuperar ≤50 m desde 11-20.
- H23 desde 21-50.
- H20 y H24 desde 51-100.
- H12, H17, H19 y H25 no tienen candidato ≤50 m en el Top-100 actual.

Esto es un techo posterior con GT, no una política capaz de seleccionar esos
candidatos. No se contabilizan promociones correctas o incorrectas porque no se
ejecutó ninguna promoción real.

## Plan de ocho imágenes

Se regeneró metadata-only la fixture H11 con límite ocho:

- 10 candidatos;
- 75 asociaciones disponibles, no 80;
- 67 IDs únicos;
- 44 IDs ya disponibles;
- 23 imágenes nuevas pendientes;
- estimación: 2.916.461 B;
- máximo duro: 184.000.000 B.

Plan:
`h11-eight-image-acquisition-sha256-9e3482443f1bbef948a87b50eea53fbdcdf9c86aa6d99fd23f3bc31a9e313783`.

No se realizó la descarga. El plan usa solo ranking e inventario, nunca la
referencia o el error de H11. La cobertura metadata-only no garantiza visibilidad.

## Caché temporal

`src/tfg_phase0/mapillary_cache.py` implementa:

- `data/cache/mapillary/images/` y `metadata/`;
- descarga única por `image_id`;
- escritura temporal y reemplazo atómico;
- SHA-256 antes de publicar el archivo;
- marcadores de inferencia activa;
- pins para experimentos congelados;
- limpieza por TTL y límite de tamaño sin tocar activos/pins;
- configuración `MAPILLARY_CACHE_DIR`, `MAPILLARY_CACHE_MAX_GB` y
  `MAPILLARY_CACHE_TTL_HOURS`.

La caché está ignorada por Git y no mueve ni elimina imágenes históricas.

## Conclusión empírica

Con los artefactos existentes no hay evidencia de mejora geográfica de 2B ni 8B:

- H11: ningún cambio de Top-1 o GeoRecall con 1/3/5 imágenes.
- Tres consultas parciales: ningún cambio de Top-1 o GeoRecall.
- 8B muestra mejor clasificación visual en 72 pares, pero esa señal no produjo
  todavía una mejora geográfica medible.
- No hay datos para comparar promoción 2B/8B ni ocho frente a cinco imágenes.

No se declara equivalencia de modelos ni que la verificación visual sea inútil.
La cobertura multicandidato es insuficiente: solo una de 25 consultas permite la
evaluación geográfica visual completa.

## Próximo paso recomendado

Solicitar autorización únicamente para las 23 imágenes del lote H11 incremental,
ejecutar 2B y 8B sobre los mismos nuevos assets y completar la comparación 1/3/5/8.
Si ocho tampoco cambia el orden geográfico de H11, no ampliar este caso. Después,
seleccionar en development un pequeño conjunto de consultas con techo Top-100
recuperable, empezando por H16 y H23, y preparar lotes multicandidato antes de
considerar una adquisición extensa.
