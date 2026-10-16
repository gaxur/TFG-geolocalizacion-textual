# Guía de uso de CrossText2Loc con Docker Compose

Esta guía describe el entorno utilizado para reproducir CrossText2Loc en la
NVIDIA GB10. No ejecuta entrenamiento ni evaluación automáticamente. Antes de
usar la GPU hay que comprobar `nvidia-smi` y respetar cualquier asignación o
proceso activo.

## Configuración validada

| Componente | Valor |
|---|---|
| Imagen | `crosstext2loc-gb10:ngc26.02` |
| Compose | `compose.cross-text2loc.yaml` |
| Base NVIDIA | `nvcr.io/nvidia/pytorch@sha256:8014e4ffc674ae9cc9aecad04b64b29c3d311ed738e54ac3042d2d45690d19e9` |
| PyTorch | `2.11.0a0+eb65b36914.nv26.02` |
| CUDA de PyTorch | `13.1` |
| CVG-Text | `6910d2747a94fbe985309bde60cd4732bcbbf50f` |
| OpenAI CLIP | `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1` |
| Modelo | `CLIP ViT-L/14@336`, FP32, contexto 300 |

Esta combinación constituye **REFERENCE ENVIRONMENT v1**. Durante los
experimentos baseline no se actualizarán automáticamente NGC, CUDA, PyTorch,
torchvision ni las dependencias. Un cambio relevante deberá crear una nueva
versión del entorno y conservar la trazabilidad de v1.

Todos los comandos se ejecutan desde la raíz:

```text
${HOME}/Projects/TFG_Marcos/TFG-geolocalizacion-textual
```

## Comprobar la imagen

```bash
docker image ls crosstext2loc-gb10
```

Debe aparecer la imagen `crosstext2loc-gb10` con tag `ngc26.02`. Para consultar
su ID y tamaño lógico:

```bash
docker image inspect crosstext2loc-gb10:ngc26.02 \
  --format '{{.Id}} {{.Size}}'
```

La imagen validada ocupaba aproximadamente 19,80 GiB lógicos.

## Levantar y entrar en el entorno

Primero comprobar que la GPU puede utilizarse:

```bash
nvidia-smi
```

Crear el contenedor y dejarlo ejecutándose en segundo plano:

```bash
docker compose -f compose.cross-text2loc.yaml up -d crosstext2loc
```

El contenedor permanece inactivo mediante `sleep infinity`: no importa PyTorch,
no carga el modelo y no inicializa CUDA. Para abrir un shell en él:

```bash
docker compose -f compose.cross-text2loc.yaml exec crosstext2loc bash
```

El shell se abre en:

```text
/workspace/project/external/CVG-Text
```

Dentro del contenedor se puede comprobar el entorno sin cargar el modelo:

```bash
python -c 'import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.get_device_name(0))'
```

La configuración Compose:

- expone la GPU con `gpus: all` y limita el proceso a la GPU visible `0`;
- deshabilita la red para evitar descargas accidentales;
- monta el proyecto completo en solo lectura;
- monta la caché CLIP del host en solo lectura;
- dirige las cachés de Hugging Face a `/tmp/huggingface`, que es temporal y
  escribible, para evitar el warning observado sin descargar ni persistir nada;
- permite escribir resultados manuales únicamente bajo
  `results/cross_text2loc_docker/manual/`;
- configura `safe.directory` solo dentro del contenedor para los comandos Git;
- permite gestionar el contenedor mediante `up`, `exec`, `stop`, `start` y
  `down`.

F4.6 añade un proceso Python residente sobre este mismo entorno. Mantener vivo
solo `sleep infinity` no mantiene el modelo: debe permanecer vivo el proceso que
contiene `CrossText2LocRetriever`. Véase
[la interfaz de retrieval](CROSSTEXT2LOC_RETRIEVAL_INTERFACE.md).

Compose resuelve `${HOME}/.cache/clip` contra el directorio personal del usuario
que ejecuta el comando, sin fijar en el archivo una ruta privada concreta.

En esta máquina `cuda:0` es el único dispositivo visible dentro del contenedor.
No debe interpretarse automáticamente como una regla válida para otra máquina o
una sesión gestionada por Slurm.

## Ejecutar un comando directo

Con el servicio levantado, este ejemplo inocuo muestra las versiones sin cargar
el checkpoint:

```bash
docker compose -f compose.cross-text2loc.yaml exec crosstext2loc \
  python -c 'import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.get_device_name(0))'
```

Para ejecutar otro script, sustituir solamente el comando `python -c ...`.
No debe ejecutarse `train.py`, `finetune.py` ni ningún flujo de entrenamiento.

## Comprobar el commit desde el contenedor

La configuración Compose resuelve de forma efímera la protección de propiedad
de Git. Esta comprobación debe devolver el commit fijado:

```bash
git rev-parse HEAD
```

Resultado esperado:

```text
6910d2747a94fbe985309bde60cd4732bcbbf50f
```

No se modifica `.git` ni la configuración persistente del host.

## Evaluación oficial reproducida

`evaluate.py` no ofrece una CLI independiente. La entrada oficial es
`zeroshot.py`, que carga el modelo y llama internamente a la evaluación de
`evaluate.py`.

Desde la raíz del proyecto, levantar primero el servicio:

```bash
docker compose -f compose.cross-text2loc.yaml up -d crosstext2loc
```

Comprobar la GPU visible dentro del contenedor:

```bash
docker compose -f compose.cross-text2loc.yaml exec crosstext2loc nvidia-smi
```

El comando completo desde el host que reproduce D5 es:

```bash
docker compose -f compose.cross-text2loc.yaml exec crosstext2loc \
  python zeroshot.py \
    --version NewYork-mixed \
    --img_type osm \
    --model CLIP-L/14@336 \
    --expand \
    --checkpoint long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

El comando equivalente si ya se está dentro del shell del contenedor es:

```bash
python zeroshot.py \
  --version NewYork-mixed \
  --img_type osm \
  --model CLIP-L/14@336 \
  --expand \
  --checkpoint long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

No se recomienda volver a ejecutarlo sin una autorización experimental expresa.
Procesa 1200 muestras con lote 4 y cuatro workers. El protocolo oficial usa la
coordenada ground truth para elegir los 100 candidatos geográficamente más
cercanos antes del ranking; no representa el futuro protocolo de Madrid.

Los CSV generados quedan persistidos en el host bajo:

```text
results/cross_text2loc_docker/manual/CLIP-L_14@336/
```

Consultar las métricas:

```bash
less results/cross_text2loc_docker/manual/CLIP-L_14@336/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth_metric.csv
```

Al terminar, detener y eliminar el contenedor de Compose:

```bash
docker compose -f compose.cross-text2loc.yaml down
```

Este `down` no elimina la imagen Docker ni los datos, checkpoint o resultados
montados desde el host.

## Ver contenedores

Contenedores activos:

```bash
docker ps
```

Contenedores activos y detenidos:

```bash
docker ps -a
```

## Eliminar completamente el contenedor y la imagen derivada

`docker compose down` elimina el contenedor; no se limita a detenerlo. Para
eliminar en una sola operación el contenedor del servicio, los contenedores
huérfanos del mismo proyecto Compose, su red y las imágenes usadas por el
servicio, ejecutar desde la raíz del proyecto:

```bash
docker compose -f compose.cross-text2loc.yaml down --rmi all --remove-orphans
```

Si la imagen derivada siguiera presente porque Docker no la considera parte del
proyecto Compose, eliminarla explícitamente:

```bash
docker image rm crosstext2loc-gb10:ngc26.02
```

Se puede comprobar que el contenedor y la imagen ya no existen con:

```bash
docker compose -f compose.cross-text2loc.yaml ps -a
docker image ls crosstext2loc-gb10
```

Si Docker indica que otro contenedor todavía utiliza la imagen, localizarlo
antes de eliminar nada:

```bash
docker ps -a --filter ancestor=crosstext2loc-gb10:ngc26.02
```

Tras confirmar que el contenedor encontrado pertenece a este entorno y que ya
no se necesita, eliminarlo y repetir el borrado de la imagen:

```bash
docker rm <nombre-o-id>
docker image rm crosstext2loc-gb10:ngc26.02
```

Esta operación no elimina los bind mounts del host: los resultados de
`results/cross_text2loc_docker/`, el clon `external/CVG-Text/`, el dataset, los
checkpoints y `${HOME}/.cache/clip` permanecen en disco. Tampoco elimina la
imagen base de NVIDIA, que puede estar compartida por otras imágenes. Para
consultar el espacio utilizado después de la limpieza:

```bash
docker system df
```

Esto limpia los recursos Docker del entorno, pero no garantiza que «no quede
rastro» de la ejecución: pueden permanecer los resultados montados en el host,
el historial del shell y registros del daemon o del sistema. Esos elementos no
deben borrarse automáticamente, especialmente si forman parte de la trazabilidad
experimental del TFG. No usar `docker compose down -v`, `docker system prune`,
`docker image prune -a` ni `docker volume prune`: no son necesarios para este
entorno y podrían eliminar recursos de otros proyectos.

## Persistencia

| Recurso | Ubicación | Persiste al salir |
|---|---|---|
| Dependencias Python | Imagen Docker | Sí, mientras exista la imagen |
| PyTorch y CUDA de usuario | Imagen Docker | Sí, mientras exista la imagen |
| Driver NVIDIA | Host | Sí; no pertenece al contenedor |
| CVG-Text | `external/CVG-Text/` del host | Sí |
| Dataset | `data/cvg_text/` del host | Sí |
| Checkpoint | `external/CVG-Text/checkpoints/` del host | Sí |
| Resultados manuales | `results/cross_text2loc_docker/manual/` | Sí |
| Dockerfile y Compose | `docker/` y `compose.cross-text2loc.yaml` | Sí |
| `/tmp` del contenedor | `tmpfs` efímero | No |
| Cambios internos no montados | Contenedor con filesystem read-only | No se pueden crear fuera de los mounts y `/tmp` |

Ejecutar `docker compose down` no elimina el dataset, checkpoint, repositorio ni
resultados, porque son archivos montados desde el host. El proyecto se monta en
solo lectura para evitar modificaciones accidentales.

## Uso diario

Levantar CrossText2Loc con GPU:

```bash
docker compose -f compose.cross-text2loc.yaml up -d crosstext2loc
```

Entrar en el shell:

```bash
docker compose -f compose.cross-text2loc.yaml exec crosstext2loc bash
```

Salir del shell sin detener el contenedor:

```bash
exit
```

Detenerlo y conservar el contenedor:

```bash
docker compose -f compose.cross-text2loc.yaml stop
```

Volver a iniciarlo:

```bash
docker compose -f compose.cross-text2loc.yaml start
```

Detener y eliminar el contenedor de Compose:

```bash
docker compose -f compose.cross-text2loc.yaml down
```
