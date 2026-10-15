# F4.1a: contratos del dataset visual de Madrid

## Alcance

F4.1a define contratos propios para relacionar candidatos F1, imágenes OSM,
futuros embeddings CrossText2Loc y resultados Top-K. No genera imágenes, no
carga checkpoints y no implementa recuperación.

Los artefactos F1, F2 y F3 permanecen inmutables. El dataset visual referencia
el manifest F1 mediante su identificador y SHA-256, y utiliza `candidate_id`
como clave primaria.

## Contratos

| Contrato | Schema | Propósito |
|---|---|---|
| Dataset visual | `schemas/f4_visual_manifest.schema.json` | Fuente, renderer, estilo, perfil, footprint, transformaciones e imágenes |
| Embeddings | `schemas/f4_embedding_manifest.schema.json` | Futuro tensor `[N, 768]`, checkpoint, preprocesamiento y orden de filas |
| Recuperación | `schemas/f4_retrieval_result.schema.json` | Futuro ranking exhaustivo texto-imagen sin ground truth |

Los validadores básicos se integran en `validate_document()`. Las invariantes
que requieren cruzar documentos o inspeccionar ficheros están en
`src/tfg_phase0/f4_validation.py`.

## Perfil experimental

El perfil fijo de F4.1a es:

```text
crosstext2loc-osm-z18-crop256-resize512-exp-v1
```

Su estado es `experimental_unconfirmed`. Registra un raster norte-arriba en
EPSG:3857, referencia de zoom 18, recorte 256 x 256 centrado en el píxel
proyectado del candidato y salida PNG RGB 512 x 512 mediante interpolación
bicúbica. El preprocesamiento posterior previsto es el oficial de OpenAI CLIP
ViT-L/14@336.

Este perfil conserva explícitamente la limitación D007: el script upstream
calcula `img_crop`, pero guarda `img`. F4.1a no interpreta el perfil como una
reproducción confirmada de los raster de entrenamiento.

## Identidad e integridad

`visual_dataset_id` es content-addressed y se calcula sobre:

- versión del contrato y del generador;
- identidad y hash del manifest F1;
- perfil visual completo;
- fuente, renderer y estilo;
- registros ordenados de imágenes y sus hashes.

La serialización de identidad usa JSON UTF-8, claves lexicográficas, separadores
compactos y prohíbe NaN. Las rutas son lógicas y relativas. Los metadatos de una
imagen `generated` deben ser completos; los estados `failed` e
`insufficient_source` no pueden aparentar que existe un artefacto.

`embedding_dataset_id` aplica el mismo criterio content-addressed a la referencia
visual, modelo, checkpoint, preprocesamiento, matriz y orden de candidatos.

`verify_visual_image_files()` comprueba localmente que cada imagen generada:

- permanece dentro de la raíz del dataset y no es un enlace simbólico;
- coincide con el SHA-256 declarado;
- tiene firma e IHDR PNG;
- declara las dimensiones reales;
- usa RGB de 8 bits.

## Compatibilidad con F1

`load_verified_f1_50m()` reutiliza `load_verified_catalog()` y, por tanto,
comprueba schema, provenance, hash de configuración, cuadrícula regenerada,
orden, coordenadas y geometrías. F4.1a añade únicamente la condición provisional
de `spacing_m=50` y `cell_size_m=50`; no resuelve D003.

El validador visual exige que cada imagen corresponda a un candidato del F1
verificado y que latitud y longitud coincidan con su centro. No modifica ni
completa los campos `artifacts` del manifest original.

## Límites para F4.1b

Antes de materializar imágenes reales deben seleccionarse una fuente, un
renderizador y un estilo con versiones y condiciones de uso verificadas. También
debe comprobarse la cobertura alrededor de los candidatos de borde. D007, D013
y D016 permanecen abiertas; F4.1a no genera evidencia de compatibilidad visual,
transferencia zero-shot ni permiso de redistribución.
