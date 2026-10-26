# Evaluación conservadora de Qwen3-VL-2B

## Alcance

Esta evaluación estudia si `Qwen/Qwen3-VL-2B-Instruct`, revisión
`89644892e4d85e24eaac8bacfd4f463576704203`, puede verificar de forma
conservadora descripciones frente a las 24 fotografías Mapillary del piloto.
No usa Ground Truth durante inferencia, no modifica candidatos o rankings, no
ejecuta CrossText2Loc y no implementa reranking.

Las tres imágenes del smoke inicial se utilizaron para diagnosticar errores y
diseñar el prompt v2. También aparecen entre las 24 fotografías. Por tanto, esta
es una evaluación de **desarrollo**, no una validación independiente ni una base
para generalización estadística.

## Auditoría del smoke v1

El resultado original se conserva sin cambios en
`results/generated/mapillary/qwen3-vl-2b-isolated-smoke/result.json`.

| Imagen | Aciertos | Sobreafirmaciones | Debió quedar no verificable |
|---|---|---|---|
| `1210433070142949` | Iglesia, arco y ladrillo | Inmobiliaria y tienda de tejidos sin rótulos legibles | Comercios y relaciones izquierda/derecha |
| `1539904880777289` | Edificio blanco | Desembocadura en plaza, columnas y edificio de piedra con banderas | Geometría de la plaza, banderas y relaciones egocéntricas |
| `483221386454901` | Ninguna coincidencia distintiva confirmada | Plaza peatonal a partir de una similitud genérica | Plaza, edificio de ladrillo y escaleras al aparcamiento |

No hubo contradicciones explícitas en v1. El error dominante fue presentar como
visible información de la descripción que la imagen no justificaba. En las dos
primeras vistas el modelo reconoció orientación ambigua, pero mantuvo relaciones
o un grado fuerte, una inconsistencia interna.

La auditoría estructurada está en
`config/mapillary_qwen3_vl_v1_audit.json`.

## Prompt conservador v2

La variante `mapillary-visual-verification-conservative-v2` exige:

- evidencia atómica exclusivamente observable;
- rótulo exacto legible para nombres o tipos de establecimientos;
- no elevar rasgos genéricos a coincidencias fuertes;
- tratar ausencia y vista parcial como `unverifiable`, no contradicción;
- abstenerse sobre izquierda/derecha sin orientación comparable;
- usar `insufficient` ante distancia, ambigüedad, baja calidad o evidencia solo
  genérica;
- reservar `strong_match` para varios rasgos distintivos visibles.

Las anotaciones humanas no se cargaron en el proceso de inferencia. Cada request
contenía únicamente la descripción española, un `candidate_id` opaco y una
imagen local. La comparación humana se ejecutó después, en otro script.

## Ejecución

Se validaron previamente 24/24 anotaciones completas, correspondencia exacta de
fotografía y candidato, y SHA-256 de las 24 imágenes. Había 9,29 GB libres. No se
descargaron modelos ni fotografías adicionales.

| Recurso | Resultado |
|---|---:|
| Fotografías procesadas | 24 |
| Tiempo de carga | 25,60 s |
| Tiempo total | 130,52 s |
| Pico CUDA asignado | 4.536.583.168 B |
| Pico CUDA reservado | 4.640.997.376 B |
| Pico RSS | 5.357.449.216 B |

El artefacto de inferencia está en
`results/generated/mapillary/qwen3-vl-2b-conservative-v2/inference.json`,
SHA-256 `0e6f5cf828fffec7546968c347e25a8c7464f12bad6c1c51b7b13f0fe15158ea`.

## Correspondencia de categorías

`utility` humana mide si una fotografía resulta útil para revisar la
descripción. `verification_level` mide la compatibilidad visual declarada por el
VLM. No son categorías semánticamente equivalentes.

Para ofrecer un descriptor reproducible se define el proxy estricto:

| Utilidad humana | Proxy VLM |
|---|---|
| `useful` | `strong_match` |
| `partially_useful` | `partial_match` |
| `not_useful` / `unverifiable` | `insufficient` |

Esta convención no es Ground Truth, no calibra probabilidades y no convierte el
acuerdo en una métrica de precisión geográfica.

## Resultados descriptivos

| Medida | Resultado |
|---|---:|
| JSON válidos | 19/24 (79,2 %) |
| Acuerdo exacto con proxy estricto | 14/24 (58,3 %) |
| Coincidencia sobreafirmada | 11/24 (45,8 %) |
| Contradicción injustificada | 11/24 (45,8 %) |
| Error de orientación/relación espacial | 3/24 (12,5 %) |
| `insufficient` correcto entre humanas `not_useful` | 14/20 (70,0 %) |

Matriz descriptiva, filas humanas y columnas VLM:

| Utilidad humana | `strong_match` | `partial_match` | `insufficient` | `contradiction` | JSON inválido |
|---|---:|---:|---:|---:|---:|
| `useful` | 0 | 0 | 1 | 0 | 0 |
| `partially_useful` | 0 | 0 | 2 | 0 | 1 |
| `not_useful` | 0 | 0 | 14 | 2 | 4 |
| `unverifiable` | 0 | 0 | 0 | 0 | 0 |

El prompt desplazó el comportamiento hacia la abstención, pero eliminó también
todos los grados positivos. Cinco respuestas alcanzaron el límite de 256 tokens
repitiendo elementos y quedaron como JSON truncado.

## Errores observados

- Ausencia tratada como contradicción: 8 casos. Ejemplos:
  `1401333830797121`, `1467353800748949`, `174852081596618` y
  `894063571492856`.
- Establecimiento afirmado sin rótulo legible: 5 casos. Ejemplos:
  `1210433070142949`, `2885559761711069`, `2857005767845410`,
  `894063571492856` y `363313801773839`.
- JSON truncado: `1539904880777289`, `2857005767845410`,
  `363313801773839`, `764752502806292` y `1387347911639563`.
- Relación espacial no comprobable: `1116233698895289`, `390624879673869` y
  `4037471469647059`.
- Inconsistencia interna: `1210433070142949` marcó como match una fachada clara
  y simultáneamente la contradijo; `2885559761711069` y `894063571492856`
  declararon matches y ausencias incompatibles sobre los mismos comercios.

La adjudicación manual completa está en
`config/mapillary_qwen3_vl_v2_adjudication.json`. Su resultado agregado está en
`results/generated/mapillary/qwen3-vl-2b-conservative-v2/comparison.json`,
SHA-256 `6be195ca8f37ac5a6a1f0a54546e96b692eb5aebbb0c74ddd6fa2ffbeb9c5d0a`.

## Decisión

Se adopta **B: apoyo exploratorio con revisión humana obligatoria**.

El 2B demuestra capacidad técnica para observar imágenes y abstenerse en muchos
casos, pero no alcanza fiabilidad suficiente para verificar automáticamente ni
reordenar candidatos. Los fallos contractuales, las sobreafirmaciones y las
contradicciones por ausencia impiden A. Sí aporta información exploratoria y
permite estudiar prompts y contratos, por lo que no se concluye C de forma
absoluta.

No se integra el modelo, no se implementa reranking y no se cambia
CrossText2Loc. Antes de plantear otro modelo debe mejorarse el contrato de salida
para limitar listas y repetición, y construirse una fixture de desarrollo con
evidencias atómicas adjudicadas. Una evaluación futura del 4B requeriría nueva
autorización, espacio suficiente y el mismo protocolo; estos resultados no
demuestran que el 4B vaya a resolver los errores.
