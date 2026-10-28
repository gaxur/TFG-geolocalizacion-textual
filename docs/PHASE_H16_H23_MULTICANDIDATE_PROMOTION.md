# Experimento multicandidato H16/H23

## Pregunta experimental

Se pretende comprobar si Qwen3-VL-2B u 8B puede usar evidencia Mapillary para
promover candidatos de una reserva CrossText2Loc y mejorar GeoRecall@1/5/10 a
50 m y distancia Top-1.

La combinación fijada es exactamente:

- consultas H16 y H23;
- variante `en_cartographic`;
- galería `madrid-50m`;
- Top-100 congelado
  `h11-h25-topn-sha256-92c2ecc639f4e4d650e55be0b7376f73f06279a23c4f59e210a812a14ad43c14`;
- SHA-256 de rankings
  `29bcea393be3048104d3920c1d6ff399aa6f247e49a38bbe34466af579355ed4`.

No se mezclan rankings, claims o runs de `es_original`.

## Auditoría de evidencia existente

| Consulta | Candidato con fotos | Rango objetivo | Fotos | Claims/runs | Compatible con experimento |
|---|---|---:|---:|---|---|
| H16 | `...R0013_C0009` | 6 | 3 | `es_original`, 15 pares | No |
| H23 | `...R0013_C0014` | 10 | 3 | `es_original`, 18 pares | No |

Los seis bytes pueden reutilizarse cuando el selector exacto los incluya, pero
los veredictos no: sus claim IDs se derivan de hashes españoles distintos de los
textos ingleses objetivo.

H16 es además una consulta interior y Mapillary aporta exteriores. Sus 15
etiquetas humanas históricas fueron `unverifiable`. Debe analizarse como control
de cambio de dominio, separado de H23.

## Claims exactos

Se amplió el compilador literal con equivalentes ingleses explícitos, sin
traducir ni inferir conceptos implícitos. El fixture nuevo contiene:

- H16: 17 claims, incluidos 11 objetos, 2 atributos y 4 relaciones;
- H23: 10 claims, incluidos 6 objetos, 2 atributos y 2 relaciones.

Cada claim referencia un span del texto `en_cartographic` y su SHA-256 exacto.
Permanecen pendientes de revisión humana en:

`results/generated/mapillary/h16-h23-multicandidate-top20-v1/review-claims.html`.

Las relaciones egocéntricas son `unverifiable` salvo que exista orientación
externamente comparable; actualmente no existe.

## Selección sin GT

H16 y H23 se eligieron retrospectivamente por el techo geográfico y, por tanto,
solo sirven como development exploratorio. Dentro del experimento se evita una
fuga adicional mediante bloques completos y simétricos:

1. Fase A: rangos 1-20 para ambas consultas.
2. Fase B: rangos 1-50 para ambas consultas.

La instrucción posterior fija **Top-50 como profundidad primaria antes de observar
outputs VLM**. Top-20 queda únicamente como análisis secundario. Por tanto, la
Fase B deja de depender de resultados de la Fase A y se elimina el *optional
stopping* entre ambas profundidades dentro de este experimento.

No se seleccionan solo los rangos 17 o 37, no se detiene la apertura al encontrar
un candidato próximo y no se sustituye un candidato sin cobertura.

Para cada candidato se seleccionan hasta ocho imágenes a 100 m mediante:

1. panorámicas primero;
2. perspectivas orientadas hacia el candidato;
3. proximidad;
4. calidad metadata;
5. `image_id` como desempate;
6. una imagen por secuencia en la primera pasada y relleno posterior.

La proximidad de cámara no demuestra visibilidad. Los assets físicos se deduplican
globalmente, pero cada asociación candidato-imagen permanece en el fixture.

## Cobertura Fase A: Top-20

| Consulta | Slots | Cubiertos a 100 m | Asociaciones |
|---|---:|---:|---:|
| H16 | 20 | 19 | 152 |
| H23 | 20 | 20 | 160 |
| Total | 40 | 39 | 312 |

- 230 IDs únicos.
- 24 ya disponibles localmente.
- 206 pendientes de adquisición.
- 62 IDs se comparten entre varias asociaciones.
- Estimación: 25.063.540 B.
- Máximo duro: 1.648.000.000 B.

El slot H16 rank 8 carece de cámara dentro de 100 m y permanece neutral.

Plan:

`h16-h23-acquisition-sha256-33049e4db165bbd972619900da0f61d2e9ffbf98403f63ef22018e3adb34664f`.

## Cobertura Fase B: Top-50

| Consulta | Slots | Cubiertos a 100 m |
|---|---:|---:|
| H16 | 50 | 49 |
| H23 | 50 | 49 |
| Total | 100 | 98 |

- 772 asociaciones.
- 411 IDs únicos.
- 32 ya disponibles.
- 379 descargas nuevas acumuladas.
- 173 descargas adicionales después de completar la Fase A.
- Estimación acumulada: 46.112.048 B.
- Máximo duro acumulado: 3.032.000.000 B.

Plan:

`h16-h23-acquisition-sha256-c5fabcc68d2066024c8058837d01e7401e473c957173caa53c206c713a331a4d`.

Para mantener el lote completo fijado durante 2B y 8B se recomienda configurar
temporalmente `MAPILLARY_CACHE_MAX_GB=4` en la Fase B. El tamaño real esperado es
muy inferior al máximo duro.

## Techo geográfico posterior

Estos resultados cargan la referencia después de congelar candidatos y no son
resultados VLM:

| Profundidad | GeoRecall H16/H23 @50 m |
|---:|---:|
| 1 | 0/2 |
| 5 | 0/2 |
| 10 | 0/2 |
| 20 | 1/2 |
| 50 | 2/2 |

- H16: primer candidato ≤50 m en rank 17, a 46,68 m.
- H23: primer candidato ≤50 m en rank 37, a 40,19 m.
- Top-1 baseline H16: 406,55 m.
- Top-1 baseline H23: 196,51 m.

El techo demuestra que una promoción es geométricamente posible, no que el VLM
pueda identificar esos candidatos.

## Experimentos ejecutables ahora

No existe un reranking o promoción real compatible que pueda ejecutarse sin
nuevas decisiones humanas o descargas:

- los claims nuevos no están revisados;
- solo 24/230 activos Top-20 están localmente disponibles;
- la cobertura reutilizable no es simétrica entre candidatos;
- los runs 2B/8B existentes están ligados a `es_original`;
- no hay veredictos para los candidatos de reserva rank 17 y 37.

Tratar candidatos sin evidencia como neutrales es correcto, pero ejecutar solo
los 24 activos disponibles introduciría sesgo de disponibilidad y no sería una
prueba multicandidato completa. Por ello no se inventaron promociones ni métricas
CT2L+VLM.

## Protocolo tras autorización

1. Revisar los 27 claims y congelar decisiones.
2. Adquirir los IDs exactos sin sustituciones tras mirar píxeles.
3. Escribir una sola vez por `image_id` en `data/cache/mapillary/` y verificar
   SHA-256.
4. Pinnar el lote durante ambas inferencias.
5. Ejecutar 2B y 8B sobre exactamente las mismas asociaciones y claims.
6. Agregar por claim y secuencia; conflictos y `unverifiable` neutrales.
7. Aplicar solo evidencia positiva y mantener `lambda_neg=0`.
8. Registrar candidato promovido y desplazado; no descartar candidatos.
9. Abrir referencias únicamente en el evaluador y calcular GeoRecall, distancia
   Top-1, promociones correctas/incorrectas y regresiones.

## Protocolo congelado

Configuración versionable:

`config/h16_h23_top50_experiment.json`

Identidades actuales:

- protocolo:
  `h16-h23-protocol-sha256-dca92d1771695b792a617583138d7fa9c70d016c17a3a17b6dcfa0e97e0d1a96`;
- política positiva:
  `topn-promotion-policy-sha256-ab2174e0d59a7a3037d13c7dd3cc430db6f0b8f5c9aeada331fd12162dffa9db`;
- plan Mapillary:
  `h16-h23-acquisition-sha256-c5fabcc68d2066024c8058837d01e7401e473c957173caa53c206c713a331a4d`.

Se congela:

- profundidad primaria Top-50 y secundaria Top-20;
- los 100 slots H16/H23 y sus 411 IDs de imagen seleccionados;
- Qwen3-VL-2B revisión `89644892...` y Qwen3-VL-8B revisión `0c351dd...`;
- prompt `visual-verdict-only-v4`, JSON `verdict` estricto, `do_sample=false` y
  `max_new_tokens=24`;
- deduplicación por secuencia, pesos 0,5/1,0 y neutralidad de conflictos;
- `positive_weight=0,2`, evidencia mínima 0,01 como guardia técnica no ajustada
  en H16/H23, un veredicto válido mínimo y hasta diez promociones;
- bloques abiertos 11-20 y 21-50 desde el inicio;
- `negative_weight=0`, sin descarte;
- distancia Top-1, GeoRecall@1/5/10 a 50/100 m, posiciones, cobertura,
  promociones correctas/incorrectas y regresiones.

Una mejora exige una distancia Top-1 inferior o ganar un GeoRecall solicitado,
informando cualquier pérdida. Una regresión es una distancia Top-1 mayor o la
pérdida de un acierto previo. Con dos consultas retrospectivas no se declarará
superioridad global de un modelo.

## Auditoría de claims

La auditoría automática verificó 27/27 spans y hashes, pero no constituye
aprobación humana. H16 incluye la frase `dark choir`, posible cambio semántico de
la descripción española histórica `retablo oscuro`; debe aprobarse, rechazarse o
corregirse mediante una nueva variante versionada antes de inferencia.

Formulario exacto Top-50:

`results/generated/mapillary/h16-h23-multicandidate-top50-v1/review-claims.html`.

El preflight actual supera todos los checks de identidad y mantiene bloqueados
revisión, autorización, assets, inferencia y evaluación. No se interpreta la
plantilla de autorización como consentimiento.

## Autorización solicitada

El protocolo primario ahora requiere el plan Top-50 acumulado de 379 imágenes
nuevas. La autorización debe referenciar exactamente su `plan_id`:

> Autorizo el plan
> `h16-h23-acquisition-sha256-c5fabcc68d2066024c8058837d01e7401e473c957173caa53c206c713a331a4d`
> para descargar hasta 379 miniaturas Mapillary de 1.024 px, conservarlas en la
> caché privada durante el experimento, ejecutar Qwen3-VL-2B y 8B de pesos fijos
> sin entrenamiento y no publicar un dataset de imágenes.

La plantilla `config/h16_h23_mapillary_authorization.template.json` permanece con
`approved=false`. Debe completarse tras autorización expresa, incluyendo persona,
fecha y límite de retención. El descargador rechaza la plantilla actual antes de
abrir red.

## Estado de H11 y otras restricciones

H11 permanece secundario; no se descargaron sus 23 imágenes. H26-H61 continúa
sellado. No se amplió D004, no se implementó diálogo y no se activó promoción en
el MVP.
