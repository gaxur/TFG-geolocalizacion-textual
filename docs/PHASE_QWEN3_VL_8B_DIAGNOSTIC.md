# Diagnóstico controlado Qwen3-VL-8B frente a 2B

## Almacenamiento

Se eliminaron exclusivamente las dos cachés autorizadas:

- `~/.cache/huggingface/hub/models--Qwen--Qwen3-Embedding-4B`: 7,6 GB;
- `~/.cache/huggingface/hub/models--Alennnndy--Qwen3.6-27B-AWQ-4bit`: 18 GB.

El espacio libre pasó de unos 7,1 GB a 34,96 GB. No se borraron datasets,
fotografías, anotaciones, resultados, checkpoints o ficheros del proyecto. No
había otro volumen persistente disponible. Tras descargar el 8B quedan
aproximadamente 11,84 GB.

## Modelo

- ID: `Qwen/Qwen3-VL-8B-Instruct`;
- revisión: `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`;
- ruta: `/home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8`;
- tamaño local: 17.545.917.782 B;
- dtype: BF16;
- cuantización: ninguna.

Hashes verificados:

| Shard | SHA-256 |
|---|---|
| 1 | `d5d0aef0eb170fc7453a296c43c0849a56f510555d3588e4fd662bb35490aefa` |
| 2 | `8be88fb5501e4d5719a6d4cc212e6a13480330e74f3e8c77daa1a68f199106b5` |
| 3 | `83de00eafe6e0d57ccd009dbcf71c9974d74df2f016c27afb7e95aafd16b2192` |
| 4 | `0a88b98e9f96270973f567e6a2c103ede6ccdf915ca3075e21c755604d0377a5` |

## Smoke aislado

El smoke BF16 sobre una imagen real y contrato V4 produjo JSON válido y
`supported`. No hubo errores ARM64, GB10, CUDA, PyTorch o Transformers.

| Recurso | 8B smoke |
|---|---:|
| Carga | 98,35 s |
| Decisión | 2,80 s |
| Pico CUDA asignado | 17,83 GB |
| Pico CUDA reservado | 17,87 GB |
| Pico RSS | 18,51 GB |

## Diagnóstico 2B frente a 8B

Se usaron exactamente los mismos diez pares, contrato V4, prompts y parámetros:
5 soportes, 2 contradicciones y 3 abstenciones humanas.

Ambos modelos produjeron la misma matriz:

| Humana | `supported` | `contradicted` | `unverifiable` |
|---|---:|---:|---:|
| `supported` | 4 | 0 | 1 |
| `contradicted` | 0 | 0 | 2 |
| `unverifiable` | 0 | 0 | 3 |

Las diez predicciones fueron idénticas. El 8B no mejoró soportes, abstenciones o
contradicciones y mantuvo 0/2 recall de contradicción.

Coste relativo 8B/2B:

- carga: 3,94×;
- ejecución diagnóstica: 2,34×;
- pico CUDA: 3,98×.

Artefactos:

- smoke: `qwen3-vl-8b-smoke-v4.json`;
- diagnóstico: `qwen3-vl-8b-verdict-diagnostic-v4.json`;
- comparación: `qwen3-vl-2b-vs-8b-diagnostic-v4.json`.

## Decisión

No se ejecutan los 60 pares con 8B: el diagnóstico no muestra mejora razonable y
el protocolo exigía detenerse en ese caso. Se mantiene Qwen3-VL-2B como baseline
y modelo preferido para desarrollo de verificación positiva/abstención. Ninguno
está validado para contradicción, descarte o penalización negativa.

El 8B queda almacenado y verificado, pero no se adopta como modelo principal. No
se ejecutó H11, reranking o integración MVP.
