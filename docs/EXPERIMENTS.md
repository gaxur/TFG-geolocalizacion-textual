# Registro de experimentos

Conservar por separado el protocolo oficial de Nueva York, cuya galería de 100
vecinos se obtiene usando las coordenadas reales de cada consulta, y cualquier
evaluación sobre una galería que no utilice el ground truth para seleccionar
candidatos. Sus métricas no son directamente comparables si cambia la galería.

## Plantilla

Cada ejecución futura debe registrar objetivo, fecha, commits, hardware,
entorno, dataset, checkpoint y hash, configuración, comando, resultados,
métricas, tiempo, memoria, problemas y cambios realizados. Solo se sustituirán
valores pendientes por observaciones reales.

## CrossText2Loc NewYork-mixed OSM en GB10

### Objetivo y resultado

Reproducir la evaluación oficial de CrossText2Loc con el checkpoint
NewYork-mixed OSM y los datos originales, exclusivamente en inferencia. La
secuencia D0-D5 terminó el 5 de octubre de 2026 con estado **REPRODUCIDO**.

| Etapa | Estado | Comprobación |
|---|---|---|
| D0 | PASS | Runtime NVIDIA, driver y GB10 visibles dentro del contenedor. |
| D1 | PASS | PyTorch NGC 26.02 ejecutó CUDA en GB10 `sm_121`. |
| D2 | PASS | Modelo, checkpoint y 1200 muestras validados en CPU. |
| D3 | PASS | Modelo FP32 completo transferido una vez a `cuda:0`. |
| D4 intento 1 | FAIL operacional | Git rechazó el mount por `dubious ownership`; no se construyó el modelo ni se ejecutó CUDA. |
| D4 retry | PASS | Una pareja real produjo embeddings finitos y normalizados. |
| D5 | PASS | Evaluación oficial completa, 1200/1200 muestras y exit code 0. |

El primer intento D4 se conserva localmente como evidencia de un fallo de
infraestructura, no de CUDA, modelo, checkpoint o preprocessing. El retry usó
una excepción `safe.directory` limitada al proceso Git del contenedor.

### Entorno de referencia v1

- Equipo: Lenovo ThinkStation PGX.
- GPU: NVIDIA GB10, compute capability 12.1.
- Imagen: `crosstext2loc-gb10:ngc26.02`.
- ID: `sha256:9df10d06a947b32d3c4f95601e9f1125073cbc067d76ee9da6f762d7eb254fc2`.
- Base: `nvcr.io/nvidia/pytorch@sha256:8014e4ffc674ae9cc9aecad04b64b29c3d311ed738e54ac3042d2d45690d19e9`.
- Python: 3.12.3.
- PyTorch: `2.11.0a0+eb65b36914.nv26.02`.
- torchvision: `0.25.0a0+1e53952f.nv26.02.44259020`.
- CUDA de PyTorch: 13.1; `CUDA_VERSION=13.1.1.006`.
- CVG-Text: `6910d2747a94fbe985309bde60cd4732bcbbf50f`.
- OpenAI CLIP: `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1`.
- Modelo: CLIP ViT-L/14@336, FP32, contexto 300.
- Checkpoint: `long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth`.
- SHA-256: `d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d`.
- Parámetros: 428.115.457; `missing_keys=[]`; `unexpected_keys=[]`.

Esta combinación queda congelada como **REFERENCE ENVIRONMENT v1**. Un cambio
posterior de NGC, CUDA, PyTorch, torchvision o dependencias debe crear una nueva
versión del entorno y no sobrescribir silenciosamente esta referencia.

### Dataset y comando

- `annotation/NewYork/test.json`: 1000 muestras.
- `annotation/NewYork-photos/test.json`: 200 muestras.
- Total: 1200; imágenes ausentes: 0.
- No se utilizó `query.zip`.
- `batch_size=4`, `num_workers=4`, `shuffle=False`.

```bash
python zeroshot.py \
  --version NewYork-mixed \
  --img_type osm \
  --model CLIP-L/14@336 \
  --expand \
  --checkpoint long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

### Resultados D5

Duración total observada: 49,538392479 segundos. Código de salida: 0.

| Subconjunto | Muestras | R@1 | R@5 | R@10 | L@50 | L@100 | L@150 | Desviación media |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global | 1200 | 59,08 % | 82,75 % | 90,00 % | 62,00 % | 66,75 % | 69,67 % | 0,18 km |
| Panorama | 1000 | 59,30 % | 82,90 % | 90,10 % | 62,40 % | 67,80 % | 70,90 % | 0,17 km |
| Single-view | 200 | 58,00 % | 82,00 % | 89,50 % | 60,00 % | 61,50 % | 63,50 % | 0,23 km |

El R@1 global observado coincide con el 59,08 documentado para este checkpoint
en New York OSM. Los demás valores se registran como resultados observados de
esta ejecución y no se extrapolan a Madrid.

### Protocolo y limitación

`evaluate.py` extrae la coordenada ground truth de cada consulta, calcula las
distancias a la galería, selecciona los 100 candidatos más cercanos y solo
entonces los ordena mediante CrossText2Loc. Por tanto, esta reproducción oficial
no es una búsqueda global independiente del ground truth.

Los experimentos futuros se separarán en:

- A: reproducción oficial, GT → 100 vecinos → CrossText2Loc;
- B: baseline Madrid sobre un catálogo fijado, sin GT en consulta;
- C: propuesta con intención geográfica LLM, preselección OSM determinista,
  `candidate_id`, CrossText2Loc y Top-K, sin GT en consulta.

No se mezclarán las métricas de A, B y C. La documentación completa está en
[CROSSTEXT2LOC_REPRODUCTION.md](CROSSTEXT2LOC_REPRODUCTION.md) y el resumen
saneado en
[`results/reproductions/crosstext2loc-newyork-osm-gb10-v1/`](../results/reproductions/crosstext2loc-newyork-osm-gb10-v1/).
