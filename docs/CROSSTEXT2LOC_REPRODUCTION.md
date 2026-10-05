# Reproducción oficial de CrossText2Loc en NVIDIA GB10

## Resultado

La reproducción controlada de CrossText2Loc NewYork-mixed con imágenes OSM
terminó el 5 de octubre de 2026 con estado **REPRODUCIDO**. Se ejecutó solo
inferencia, sin entrenamiento, fine-tuning, cambios de arquitectura ni cambios
en el código de evaluación oficial.

La evidencia numérica compacta está en
[`results/reproductions/crosstext2loc-newyork-osm-gb10-v1/result.json`](../results/reproductions/crosstext2loc-newyork-osm-gb10-v1/result.json).
Los logs brutos y artefactos derivados del dataset se conservan localmente y no
se redistribuyen.

## Entorno de referencia v1

| Componente | Valor validado |
|---|---|
| Equipo | Lenovo ThinkStation PGX |
| GPU | NVIDIA GB10, compute capability 12.1 |
| Imagen | `crosstext2loc-gb10:ngc26.02` |
| ID de imagen | `sha256:9df10d06a947b32d3c4f95601e9f1125073cbc067d76ee9da6f762d7eb254fc2` |
| Base | `nvcr.io/nvidia/pytorch@sha256:8014e4ffc674ae9cc9aecad04b64b29c3d311ed738e54ac3042d2d45690d19e9` |
| Python | 3.12.3 |
| PyTorch | `2.11.0a0+eb65b36914.nv26.02` |
| torchvision | `0.25.0a0+1e53952f.nv26.02.44259020` |
| CUDA de PyTorch | 13.1 |
| `CUDA_VERSION` de la imagen | `13.1.1.006` |
| CVG-Text | `6910d2747a94fbe985309bde60cd4732bcbbf50f` |
| OpenAI CLIP | `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1` |
| Modelo | CLIP ViT-L/14@336, FP32, contexto expandido a 300 |
| Checkpoint | `long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth` |
| SHA-256 | `d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d` |

La imagen derivada conserva PyTorch y torchvision de la base NVIDIA. Añade
`accelerate==0.33.0`, `transformers==4.44.2`, `setuptools==80.10.2` y OpenAI
CLIP en el commit indicado. La base y las dependencias directas están fijadas;
el ID anterior identifica la imagen efectivamente validada. Cualquier
reconstrucción debe volver a verificar su ID y las versiones instaladas antes
de considerarse equivalente a v1.

## Validaciones D0-D5

| Etapa | Resultado | Evidencia principal |
|---|---|---|
| D0 | PASS | Runtime NVIDIA, driver y GB10 visibles dentro del contenedor. |
| D1 | PASS | PyTorch NGC 26.02 ejecutó una operación CUDA real sobre `sm_121`. |
| D2 | PASS | Modelo, checkpoint y 1200 muestras validados en CPU; `missing_keys=[]`, `unexpected_keys=[]`. |
| D3 | PASS | El modelo FP32 completo se movió una vez a `cuda:0` y sincronizó correctamente. |
| D4 intento 1 | FAIL operacional | Git rechazó el clon montado por `detected dubious ownership`; no se construyó el modelo ni se ejecutó CUDA o preprocessing. |
| D4 retry | PASS | Una pareja OSM-texto real produjo embeddings FP32 finitos `[1, 768]`, normas 1 y similitud finita. |
| D5 | PASS | `zeroshot.py` y `evaluate.py` oficiales procesaron 1200/1200 muestras, exit code 0. |

El retry D4 corrigió la validación con una excepción `safe.directory` limitada
al proceso Git del contenedor. No modificó el clon ni su configuración
persistente. El primer intento se conserva localmente como evidencia del fallo
de infraestructura, no como fallo de CUDA, modelo, checkpoint o preprocessing.

## Dataset y ejecución D5

- `annotation/NewYork/test.json`: 1000 muestras.
- `annotation/NewYork-photos/test.json`: 200 muestras.
- Total: 1200 muestras, cero imágenes OSM ausentes.
- `query.zip`: no utilizado.
- `batch_size=4`, `num_workers=4`, `shuffle=False`.
- Duración total observada: `49.538392479` segundos.
- Código de salida: `0`.

Comando oficial:

```bash
python zeroshot.py \
  --version NewYork-mixed \
  --img_type osm \
  --model CLIP-L/14@336 \
  --expand \
  --checkpoint long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

## Métricas observadas

| Subconjunto | Muestras | R@1 | R@5 | R@10 | L@50 | L@100 | L@150 | Desviación media |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global | 1200 | 59,08 % | 82,75 % | 90,00 % | 62,00 % | 66,75 % | 69,67 % | 0,18 km |
| Panorama | 1000 | 59,30 % | 82,90 % | 90,10 % | 62,40 % | 67,80 % | 70,90 % | 0,17 km |
| Single-view | 200 | 58,00 % | 82,00 % | 89,50 % | 60,00 % | 61,50 % | 63,50 % | 0,23 km |

El R@1 global observado, 59,08 %, coincide con el valor identificado en el
checkpoint y documentado para New York OSM. Esta comparación no permite inferir
rendimiento en Madrid.

## Limitación metodológica crítica

La evaluación oficial no es una búsqueda global independiente:

```text
texto de consulta
  -> coordenada ground truth extraída del nombre
  -> 100 candidatos geográficamente más cercanos al ground truth
  -> ranking CrossText2Loc dentro de esos 100
  -> métricas
```

`evaluate.py` calcula la distancia Haversine desde la coordenada real de cada
consulta a toda la galería y selecciona los 100 vecinos más cercanos antes de
ordenar por similitud. El ground truth participa en la construcción del conjunto
de candidatos. Esto es correcto para reproducir el protocolo oficial, pero no
es un mecanismo válido en tiempo de consulta para Madrid.

Los experimentos futuros deben mantenerse separados:

| Experimento | Selección de candidatos |
|---|---|
| A. Reproducción oficial | Ground truth → 100 vecinos → CrossText2Loc. |
| B. Baseline Madrid | Descripción → CrossText2Loc sobre catálogo fijado, sin ground truth en consulta. |
| C. Propuesta | Descripción → intención geográfica LLM → preselección OSM determinista → `candidate_id` → CrossText2Loc → Top-K, sin ground truth en consulta. |

Las métricas de A, B y C no deben mezclarse si difieren sus galerías o
mecanismos de selección.

## Estado y continuación

La reproducción de Nueva York cierra el riesgo técnico de ejecutar el modelo y
su evaluación oficial en GB10. No valida transferencia zero-shot, generación de
imágenes OSM ni rendimiento en Madrid.

La siguiente fase del roadmap es **Fase 1: modelo geográfico y manifest de
Madrid**. Debe implementar D001, D002, D004, D005 y D012, manteniendo
configurable la granularidad de D003. No debe generar todavía imágenes o
embeddings definitivos de CrossText2Loc mientras D007 siga pendiente.

También permanecen pendientes D013 para la elección de checkpoint de
transferencia, D016 para permisos de artefactos, D021 y D024 para preselección e
idioma, y D029-D031 para cerrar el dataset y la evaluación de Madrid.
