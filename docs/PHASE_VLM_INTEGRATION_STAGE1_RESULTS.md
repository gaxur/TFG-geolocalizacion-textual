# Resultados de integración VLM posterior a CrossText2Loc

## Integración funcional

`scripts/run_visual_fixture_v4.py` consume ranking CrossText2Loc congelado,
claims revisados, assets/asociaciones Mapillary y una configuración explícita
2B/8B. El request VLM no contiene query ID, rango, coseno, coordenadas o GT. Los
errores técnicos son estados separados; agregación y reranking son procesos
posteriores.

La preparación multiconsulta separa idioma de retrieval y claims: conserva
`en_cartographic` para CrossText2Loc y compila claims desde `es_original`. H18 y
H22 se materializaron con diez candidatos, cobertura completa y 11/10 claims,
sin ejecutar VLM ni abrir referencias.

## H11 con pipeline real

H11 se ejecutó como prueba funcional sin GT: diez candidatos, 48 asociaciones,
44 assets, 12 claims, 576 jobs por modelo, 144 abstenciones de orientación y 432
llamadas reales.

| Medida | 2B | 8B |
|---|---:|---:|
| Outputs inválidos | 0 | 0 |
| `supported` | 248 | 268 |
| `contradicted` | 0 | 0 |
| `unverifiable` | 328 | 308 |
| Carga | 24,42 s | 97,88 s |
| Ejecución | 197,24 s | 595,27 s |
| Pico CUDA asignado | 4,63 GB | 18,08 GB |
| Pico RSS | 5,23 GB | 18,51 GB |

Con reranking desactivado, ambos conservan exactamente IDs, orden, rangos y
cosenos. Las coordenadas baseline no se alteran. Ningún modelo produce evidencia
negativa. Sin anotación humana H11 y lambdas congelados en otras consultas, las
diferencias positivas no demuestran mejora. No se abrió GT ni se activó
reranking.

## Comparación completa 2B/8B sobre 60 pares humanos

| Métrica | 2B | 8B |
|---|---:|---:|
| Accuracy | 0,850 | 0,867 |
| Macro-F1 | 0,557 | 0,570 |
| Falsos soportes | 6 | 5 |
| Falsas contradicciones | 0 | 0 |
| Abstenciones correctas | 39 | 40 |
| Abstenciones incorrectas | 3 | 3 |
| Recall contradicción | 0/2 | 0/2 |
| Outputs válidos | 60/60 | 60/60 |

La diferencia es un caso. Hubo nueve pares discordantes: cuatro favorables al 2B
y cinco al 8B. McNemar exacto bilateral: `p=1,0`. El bootstrap emparejado por
consulta de la diferencia 8B−2B fue `[-0,133; 0,167]`, con cuatro consultas. No
demuestra superioridad ni equivalencia.

Ambos obtuvieron 31/36 en objetos y 3/3 abstenciones egocéntricas. En atributos,
8B obtuvo 18/21 y 2B 17/21. No hay OCR y solo dos contradicciones, por lo que esas
capacidades no están suficientemente evaluadas.

## Evaluación multiimagen

La infraestructura deduplica secuencias y agrega vistas. H11 demuestra que
produce puntuaciones por candidato, pero no existe referencia humana agregada
para afirmar que varias imágenes mejoran frente a una. Esa comparación debe
esperar nuevas anotaciones y agrupar por consulta/candidato.

## Conjunto humano ampliado pendiente

Formulario:

```text
http://127.0.0.1:8765/results/generated/mapillary/visual-reranking-expanded-v1/annotations.html
```

Contiene 72 pares, 24 claims, 12 imágenes y H18/H22/H23/H25. Reutiliza imágenes
existentes; no usa predicciones VLM ni GT. Debe anotarse antes de ejecutar ambos
modelos. Es development ampliado, no test final independiente.

## Incertidumbre y parada

Los 60 pares actuales pertenecen a cuatro consultas usadas para diseñar el
contrato. La diferencia 2B/8B es menor que la incertidumbre agrupada y ninguno
detecta contradicciones. No se declara ganador definitivo por calidad. El 2B
mantiene ventaja de coste y es el default de desarrollo.

Se detiene la expansión GPU hasta recibir las 72 anotaciones. No se activa
reranking: elegir lambdas con H11/GT o con el mismo conjunto del prompt invalidaría
la evaluación.

La evaluación ampliada y la sensibilidad H11 posteriores se documentan en
[PHASE_VLM_EXPANDED_EVALUATION_AND_RERANKING.md](PHASE_VLM_EXPANDED_EVALUATION_AND_RERANKING.md).
