# Qwen3-8B para transformación textual

## Función dentro del proyecto

Qwen3-8B se utiliza exclusivamente como transformador textual experimental. Su
función es producir distintas representaciones de una descripción española antes
de ejecutar CrossText2Loc:

```text
descripción española original
        ↓
Qwen3-8B
        ├── español cartográfico
        ├── traducción inglesa convencional
        └── traducción inglesa con topónimos protegidos
        ↓
validación automática
        ↓
revisión humana
        ↓
CrossText2Loc sobre cada variante por separado
```

Qwen no devuelve coordenadas, no selecciona candidatos, no consulta OSM y no
modifica el ranking. Tampoco se usa para responder al usuario como chatbot.

## Modelo validado

| Campo | Valor |
|---|---|
| Modelo | `Qwen/Qwen3-8B` |
| Revisión | `b968826d9c46dd6066d109eabc6255188de91218` |
| Tipo | LLM causal textual, no VLM |
| Parámetros | Aproximadamente 8,2B |
| Formato | 5 shards Safetensors BF16 |
| Tamaño de pesos | 16.381.470.720 bytes |
| Tensores | 399 |
| Licencia declarada | Apache-2.0 |
| Fine-tuning del TFG | Ninguno |
| Modo de razonamiento | Non-thinking |

Fuente oficial: <https://huggingface.co/Qwen/Qwen3-8B>.

Snapshot local validado, fuera del repositorio Git:

```text
$HOME/models/hf/Qwen3-8B-b968826d9c46
```

Manifest SHA-256 calculado por F5.2:

```text
d95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570
```

SHA-256 de los cinco shards:

```text
31d6a825ae35f11fb85b195b4c42c146c051e446433125a215336abdf95cbf5f
5991236cea6fe21f3d43cab0f0e84448734fbbe0789816202989f2ddc9d18282
c5185c4794be2d8a9784d5753c9922db38df478ce11f9ed0b415b7304d896836
b5ee7de71fbf17db3d5704e0c8f2bc7d005ca9e1d7ca2aeb19827b0cfcaa917a
20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff
```

No debe sustituirse silenciosamente por `Qwen3.8`, Qwen2.5, una cuantización u
otro checkpoint. Un cambio de modelo o revisión constituye otra configuración
experimental y debe compararse por separado.

## Entorno de ejecución validado

```text
Hardware: NVIDIA ThinkStation PGX
Arquitectura: ARM64
GPU: NVIDIA GB10 Grace Blackwell
Python: 3.12.3
PyTorch: 2.11.0+cu130
CUDA de PyTorch: 13.0
Transformers: 5.9.0
Accelerate: 1.13.0
Hugging Face Hub: 1.15.0
```

Las dependencias esperadas están en `requirements-f52-qwen.txt`. No se instalan
globalmente ni se añaden al contenedor de CrossText2Loc. Qwen y CrossText2Loc
deben ejecutarse en procesos y entornos separados.

## Configuración de generación

F5.2 fija:

```text
prompt_version: f52-text-transform-v1
do_sample: false
temperature: 0
seed: 0
enable_thinking: false
max_new_tokens: 256
```

`enable_thinking=false` evita bloques de razonamiento `<think>...</think>` y
reduce coste para estas transformaciones cortas. El adaptador utiliza el chat
template oficial cuando admite este parámetro.

La generación observada fue idéntica en 18/18 textos al repetir dos lotes en el
mismo entorno. Esto no garantiza identidad en otro driver, GPU, versión de
PyTorch/Transformers o revisión del modelo.

## Tareas soportadas

### Español cartográfico

Tarea interna:

```text
cartographic_rewrite_es
```

Conserva información potencialmente visible en OSM:

- calles y avenidas;
- cruces e intersecciones;
- plazas y parques;
- edificios y estaciones;
- formas urbanas;
- relaciones espaciales;
- negaciones;
- orientación explícita;
- topónimos.

Puede eliminar detalles puramente visuales como colores, materiales o carteles,
pero debe registrar cualquier eliminación. No se asume que una reescritura
cartográfica mejore la geolocalización.

### Traducción inglesa convencional

Tarea interna:

```text
translate_en_conventional
```

Traduce conservando el significado general. Los nombres propios no se protegen
mediante placeholders, porque interesa observar cómo los trata una traducción
convencional. Después se registran posibles cambios u omisiones de topónimos.

### Traducción inglesa con topónimos protegidos

Tarea interna:

```text
translate_en_preserve_toponyms
```

Conserva literalmente los topónimos propios revisados en F5.1. Ejemplos:

```text
Plaza Mayor  → Plaza Mayor
Gran Vía     → Gran Vía
Puerta del Sol → Puerta del Sol
```

No se protege una expresión genérica como `una plaza grande`.

## Protección mediante placeholders

Antes de traducir:

```text
Plaza Mayor → __TOPONYM_000__
Gran Vía     → __TOPONYM_001__
```

El modelo recibe los placeholders y una instrucción explícita para no
modificarlos. Después se exige:

- que aparezcan todos;
- que cada uno aparezca exactamente una vez;
- que no se inventen placeholders;
- que no quede ninguno sin restaurar.

Finalmente se restauran las menciones originales. Una pérdida, duplicación o
alteración rechaza automáticamente la variante.

La protección se basa en spans anotados manualmente en F5.1, no en mayúsculas ni
en una detección automática de entidades.

## Validación de las salidas

El pipeline comprueba automáticamente:

- texto vacío;
- longitud excesiva;
- idioma incompatible de forma heurística;
- pérdida o modificación de números y distancias;
- cambio de negaciones explícitas;
- pérdida de norte, sur, este, oeste, izquierda, derecha, delante o detrás;
- topónimos protegidos ausentes o alterados;
- placeholders perdidos, duplicados o inventados;
- posibles objetos geográficos nuevos detectables mediante vocabulario.

También registra elementos conservados, eliminados y modificados.

Estas reglas son heurísticas. No prueban equivalencia semántica, no detectan
todos los errores y no convierten una salida en válida para evaluación.

## Revisión humana obligatoria

Las salidas reales se materializan con:

```text
status: generated
review_status: pending
human_review_required: true
```

No pasan a ranking real hasta aplicar decisiones humanas explícitas con:

```bash
python scripts/review_f5_textual_variants.py \
  --sidecar <derived-sidecar.json> \
  --decisions <human-review-decisions.json> \
  --output <reviewed-sidecar.json>
```

El archivo de decisiones debe:

- identificar el sidecar de origen;
- declarar un revisor;
- cubrir exactamente todas las variantes generadas;
- usar `approve` o `reject`;
- incluir notas para cada decisión.

No existe aprobación automática de todas las salidas.

## Ejecución

Generación real:

```bash
python scripts/generate_f5_textual_variants.py \
  --sidecar <sidecar-f51.json> \
  --source-query-dataset <dataset-f43.json> \
  --manifest data/processed/catalog/manifest-50m.json \
  --transformer qwen \
  --model-path "$HOME/models/hf/Qwen3-8B-b968826d9c46" \
  --model-id Qwen/Qwen3-8B \
  --model-revision b968826d9c46dd6066d109eabc6255188de91218 \
  --max-new-tokens 256 \
  --seed 0 \
  --output-root results/generated/f5/f52
```

El adaptador usa `local_files_only=True` y no descarga durante la ejecución.

Rankings, después de cerrar Qwen y revisar las variantes:

```bash
python scripts/rank_f5_textual_variants.py \
  --sidecar <reviewed-sidecar.json> \
  --source-query-dataset <dataset-f43.json> \
  --transformation-run <run.json> \
  --cvg-utils-sha256 <sha256-utils.py> \
  --clip-weights "$HOME/.cache/clip/ViT-L-14-336px.pt" \
  --gallery madrid-50m \
  --gallery madrid-25m \
  --top-k 10 \
  --output-root results/generated/f5/f52
```

## Gestión de GPU

Qwen3-8B y CrossText2Loc no se mantuvieron cargados simultáneamente:

1. detener únicamente la API Atlas;
2. cargar Qwen y generar todas las variantes;
3. cerrar Qwen y liberar CUDA;
4. revisar las salidas;
5. cargar CrossText2Loc y ejecutar rankings;
6. cerrar el runner y restaurar el MVP.

No deben detenerse procesos GPU ajenos al proyecto.

## Telemetría observada en GB10

| Medición | Ejecución 1 | Ejecución 2 |
|---|---:|---:|
| Carga | 82,04 s | 89,28 s |
| CUDA asignada tras carga | 16,381 GB | 16,381 GB |
| Pico CUDA asignado | 16,426 GB | 16,426 GB |
| Generación total, 18 variantes | 22,78 s | 22,86 s |
| Generación media | 1,266 s | 1,270 s |
| Generación mediana | 1,221 s | 1,226 s |
| CUDA asignada tras cierre | 8,52 MB | 8,52 MB |
| CUDA reservada tras cierre | 20,97 MB | 20,97 MB |

La inferencia mínima tardó 2,414 s. No se generó contenido de razonamiento.

## Ejemplos reales

```text
Estoy cerca de la Plaza Mayor, junto a una calle estrecha.
→ I am near the Plaza Mayor, next to a narrow street.
```

```text
No hay ningún parque cerca de esta intersección.
→ There is no park near this intersection.
```

```text
La estación está al norte de la plaza.
→ The station is to the north of the square.
```

```text
Veo una iglesia a mi izquierda y una calle a la derecha.
→ I see a church on my left and a street on the right.
```

`Plaza Mayor` y `Gran Vía` se conservaron en las variantes protegidas. Las 18
salidas del lote fueron revisadas manualmente: 18 aprobadas y 0 rechazadas.

## Efecto observado sobre CrossText2Loc

Se generaron 48 rankings Top-10 sobre seis sondas técnicas y ambas galerías.

| Variante | Acuerdo Top-1 con original | Jaccard@10 | Distancia Top-1 media |
|---|---:|---:|---:|
| Español cartográfico | 0,917 | 0,857 | 31,7 m |
| Inglés convencional | 0,000 | 0,095 | 351,4 m |
| Inglés con topónimos protegidos | 0,000 | 0,072 | 406,3 m |

Estos valores muestran que las traducciones modificaron mucho el ranking en las
seis sondas. No demuestran que el español sea más preciso ni que la traducción
sea perjudicial: no existe ground truth para estas consultas.

## Artefactos y privacidad

Los pesos y resultados permanecen fuera de Git:

```text
$HOME/models/hf/Qwen3-8B-b968826d9c46/
results/generated/f5/f52/
```

No debe introducirse información personal sensible en las descripciones. Antes
de publicar prompts, salidas o decisiones de revisión hay que comprobar su
procedencia y la política de datos aplicable.

## Limitaciones imprescindibles

- Qwen transforma texto; no geolocaliza ni conoce el catálogo.
- Una traducción fluida puede cambiar o perder información espacial.
- La protección de topónimos no protege automáticamente relaciones o atributos.
- Las heurísticas no sustituyen la revisión humana.
- Un score CrossText2Loc mayor no demuestra una mejor ubicación.
- Las métricas actuales son de estabilidad, no Recall ni error geográfico.
- Solo se probaron seis sondas técnicas sin ground truth.
- Qwen3-8B es textual; no es Qwen3-VL ni verifica imágenes.
- No se implementaron fine-tuning, diálogo, preselección OSM, reranking, fusión
  de scores o fusión de coordenadas.

Documentación metodológica completa de F5.2:
[PHASE5_TEXT_TRANSFORMATION.md](PHASE5_TEXT_TRANSFORMATION.md).
