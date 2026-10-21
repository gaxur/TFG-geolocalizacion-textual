# F5.6: conjunto documental Street View y migración desde Panoramax

## Estado

F5.6 registró cuatro capturas manuales locales de Google Street View como
evidencias documentales. Es un antecedente histórico de F5.7, sustituido para la
experimentación vigente por H01–H10 en F5.9. No son observaciones
`human_in_situ`, sus coordenadas proceden del enlace suministrado y la
incertidumbre posicional es desconocida.

```text
dataset_id:
f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a
```

Resultado:

| Estado | Cantidad |
|---|---:|
| Capturas locales presentes | 0; bytes retirados tras F5.9 |
| Dentro de D004 por coordenada de enlace | 4 |
| Excluidas antes del dataset | 1 (`SV-02`) |
| Revisión formal pendiente | 4 |
| Recall exacto elegible | 0 |
| GT oficial aprobado | 0 |

F5.6 no ejecutó modelos. F5.7 reutilizó posteriormente el dataset materializado y
sus textos, sin necesitar las imágenes durante Qwen, retrieval o evaluación.

## Archivos y política Git

Las capturas estuvieron históricamente en:

```text
data/streetview/SV-01.png ... SV-04.png  # retiradas
```

Los cuatro bytes locales se eliminaron después de completar H01–H10: ya no eran
necesarios para el flujo vigente y su conservación aumentaba el riesgo asociado
a contenido no abierto. El dataset histórico conserva rutas lógicas, dimensiones,
tamaño y SHA-256 para interpretar F5.7, pero esos hashes ya no pueden revalidarse
sin volver a aportar las capturas por una vía autorizada. No se copiaron ni
publicaron bytes.

Hashes:

| Captura | SHA-256 |
|---|---|
| SV-01 | `f16a87c86932bece5a5155a5c117e36abcdfaeed737ad5081662adff86d069b0` |
| SV-02 (antes SV-03) | `1d6c61ee757885f0e66aefaba93d981c7fc0afe934723277be612afde577d3c5` |
| SV-03 (antes SV-04) | `85f7fbc2fd017a7bb8ee4b315e9815aef5acbe89ade6f48750583420c8f9d08a` |
| SV-04 (antes SV-05) | `fad0b7fdfac37803c369c9a4f494c03828574944f57019ee87936bc633e6005b` |

## Referencias geográficas

Se distinguen:

- `link_coordinate`: coordenada embebida en la URL suministrada;
- posición de cámara verificada: **no disponible**;
- incertidumbre: `unknown`;
- asignación de punto: resultado geométrico exploratorio sin precisión;
- GT exacto: no validado.

| Captura | D004 | 25 m por punto | 50 m por punto | Recall exacto |
|---|---|---|---|---|
| SV-01 | dentro | assigned | assigned | no: incertidumbre desconocida |
| SV-02 (antes SV-03) | dentro | assigned | assigned | no: incertidumbre desconocida |
| SV-03 (antes SV-04) | dentro | assigned | assigned | no: incertidumbre desconocida |
| SV-04 (antes SV-05) | dentro | assigned | assigned | no: incertidumbre desconocida |

El parámetro `650a`/similar de las URLs no se interpreta como precisión. SV-02 se
retiró del dataset activo y su PNG local original se eliminó: estaba 16,22 m al norte de
D004, 29,29 m al norte de la cobertura 25 m y 54,33 m al norte de la cobertura
50 m. URL, panorama y coordenadas permanecen como `SV-EXCLUDED-01` con
`legacy_observation_id: SV-02`. Las antiguas SV-03/04/05 se renumeraron como
SV-02/03/04 y conservan `legacy_observation_id`.

## Orientación y descripciones

Se conservan panorama ID, URL completa, heading y pitch. Heading se interpreta
solo como dirección declarada de la cámara en la URL; no se convierte en
orientación corporal.

Las cuatro descripciones históricas están congeladas antes de variantes y no
contienen coordenadas ni IDs. La correspondencia visual, atributos y relaciones
egocéntricas siguen `pending` de revisión formal. El antiguo HTML local se retiró
porque enlazaba capturas ya eliminadas. Se conserva `dataset.json`, que es la
entrada trazable usada por F5.7.

```text
results/generated/f5/f56/<dataset_id>/dataset.json
```

El responsable actualizó los detalles de las cuatro descripciones y se alinearon
las listas `visible_evidence` con esos textos. Los hashes, panorama IDs,
coordenadas y enlaces no cambiaron; esta comprobación garantiza correspondencia
documental tras la renumeración, no aprobación visual automática.

El entorno automatizado valida forma, fugas, hashes y orientación declarada, pero
no sustituyó la inspección humana del contenido PNG. No se registra
`image_correspondence_verified=true` sin esa revisión.

## Métricas permitidas

Actualmente:

- Recall@K oficial: no disponible;
- precisión geográfica oficial: no disponible;
- error Haversine exploratorio: se podrá calcular frente a
  `approximate_link_coordinate` para las cuatro dentro de D004, etiquetado con
  incertidumbre desconocida;
- estabilidad de rankings: posible tras revisión, pero no equivale a precisión.

`exploratory-reference.json` formaliza esta separación y declara
`official_metrics_allowed=false`.

## Comparación de cinco variantes

Precondiciones no cumplidas:

1. las cuatro descripciones siguen pendientes de revisión formal;
2. no hay celda GT validada por incertidumbre conocida;
3. solo cuatro referencias de enlace están dentro de D004.

Por ello F5.6 no ejecutó F5.2 ni CrossText2Loc:

```text
variantes generadas: 0
variantes aprobadas: 0
rankings: 0
observaciones oficialmente evaluables: 0
```

`execution-gate.json` materializa estas precondiciones y bloquea el paso a
variantes/rankings mientras haya descripciones pendientes. No es un lanzador de
modelos.

Tras revisión formal podrá generarse un informe exploratorio de 4 × 5 × 2 = 40
rankings, pero sin Recall exacto y sin afirmar superioridad con una muestra tan
pequeña.

## Limpieza Panoramax

Se eliminan del flujo activo:

- adquisición y parser Panoramax;
- schemas de inventario/revisión Panoramax;
- decisiones y configuraciones Panoramax;
- scripts de materialización visual Panoramax;
- tests y fixtures Panoramax;
- documentación operativa F5.5/F5.5b.

Se conserva:

- historial Git de F5.5/F5.5b;
- artefactos locales ignorados, sin borrado masivo;
- F5.4;
- plantilla/importador genérico de observaciones propias, refactorizado fuera del
  módulo Panoramax;
- benchmark `synthetic_osm` F5.5c y sus tests.

## Reconstrucción histórica opcional

```bash
.venv-geo/bin/python scripts/build_f56_streetview_documentary.py \
  --image-root <directorio-autorizado-con-SV-01.png-a-SV-04.png> \
  --output-root results/generated/f5/f56
```

Este comando ya no forma parte del flujo activo y falla si no se proporcionan
explícitamente las cuatro imágenes privadas. Los tests usan PNG sintéticos
temporales y no recrean evidencia visual.

> Actualización posterior: F5.7 ejecutó esta vía como excepción provisional
> expresa D074, tras controles automáticos y antes de revisión humana. F5.6
> conserva sus estados `pending`; los resultados aproximados se documentan en
> [PHASE57_EXPERIMENTAL_EVALUATION.md](PHASE57_EXPERIMENTAL_EVALUATION.md) y no
> son métricas oficiales F5.4. F5.9 H01–H10 sustituye esta vía como conjunto
> humano exploratorio vigente; no reinterpreta retrospectivamente F5.7.
