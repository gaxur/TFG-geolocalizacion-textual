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
| Selección visual | `schemas/f4_visual_selection.schema.json` | Nueve candidatos fijos, roles espaciales y separación de evaluación |
| Fuente OSM | `schemas/f4_osm_source.schema.json` | Datos, provenance, cobertura, licencia y cierre |
| Renderer y estilo | `schemas/f4_renderer_provenance.schema.json` | Configuración, versión, estilo y manifests de assets/fuentes |
| Assets | `schemas/f4_assets_manifest.schema.json` | Hash, tamaño, origen y licencia de recursos cartográficos |
| Embeddings | `schemas/f4_embedding_manifest.schema.json` | Futuro tensor `[N, 768]`, checkpoint, preprocesamiento y orden de filas |
| Recuperación | `schemas/f4_retrieval_result.schema.json` | Futuro ranking exhaustivo texto-imagen sin ground truth |

Los validadores básicos se integran en `validate_document()`. Las invariantes
que requieren cruzar documentos o inspeccionar ficheros están en
`src/tfg_phase0/f4_validation.py`.

## Perfil experimental

El perfil corregido para F4.1b-A es:

```text
crosstext2loc-osm-z18-crop256-resize512-exp-v2
```

Su estado es `experimental_unconfirmed`. Registra un raster norte-arriba en
EPSG:3857, zoom 18, recorte de 256 x 256 píxeles nativos centrado con precisión
subpíxel en el candidato y salida PNG RGB 512 x 512 mediante interpolación
bicúbica. El preprocesamiento posterior previsto es el oficial de OpenAI CLIP
ViT-L/14@336.

El contrato distingue tres superficies:

- `request_bbox`: bbox real solicitada al renderer, ampliada hasta cubrir el
  crop completo de 256 píxeles z18;
- `source_mosaic_bbox`: extensión alineada con las teselas XYZ necesarias;
- `output_bbox`: footprint real del crop nativo de 256 píxeles a zoom 18.

`request_bbox` y `output_bbox` miden aproximadamente 152,874 m proyectados por
lado en esta versión. Los 67,2512 m calculados por el script upstream se
conservan en el perfil únicamente como evidencia de su procedimiento ambiguo;
no se usan para solicitar una fuente insuficiente.

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

El manifest exige siempre los nueve registros de la selección, incluidos los
fallos o coberturas insuficientes con estado explícito. El primer render de
desarrollo actualizará solo su registro, sin publicar un manifest parcial.

`verify_visual_image_files()` comprueba localmente que cada imagen generada:

- permanece dentro de la raíz del dataset y no es un enlace simbólico;
- coincide con el SHA-256 declarado;
- tiene una estructura PNG completa, CRC válidos, `IDAT` descomprimible e
  `IEND` final sin bytes sobrantes;
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

## Selección y cobertura

`config/madrid_f4_visual_fixture.json` fija nueve candidatos independientes de
texto y ground truth. El preflight de solo lectura se ejecuta con:

```bash
python scripts/preflight_f4_visual.py \
  --manifest data/processed/catalog/manifest-50m.json \
  --snapshot-dir data/raw/osm/snapshots/<osm_snapshot_id>
```

La cobertura se decide comprobando que `output_bbox` esté completamente
contenido en la bbox declarada por la fuente. Los nodos exteriores añadidos para
cerrar ways no amplían la cobertura válida.

La selección incluye cinco sondas interiores (`R0004_C0008`, `R0008_C0004`,
`R0008_C0008`, `R0008_C0012`, `R0013_C0008`) y cuatro de borde
(`R0001_C0001`, `R0004_C0016`, `R0008_C0001`, `R0016_C0008`). Con el snapshot
F2 actual, ocho están cubiertas y `R0004_C0016` necesita unos 43,329 m
proyectados adicionales al este.

Con F2, ocho candidatos están cubiertos y
`MADP_MADRID_PILOT_GRID_V1_GA467049559FD_S050_L050_R0004_C0016` requiere margen
adicional al este.

## Límites para F4.1b-B

Antes de materializar imágenes reales deben adquirirse una fuente con margen y
los recursos de un renderizador y estilo con versiones, hashes y condiciones de
uso verificadas. D007, D013 y D016 permanecen abiertas; el contrato corregido no
genera evidencia de compatibilidad visual, transferencia zero-shot ni permiso
de redistribución.
