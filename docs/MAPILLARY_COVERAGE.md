# Medición de cobertura Mapillary en D004

## Estado y límite de esta fase

La implementación mide cobertura **espacial** de metadatos Mapillary sobre las
galerías de Madrid y los Top-10 H11-H25. No descarga fotografías, no ejecuta un
VLM, no reordena candidatos y no utiliza coordenadas de referencia.

Mapillary permanece **CONDICIONADO** hasta revisar manualmente los términos que
se presenten al registrar la aplicación y medir la cobertura real. A fecha de
consulta, 22 de octubre de 2026, no se ha registrado una aplicación desde este
repositorio, no existe un token versionado y no se han realizado solicitudes.

> **Punto de parada obligatorio:** no ejecutar la adquisición hasta que la
> persona responsable autorice expresamente registrar la aplicación, aceptar sus
> condiciones y realizar las primeras solicitudes controladas.

Fuentes oficiales consultadas:

- [licencia CC BY-SA de las imágenes](https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data);
- [acceso mediante Mapillary API](https://help.mapillary.com/hc/en-us/articles/360010234680-Accessing-imagery-and-data-through-the-Mapillary-API);
- [SDK oficial de Mapillary API v4](https://github.com/mapillary/mapillary-python-sdk);
- [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

## Componentes

| Componente | Función |
|---|---|
| `src/tfg_phase0/mapillary_coverage.py` | Cliente API v4, normalización, hashes, cobertura y validadores |
| `scripts/acquire_mapillary_d004_inventory.py` | Único comando con red; exige token y adquiere solo metadatos D004 |
| `scripts/evaluate_mapillary_d004_coverage.py` | Evaluación local sobre inventario congelado; no usa red ni GT |
| `tests/test_mapillary_coverage.py` | Respuestas simuladas, errores, distancias, conteos e integridad |

El cliente usa `https://graph.mapillary.com/images`, autenticación en cabecera,
paginación de la respuesta, reintentos acotados para HTTP 429/5xx y un intervalo
configurable entre páginas. El token no forma parte de URL, logs ni artefactos.

## Cobertura contractual

La evaluación exige exactamente:

- 1.115 candidatos de `madrid-25m`;
- 253 candidatos de `madrid-50m`;
- las 15 filas H11-H25 de `en_cartographic` y `madrid-50m`;
- 150 posiciones Top-10 y 88 `candidate_id` únicos.

Los rankings se leen de
`results/generated/f5/h11-h25-independent/rankings.json`. No se abre
`evaluation.json` ni el dataset con referencias. La adquisición recibe solo la
bbox D004, nunca candidatos, consultas o GT.

## Configuración manual pendiente de autorización

Cuando se autorice continuar:

1. Acceder manualmente a Mapillary con una cuenta controlada por el proyecto.
2. Registrar una aplicación específica desde el
   [panel de desarrolladores](https://www.mapillary.com/dashboard/developers).
3. Revisar y conservar la fecha y versión de los términos mostrados.
4. Confirmar que el acceso no solicita facturación y anotar los límites
   aplicables a la aplicación.
5. Obtener un `client access token`.
6. Crear localmente `.env` y añadir:

   ```text
   MAPILLARY_ACCESS_TOKEN=valor_local_no_versionado
   ```

7. Cargar la variable en la sesión sin mostrarla en terminal ni historial.
8. Verificar antes de usarla:

   ```bash
   git check-ignore -v .env
   ```

La raíz `.gitignore` ya excluye `.env` y `.env.*`. No incluir el token en
capturas, comandos compartidos, informes, manifests o incidencias.

## Adquisición controlada

Tras la autorización explícita y con la variable ya presente en el entorno:

```bash
python scripts/acquire_mapillary_d004_inventory.py \
  --output results/generated/mapillary/d004/inventory.json
```

El comando solicita únicamente estos campos:

```text
id, geometry, computed_geometry, captured_at,
compass_angle, computed_compass_angle, sequence,
camera_type, width, height, quality_score
```

No solicita URLs de thumbnail y no descarga imágenes. Sin token termina antes de
abrir una conexión. Los límites conservadores iniciales son 2.000 registros por
página, 100 páginas máximas, 0,25 s entre páginas y tres reintentos.

## Evaluación local

Una vez congelado el inventario:

```bash
python scripts/evaluate_mapillary_d004_coverage.py \
  --inventory results/generated/mapillary/d004/inventory.json \
  --output-root results/generated/mapillary/d004/coverage
```

Las rutas por defecto verificadas son:

```text
data/processed/catalog/manifest-25m.json
data/processed/catalog/manifest-50m.json
results/generated/f5/h11-h25-independent/rankings.json
```

## Artefactos

La adquisición produce `inventory.json`, con consulta, fecha UTC, licencia,
metadatos normalizados e identidad SHA-256 derivada del contenido.

La evaluación produce:

| Archivo | Contenido |
|---|---|
| `coverage.json` | Filas por candidato y resúmenes a 10, 25, 50 y 100 m |
| `report.md` | Tabla legible por galería y consulta H11-H25 |
| `manifest.json` | Rutas, tamaños y SHA-256 de todos los inputs y outputs |

Por candidato se registra distancia a la cámara más próxima, número de imágenes,
posiciones de cámara deduplicadas a seis decimales, secuencias, bins angulares de
45 grados y antigüedad disponible. Estos datos miden cobertura espacial. La
utilidad visual permanece `not_measured_metadata_only` hasta revisar imágenes en
otra fase autorizada.

## Pruebas sin red

```bash
python -m unittest tests.test_mapillary_coverage -v
```

Las pruebas simulan paginación, HTTP 429 y 400, ausencia de token, coordenadas
inválidas, deduplicación, distancias, radios, orientación, conteos contractuales,
hashes y manipulación de artefactos. No necesitan cuenta ni acceso a Mapillary.

## Criterio de avance

Solo se propondrá descargar una fixture de imágenes si:

1. los términos de aplicación son compatibles con adquisición, conservación e
   inferencia local mediante VLM;
2. no se exige facturación incompatible con coste cero;
3. la medición muestra cobertura espacial suficiente en `madrid-50m` y los 88
   candidatos H11-H25;
4. una revisión posterior demuestra utilidad visual, no solo proximidad.

## Justificación y auditoría del margen espacial de adquisición

### Región de estudio frente a región de fotografías

D004 continúa siendo la región de estudio y mantiene la bbox WGS84:

```text
norte 40.4200, sur 40.4120, este -3.6990, oeste -3.7090
```

El margen no crea candidatos, no amplía las galerías y no modifica imágenes OSM,
embeddings ni rankings. Solo permite adquirir cámaras exteriores que estén a una
distancia menor o igual que el radio analizado de un candidato interior.

El inventario original consultó exactamente D004. De los 88 candidatos únicos
Top-10, 19 tienen el centro a menos de 100 m del borde. Su vecindad de 100 m no
queda contenida en la bbox original; por tanto, la medición podía truncarse.

### Método y suficiencia geométrica

El valor 100 m coincide con el mayor radio de cobertura del protocolo
`10/25/50/100 m`. La expansión se calcula con las transformaciones propias
WGS84↔EPSG:25830 de `src/tfg_phase0/crs.py`:

1. muestrear el perímetro de D004;
2. obtener su envolvente en EPSG:25830;
3. expandir esa envolvente 100 m en los cuatro lados;
4. transformar de vuelta todo el perímetro expandido;
5. usar su envolvente WGS84 con un épsilon exterior.

La bbox resultante fue:

```text
norte 40.42096885773377
sur   40.411031034236295
este  -3.6977293744163324
oeste -3.7102721264497216
```

La comprobación automática muestrea el perímetro original y 72 direcciones de
un círculo de 100 m alrededor de cada punto. Todos los puntos quedan dentro de
la bbox consultada, incluidas las esquinas. Por ello, 100 m es suficiente para
el objetivo definido; no fue necesario aumentar el margen.

### Completitud de la API y partición

La primera consulta monolítica ampliada devolvió 1.857 imágenes, pero compartía
solo 347 IDs con las 1.655 del inventario original. Además reducía algunas
coberturas cortas, comportamiento incompatible con un superconjunto espacial.
No se interpretó como desaparición real de imágenes.

La solución mínima fue dividir la bbox ampliada en una cuadrícula 2×2, consultar
las cuatro celdas y unir por `image_id`. Las celdas devolvieron 1.286, 1.363, 938
y 1.750 imágenes; ninguna alcanzó el límite de 2.000 y ninguna anunció una página
adicional. La unión congelada contiene 5.337 IDs. El inventario original se
conserva intacto y el ampliado está en:

```text
results/generated/mapillary/d004-buffer100m/inventory.json
```

### Cobertura antes y después

| Conjunto | Radio | Original | Expandido 2×2 |
|---|---:|---:|---:|
| `madrid-25m` | 10 m | 88/1.115 (7,9 %) | 244/1.115 (21,9 %) |
| `madrid-25m` | 25 m | 232/1.115 (20,8 %) | 552/1.115 (49,5 %) |
| `madrid-25m` | 50 m | 492/1.115 (44,1 %) | 905/1.115 (81,2 %) |
| `madrid-25m` | 100 m | 897/1.115 (80,4 %) | 1.092/1.115 (97,9 %) |
| `madrid-50m` | 10 m | 17/253 (6,7 %) | 49/253 (19,4 %) |
| `madrid-50m` | 25 m | 52/253 (20,6 %) | 126/253 (49,8 %) |
| `madrid-50m` | 50 m | 108/253 (42,7 %) | 208/253 (82,2 %) |
| `madrid-50m` | 100 m | 198/253 (78,3 %) | 249/253 (98,4 %) |
| Top-10 únicos | 10 m | 4/88 (4,5 %) | 17/88 (19,3 %) |
| Top-10 únicos | 25 m | 18/88 (20,5 %) | 47/88 (53,4 %) |
| Top-10 únicos | 50 m | 37/88 (42,0 %) | 74/88 (84,1 %) |
| Top-10 únicos | 100 m | 71/88 (80,7 %) | 86/88 (97,7 %) |

Las diferencias combinan dos correcciones: cámaras exteriores al límite y una
consulta espacial más completa mediante partición. No son una mejora del modelo
ni demuestran visibilidad, encuadre o utilidad para Qwen3-VL.

## Piloto visual offline

La selección congelada usa diez candidatos Top-10 sin GT:

```text
3 con cámara <25 m
3 entre 25 y 50 m
2 entre 50 y 100 m
2 sin cámara hasta 100 m
```

El plan contiene 24 fotografías únicas, hasta tres por candidato cubierto. Los
artefactos están en `results/generated/mapillary/visual-pilot-v1/`. Inicialmente
las imágenes quedaron bloqueadas hasta la confirmación del titular. Tras
recibirla se descargaron 24/24 y se regeneró `report.html` con las vistas reales;
los dos controles permanecen como «sin evidencia visual disponible».

H11–H25 aporta únicamente el texto de `plan.json` y los Top-10 congelados de
`rankings.json`. El selector no abre `dataset.json`, `evaluation.json` ni el
informe final. Una validación recursiva aborta si recibe campos de referencia,
ground truth, distancia al GT, Recall, GeoRecall o etiquetas de acierto. El
descargador repite esa validación antes de acceder a Mapillary. Por tanto, cada
consulta visual conoce:

```text
query_id + descripción + candidate_id + coordenadas candidatas + baseline_rank
```

y no conoce:

```text
coordenada real + candidato correcto + distancia al GT + etiqueta de acierto
```

Preparación reproducible:

```bash
python scripts/prepare_mapillary_visual_pilot.py \
  --inventory results/generated/mapillary/d004-buffer100m/inventory.json \
  --coverage results/generated/mapillary/d004-buffer100m/coverage/coverage.json \
  --output-root results/generated/mapillary/visual-pilot-v1
```

Tras revisar y documentar los términos, la descarga controlada requerirá una
confirmación explícita:

```bash
python scripts/acquire_mapillary_pilot_images.py \
  --selection results/generated/mapillary/visual-pilot-v1/selection.json \
  --image-plan results/generated/mapillary/visual-pilot-v1/image-plan.json \
  --output-root results/generated/mapillary/visual-pilot-v1 \
  --max-downloads 30 \
  --confirm-terms-reviewed
```

El flag no sustituye la revisión contractual; únicamente evita una descarga
accidental. El modelo Qwen3-VL no se descarga ni ejecuta en esta fase.

### Confirmación contractual del piloto

La revisión del 23 de octubre de 2026 pudo verificar la licencia CC BY-SA y la
existencia de la API oficial, pero esta pasarela no pudo recuperar los términos
completos de `https://www.mapillary.com/terms` ni los términos de desarrollador
(HTTP 400). No se consideró ese silencio como permiso y el flag permaneció
bloqueado hasta la confirmación posterior del titular.

La persona titular de la aplicación debe entrar en el panel de Mapillary,
revisar los términos aplicables y confirmar expresamente:

```text
He revisado los términos aplicables a mi aplicación Mapillary y confirmo que
permiten descargar mediante la API estas 24 miniaturas de 1024 px, conservarlas
localmente para el TFG, inspeccionarlas/anotarlas y procesarlas posteriormente
con un Qwen3-VL de pesos fijos, sin entrenamiento ni publicación de un dataset.
No he identificado facturación ni una restricción adicional incompatible.
```

Si existe cualquier condición adicional, debe registrarse junto a esa
confirmación antes de ejecutar `acquire_mapillary_pilot_images.py`. No es
necesario revelar el token.

### Adquisición ejecutada

La persona titular proporcionó la confirmación expresa requerida el 23 de
octubre de 2026. Se ejecutó el descargador existente con límite 30 y se
obtuvieron las 24/24 miniaturas planificadas a 1.024 px, sin fallos. El total
almacenado es 2.802.298 bytes. Cada fila del manifest conserva creador, enlace de
perfil, enlace público a la imagen, atribución Mapillary, enlace CC BY-SA 4.0,
nota de modificación, resolución, tamaño y SHA-256.

```text
results/generated/mapillary/visual-pilot-v1/images/
results/generated/mapillary/visual-pilot-v1/photo-manifest.json
results/generated/mapillary/visual-pilot-v1/report.html
```

Las imágenes permanecen fuera de Git. La inspección visual manual continúa
pendiente porque el agente que ejecutó esta fase no dispone de entrada visual;
las anotaciones no se completaron de forma ficticia.

El HTML actualizado incluye controles por `image_id` y un botón para exportar
`annotations.json`. Tras revisar las 24 vistas, guardar el archivo exportado en
la raíz del piloto y generar el resumen:

```bash
python scripts/summarize_mapillary_visual_annotations.py \
  --annotations results/generated/mapillary/visual-pilot-v1/annotations.json \
  --photo-manifest results/generated/mapillary/visual-pilot-v1/photo-manifest.json \
  --output results/generated/mapillary/visual-pilot-v1/annotation-summary.json
```

El resumen solo publica porcentajes si todas las fotografías están realmente
marcadas `reviewed`; una plantilla pendiente no se contabiliza como
`unverifiable`.
