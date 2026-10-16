# Interfaz residente CrossText2Loc para el MVP

## Alcance

F4.6 expone una interfaz Python reutilizable. No implementa HTTP, frontend,
preselección, LLM ni un índice aproximado. El futuro backend podrá envolver esta
interfaz sin volver a implementar carga, codificación, ranking o coordenadas.

## Ciclo de vida

```text
load()
  -> una instancia CrossText2Loc FP32 en GPU
  -> una o dos matrices visuales en CPU
  -> catálogos e IDs residentes

retrieve_many()
  -> valida petición
  -> codifica texto una vez
  -> ranking exhaustivo por galería
  -> Top-K con WGS84 y similitud coseno

close()
  -> libera el modelo y rechaza nuevas consultas
```

Importar `src.tfg_phase0.crosstext2loc_runtime` no importa Torch/CLIP ni
inicializa CUDA. La carga es explícita.

## Interfaz pública

```python
from pathlib import Path
from src.tfg_phase0 import CrossText2LocRetriever, GalleryConfig, ModelConfig

model = ModelConfig(
    checkpoint=Path("checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"),
    clip_weights=Path("/root/.cache/clip/ViT-L-14-336px.pt"),
    cvg_text_root=Path("external/CVG-Text"),
    cvg_utils_sha256="<sha256 verificado>",
    device="cuda",
)

retriever = CrossText2LocRetriever.load(
    model_config=model,
    gallery_configs=[gallery_25m, gallery_50m],
    region_config=Path("config/madrid.yaml"),
)

response = retriever.retrieve_many(
    gallery_ids=["madrid-25m", "madrid-50m"],
    query_id="query-001",
    text="A broad avenue next to a green park",
    language="en",
    k=10,
)

retriever.close()
```

`retrieve()` consulta una sola galería. `retrieve_many()` reutiliza una única
codificación textual para todas las galerías solicitadas.

## Contratos JSON

Petición: `schemas/crosstext2loc_retrieval_request.schema.json`.

```json
{
  "schema_version": "1.0",
  "contract_version": "crosstext2loc-retrieval-request-v1",
  "query": {"query_id": "q1", "text": "A broad avenue", "language": "en"},
  "gallery_ids": ["madrid-25m", "madrid-50m"],
  "top_k": 10
}
```

La petición no admite coordenadas, ground truth, paths, checkpoint ni modelo.
`top_k` debe caber en todas las galerías solicitadas.

Respuesta: `schemas/crosstext2loc_retrieval_response.schema.json`.

Cada resultado contiene:

- `rank`;
- `candidate_id`;
- `latitude` y `longitude` WGS84;
- `cosine_similarity`;
- identificadores de galería visual, embeddings y checkpoint.

La similitud coseno no es una probabilidad ni una confianza calibrada.

## Runner sin HTTP

`scripts/run_f46_retriever.py` procesa un JSON o un flujo JSONL por stdin. En
modo JSONL mantiene el modelo y las galerías dentro del mismo proceso.

La ruta del peso base CLIP se proporciona explícitamente:

```bash
export CLIP_WEIGHTS_PATH=/root/.cache/clip/ViT-L-14-336px.pt
python scripts/run_f46_retriever.py \
  --cvg-utils-sha256 <sha256> \
  --request request.json
```

No abre sockets ni requiere dependencias web.

## Recursos

Configuración: `config/madrid_f46_retriever.json`.

| Galería | Matriz | Residentes |
|---|---:|---:|
| `madrid-50m` | `(253,768)` | 253 candidatos |
| `madrid-25m` | `(1115,768)` | 1.115 candidatos |

Las matrices suman aproximadamente 4,2 MiB y permanecen en CPU. El modelo
permanece en GPU.

Medición real GB10:

| Momento | CUDA asignada | CUDA reservada |
|---|---:|---:|
| Tras carga | 1.712.462.336 B | 1.772.093.440 B |
| Tras primera consulta | 1.726.355.968 B | 1.803.550.720 B |
| Pico de la primera consulta, tras reset post-carga | 1.741.103.104 B | 1.803.550.720 B |

Inicialización observada: 5.571,25 ms. Primera consulta Top-10 sobre ambas
galerías: 154,19 ms. Son medidas de una ejecución experimental, no un SLA.

## Validación y errores

Errores públicos:

- `RetrievalInputError`: texto, idioma, query ID o K inválidos;
- `GalleryNotLoadedError`: alias no cargado;
- `ResourceIntegrityError`: bundle, hash o recurso incompatible;
- `ModelCompatibilityError`: modelo/checkpoint incompatible;
- `InferenceError`: fallo de inferencia/CUDA;
- `RuntimeClosedError`: consulta posterior al cierre.

No existe fallback silencioso a CPU, otro checkpoint, CLIP base u otra galería.

La carga normal valida manifests, matriz, IDs y catálogo sin decodificar todos
los PNG. `deep_validate_visual_assets=True` habilita la validación profunda para
auditoría y cierre.

## Concurrencia

La primera implementación serializa el ciclo completo de cada petición mediante
un lock de vida útil, evitando que `close()` invalide una inferencia activa. La
codificación reutiliza una única instancia PyTorch/CUDA y el futuro MVP no debe
crear copias del modelo.

## Limitaciones

- Perfil visual D007 todavía experimental.
- Checkpoint D013 entrenado en Nueva York.
- Licencia D016 pendiente.
- Política multilingüe D024 pendiente.
- Sin evaluación geográfica formal por D029/D030.
- Búsqueda exhaustiva como baseline; no se incorpora HNSW.
