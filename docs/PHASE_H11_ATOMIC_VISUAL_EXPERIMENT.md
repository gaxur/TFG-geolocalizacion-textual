# Preparación del experimento visual atómico H11

## Estado

El experimento usa la descripción original española de H11, la galería
`madrid-50m` y sus diez candidatos CrossText2Loc congelados. H11 es desarrollo y
su coordenada de enlace tiene incertidumbre desconocida; no constituye una
evaluación independiente ni Ground Truth oficial F5.4.

La preparación, selección de fotografías, claims, inferencia, agregación y
reranking no abren la referencia H11. Solo
`scripts/evaluate_h11_visual_reranking.py` contiene y utiliza esa coordenada.

## Anotación humana previa

La validación del contrato atómico utiliza la fixture ya preparada de H12, H14,
H16 y H19:

```text
results/generated/mapillary/visual-reranking-development-v1/atomic-annotations.html
```

Contiene 60 pares claim-imagen. Para cada fila:

1. seleccionar `supported`, `contradicted` o `unverifiable`;
2. escribir una explicación breve;
3. marcar `Revisada`;
4. exportar cuando las 60 filas estén completas.

La ausencia o una vista parcial se marca `unverifiable`. `contradicted` exige
una incompatibilidad visible. Guardar el resultado exportado como:

```text
results/generated/mapillary/visual-reranking-development-v1/atomic-annotations.json
```

Validación posterior:

```bash
python scripts/validate_visual_atomic_annotations.py \
  --annotations results/generated/mapillary/visual-reranking-development-v1/atomic-annotations.json \
  --fixture results/generated/mapillary/visual-reranking-development-v1/atomic-development-fixture.json
```

El HTML comprueba cobertura antes de exportar y el comando aplica además el
schema `visual_atomic_human_annotations.schema.json` y los IDs exactos.

## Fixture H11

Artefacto:

```text
results/generated/mapillary/h11-visual-development-v1/fixture.json
```

Identidad:

```text
h11-visual-fixture-sha256-f020c73e5bfdb43f9486bf4797510cd92a053465231833428b15690bb8daf520
```

La selección se construyó desde `rankings.json`, `plan.json` e inventario
Mapillary. No abrió `config/madrid_h11_h25_independent.json` ni ninguna
evaluación. Conserva:

- 10 candidatos, scores coseno, rangos y coordenadas de centro;
- 48 asociaciones candidato-imagen;
- 44 assets únicos;
- hasta cinco vistas por candidato; el rango 9 dispone de tres;
- posición, orientación, secuencia, fecha y distancia de cámara;
- `orientation_comparable=false` para todas las vistas.

El compilador produjo 12 claims, incluidos teatro y carteles publicitarios. Deben
revisarse en:

```text
results/generated/mapillary/h11-visual-development-v1/review-claims.html
```

Se deben aprobar solo claims atómicos, literales y visualmente comprobables. Las
relaciones `enfrente`, izquierda y derecha deben rechazarse en esta fixture
porque no existe orientación comparable. Guardar la exportación como:

```text
results/generated/mapillary/h11-visual-development-v1/reviewed-claims.json
```

El ejecutor comprueba que los 12 claims tengan exactamente una decisión y que
ninguno haya sido modificado.

## Fotografías H11

Manifest:

```text
results/generated/mapillary/h11-visual-development-v1/asset-manifest.json
```

Resultado:

| Medida | Valor |
|---|---:|
| Assets únicos | 44 |
| Reutilizados por hash | 1 |
| Descargados nuevos | 43 |
| Fallos | 0 |
| Bytes totales de assets | 5.579.316 B |

El asset `2857005767845410` se reutilizó desde el piloto anterior. No se duplicó
el JPEG; el manifest H11 conserva una ruta relativa y el hash. Las 43 miniaturas
nuevas se descargaron mediante API oficial, con autor, licencia CC BY-SA 4.0,
atribución, URL, dimensiones, tamaño y SHA-256.

## Ejecución VLM

No ejecutar hasta completar y validar las anotaciones atómicas y la revisión de
claims H11. Después:

```bash
python scripts/run_h11_atomic_vlm.py \
  --fixture results/generated/mapillary/h11-visual-development-v1/fixture.json \
  --assets results/generated/mapillary/h11-visual-development-v1/asset-manifest.json \
  --reviewed-claims results/generated/mapillary/h11-visual-development-v1/reviewed-claims.json \
  --model-path /home/dataai/models/hf/Qwen3-VL-2B-Instruct-89644892e4d8 \
  --output results/generated/mapillary/h11-visual-development-v1/atomic-run.json
```

El ejecutor carga Qwen3-VL-2B una vez, no usa GT, no envía rango, score o
coordenadas al modelo, no repara JSON y conserva todos los fallos. Las relaciones
egocéntricas no comparables se registran como abstención de política sin llamar
al VLM.

## Agregación y ranking separado

Primero comprobar el modo neutral, que debe conservar el orden:

```bash
python scripts/build_h11_visual_reranking.py \
  --fixture results/generated/mapillary/h11-visual-development-v1/fixture.json \
  --run results/generated/mapillary/h11-visual-development-v1/atomic-run.json \
  --output results/generated/mapillary/h11-visual-development-v1/reranking-disabled.json
```

Una configuración experimental explícita se ejecutaría, por ejemplo, con:

```bash
python scripts/build_h11_visual_reranking.py \
  --fixture results/generated/mapillary/h11-visual-development-v1/fixture.json \
  --run results/generated/mapillary/h11-visual-development-v1/atomic-run.json \
  --enable --lambda-pos VALOR --lambda-neg VALOR \
  --output results/generated/mapillary/h11-visual-development-v1/reranking-lambda.json
```

Los valores no deben elegirse mirando la distancia H11 antes de congelar el
ranking. Cada configuración probada debe conservarse, incluidos empeoramientos.

## Evaluación GT aislada

Solo después de congelar el ranking:

```bash
python scripts/evaluate_h11_visual_reranking.py \
  --fixture results/generated/mapillary/h11-visual-development-v1/fixture.json \
  --reranking results/generated/mapillary/h11-visual-development-v1/reranking-lambda.json \
  --output results/generated/mapillary/h11-visual-development-v1/evaluation-lambda.json
```

El evaluador calcula Top-1 original/experimental, distancias, delta, candidato
más cercano dentro del Top-10, invariancia del conjunto y evidencias responsables
del cambio. Rechaza cualquier ranking que cambie los diez IDs o contenga GT.

## Limitaciones

- H11 ya es desarrollo y no puede demostrar generalización.
- La referencia es una coordenada de enlace con incertidumbre desconocida.
- La proximidad de cámara no acredita visibilidad desde el candidato.
- No existe orientación corporal comparable.
- No se ha ejecutado aún Qwen3-VL sobre H11 ni se ha medido mejora.
- No se ha integrado nada en el MVP.
