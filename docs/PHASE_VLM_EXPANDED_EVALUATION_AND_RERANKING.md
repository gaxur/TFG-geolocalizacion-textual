# Evaluación ampliada VLM y sensibilidad de reranking H11

## Procedencia

El conjunto ampliado contiene H18, H22, H23 y H25, 72 pares, 24 claims y 12
imágenes. Codex local generó propuestas `AI-proposed`; Marcos revisó las 72 filas.
Los veredictos humanos coinciden 72/72 con las propuestas AI, aunque 19 textos de
evidencia/razón fueron modificados. Por ello se trata como referencia humana
asistida de development, no anotación independiente ciega. Hay mojibake en 19
explicaciones, pero no afecta IDs o clases.

Distribución: 17 `supported`, 4 `contradicted`, 51 `unverifiable`.

## Resultados 2B/8B

| Métrica | 2B | 8B |
|---|---:|---:|
| Outputs válidos | 72/72 | 72/72 |
| Accuracy | 0,750 | 0,833 |
| Macro-F1 | 0,477 | 0,810 |
| Falsos soportes | 9 | 8 |
| Falsas contradicciones | 0 | 0 |
| Recall contradicción | 0/4 | 3/4 |
| Precision contradicción | no definida | 1,000 |
| Abstenciones correctas | 43 | 44 |
| Abstenciones incorrectas | 9 | 4 |
| Latencia decisión media | 0,467 s | 1,379 s |
| Pico CUDA asignado | 4,46 GB | 17,83 GB |
| Pico RSS | 5,23 GB | 18,51 GB |

Matriz 2B:

| Humana | soporte | contradicción | abstención |
|---|---:|---:|---:|
| soporte | 11 | 0 | 6 |
| contradicción | 1 | 0 | 3 |
| abstención | 8 | 0 | 43 |

Matriz 8B:

| Humana | soporte | contradicción | abstención |
|---|---:|---:|---:|
| soporte | 13 | 0 | 4 |
| contradicción | 1 | 3 | 0 |
| abstención | 7 | 0 | 44 |

Por categoría: ambos 3/3 en relaciones egocéntricas por política; 8B mejora en
objetos (28/33 frente a 24/33), atributos (17/24 frente a 16/24) y texto visible
(6/6 frente a 5/6). Los seis casos de texto visible son humanos `unverifiable`,
por lo que no evalúan OCR positivo.

## Incertidumbre emparejada

El 8B acierta 60/72 y 2B 54/72. La tabla emparejada de corrección es: 51 ambos
correctos, 3 solo 2B, 9 solo 8B y 9 ambos incorrectos. Hay 12 discordancias.
McNemar exacto bilateral: `p=0,146`. Bootstrap emparejado por consulta
para diferencia 8B−2B: `+0,083`, IC percentil 95 % `[+0,028; +0,139]`, con solo
cuatro grupos.

El resultado sugiere una ventaja 8B en esta referencia asistida, especialmente
contradicciones, pero no es confirmatorio: pocas consultas, cuatro
contradicciones, dependencia intra-consulta y conjunto de development. No prueba
generalización ni seguridad para descarte.

## Sensibilidad H11 de reranking positivo

Se conservaron todos los resultados para lambdas predeclarados
`[0, 0.05, 0.10, 0.20]`, con `lambda_neg=0`, para ambos modelos. No se selecciona
el mejor lambda.

- 2B: ningún cambio de orden para los cuatro lambdas.
- 8B: ningún cambio hasta 0,10; con 0,20 solo permuta rangos 9/10.
- Top-1 permanece a 415,48 m.
- El candidato más próximo permanece en rango 3 a 237,26 m.
- GeoRecall@1/@5/@10 a 50 m permanecen falsos.
- GeoRecall@10 es invariante por conjunto; H11 es irrecuperable a 50 m mediante
  reranking de esos diez candidatos.

Esto no demuestra que el VLM no pueda ayudar en otras consultas. Demuestra que
la evidencia positiva agregada no supera los márgenes CT2L relevantes en H11 y
que el Top-10 no contiene solución a 50 m.

## Descarte, sustitución y Top-N

No se ejecutan. El 8B tiene solo cuatro contradicciones humanas de referencia y
un falso soporte precisamente sobre una contradicción; no hay validación de falso
descarte suficiente. Además, no existe una reserva Top-50/Top-100 congelada por
consulta, fotografías/claims para esa reserva ni política calibrada. Simular su
impacto sería inventar resultados.

## Decisión provisional

- 2B sigue siendo default por coste para desarrollo y reranking positivo.
- 8B muestra señal de mayor calidad en el conjunto ampliado, pero requiere
  validación independiente antes de adoptarse.
- Ningún modelo se habilita para descarte/MVP.
- No se activa reranking real: faltan lambdas calibrados en consultas con Top-10
  visual completo y una evaluación distinta.
