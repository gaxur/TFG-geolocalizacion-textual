# Pesos locales (no versionados)

Git solo conserva este README; los pesos permanecen locales. El evaluador
oficial de CVG-Text usa por defecto su propio directorio
`external/CVG-Text/checkpoints/`, mientras que el runtime propio del MVP usa la
ruta configurable bajo `checkpoints/CrossText2Loc/`.

El checkpoint congelado utilizado por F4 y el MVP es
`long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth`, publicado por
[los autores](https://huggingface.co/CVG-Text/CrossText2Loc). Su SHA-256 validado
es `d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d`.
El repositorio no lo descarga automáticamente ni lo versiona.

`compose.mvp.yaml` monta el proyecto y la caché CLIP en solo lectura. Antes de
desplegar deben existir:

```text
checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
$HOME/.cache/clip/ViT-L-14-336px.pt
```

Para otra ubicación de la caché CLIP se utiliza `MVP_CLIP_CACHE_DIR`. Consultar
[MVP.md](../docs/MVP.md); nunca incluir estos archivos en
una imagen o commit.

Resumen de nombres obligatorios:

| Recurso | Nombre y ubicación |
|---|---|
| Checkpoint | `checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth` |
| CLIP | `${MVP_CLIP_CACHE_DIR:-$HOME/.cache/clip}/ViT-L-14-336px.pt` |

No renombrar el checkpoint sin actualizar deliberadamente
`config/madrid_f46_retriever.json`. El wrapper no busca pesos alternativos.
