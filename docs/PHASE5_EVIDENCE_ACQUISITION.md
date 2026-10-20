# F5.5: adquisición de evidencias y preparación de Ground Truth

## Alcance y estado

F5.5 implementa dos vías complementarias:

1. inventario reproducible de fotografías Panoramax dentro de D004;
2. plantillas e importación estricta de futuras observaciones `human_in_situ`.

No ejecuta CrossText2Loc, Qwen, prefiltrado ni reranking. Ningún registro se
aprueba automáticamente como GT. F5.4 conserva sus criterios científicos sin
cambios.

## Fuentes auditadas

| Fuente | Cobertura observada en D004 | Coordenada/orientación | Licencia | Decisión |
|---|---:|---|---|---|
| Panoramax | 10 items, 2 colecciones | Cámara; azimut en 10; precisión en 6 | CC BY-SA 4.0 por item | Implementada como inventario y cola pending |
| Wikimedia Commons | 4.226 files geolocalizados; 4.121 `type=camera` | Cámara si usa `Location`; heading ocasional | Por archivo | Fuente suplementaria; no importación automática |
| Mapillary | No inventariable sin token | Original/computed geometry y compass angle | CC BY-SA 4.0 declarada | Bloqueada por credenciales y términos operativos pendientes |
| KartaView | Respuesta vacía en radios 1 km y 2 km | Cámara, metadata variable | CC BY-SA 4.0 en términos antiguos | No viable actualmente |
| Fotografías propias | Pendiente de recogida | Posición y orientación controladas | Control del proyecto | Vía recomendada para GT definitivo |

Wikimedia Commons confirma que `{{Location}}` representa el lugar desde el que se
capturó la imagen, distinto de `{{Object location}}`. Sin embargo, sus coordenadas
comunitarias no incluyen siempre precisión ni validación independiente; por ello
no se convierten automáticamente en GT F5.4.

## Snapshot Panoramax real

Endpoint consultado:

```text
https://api.panoramax.xyz/api/search?bbox=-3.709,40.412,-3.699,40.420&limit=1000
```

Resultado observado:

```text
items: 10
colecciones: 2
con precisión horizontal: 6
sin precisión horizontal: 4
```

El snapshot conserva los bytes originales, SHA-256, URL completa, fecha UTC,
metadatos STAC, coordenada, colección, productor, licencia, azimut, cámara,
assets y asignaciones a ambos catálogos. La API respondió `application/json` con
una lista `features`, aunque sin `type: FeatureCollection`; el parser admite esa
forma observada sin alterar el raw.

```text
inventory_id:
f55-panoramax-inventory-sha256-0664a7bdcb06c84d46dc81b03f8ea9f468da2bab7ac695b3f7b9ce523ca19e89

raw response: 79.043 bytes
raw SHA-256: 67882b891ac6a6523ea93ba1d8a3e99a047b4cbf7a4c6354a87483b7187b2d1a
snapshot local total: 456 KiB
```

Los artefactos están fuera de Git:

```text
results/generated/f5/f55/panoramax/<inventory_id>/
├── raw-response.geojson
├── inventory.json
├── review-queue.json
├── review.html
└── assets/
```

Si la API falla, el CLI crea `failure-<UTC>.json` y no publica un snapshot
parcial. `--raw-response` permite reanudar con los mismos bytes, exigiendo
`--retrieved-at-utc` para no inventar provenance.

Una primera ejecución detectó después de publicar un aliasing entre assets de
inventario y cola: adjuntar hashes mutaba el inventario ya identificado. El
directorio se conservó sin sobrescribir, se corrigió mediante copia profunda y el
snapshot v2 anterior se revalidó completo. No debe utilizarse el intento con ID
`f55-panoramax-inventory-sha256-222688...`.

## Análisis geométrico

Se reutiliza `assign_reference()`; no se busca el centroide más próximo ni se
infiere precisión desde decimales.

| Galería | Estado | Items |
|---|---|---:|
| 25 m | `accuracy_insufficient` | 6 |
| 25 m | `accuracy_unavailable` | 4 |
| 50 m | `assigned` | 1 |
| 50 m | `accuracy_insufficient` | 3 |
| 50 m | `outside_catalog_coverage` | 2 |
| 50 m | `accuracy_unavailable` | 4 |

Así, ninguna captura permite Recall exacto a 25 m y solo una permite Recall
exacto a 50 m. Las demás podrían aportar error Haversine tras validación humana,
pero no se relajan los bordes ni la incertidumbre para aumentar la muestra.

`accuracy_unavailable` es un estado propio del inventario F5.5, anterior a F5.4:
indica que Panoramax no declaró precisión y por ello no se invocó una asignación
con precisión inventada.

## Selección piloto

La selección usa *farthest-point sampling* en EPSG:25830:

- semilla determinista: item más al norte y, después, al oeste;
- siguiente item: máxima distancia mínima a los ya seleccionados;
- desempate por `item_id`;
- máximo tres items por colección mientras exista alternativa;
- sin imágenes, OSM, rankings ni resultados del modelo.

Items seleccionados:

| Orden | Item | Colección | 25 m | 50 m |
|---:|---|---|---|---|
| 1 | `fdf10c50-11ee-4f43-af3f-5704f8fed2a1` | `a7cf...` | accuracy insufficient | accuracy insufficient |
| 2 | `091933c1-c0a1-4132-b0f6-54082712fdff` | `14ea...` | accuracy insufficient | outside coverage |
| 3 | `d766c3b3-875a-4442-8f0b-56b0f26d49bf` | `a7cf...` | accuracy unavailable | accuracy unavailable |
| 4 | `a36f42ac-816c-4de1-8f70-3f88bf1fb80b` | `a7cf...` | accuracy unavailable | accuracy unavailable |
| 5 | `08b1f259-52a8-4c86-814e-46f99bc85dc7` | `14ea...` | accuracy insufficient | assigned |

Se descargaron cinco thumbnails, no SD/HD. Cada asset conserva URL, timestamp,
tamaño, media type y SHA-256. Los ficheros son decodificables, pero la revisión
del contenido visual debe realizarla una persona mediante `review.html`.

Estado actual:

```text
pending: 5
approved: 0
rejected: 0
```

## Revisión humana Panoramax

El revisor abre `review.html` sin conexión y edita una copia de
`review-queue.json`. Para aprobar debe declarar:

- identidad del revisor y fecha UTC;
- licencia comprobada;
- posición de cámara revisada;
- correspondencia descripción/evidencia;
- descripción original humana en español;
- razones de aceptación;
- asset descargado con hash válido;
- si usa el azimut, incertidumbre angular explícita.

El azimut de cámara no equivale automáticamente a orientación corporal. No se
deben añadir objetos desde OSM ni consultar rankings. Una imagen insuficiente se
rechaza o permanece pendiente; no se completa con Qwen.

## Recogida propia `human_in_situ`

Plantilla:
[`config/madrid_f55_field_observation_template.json`](../config/madrid_f55_field_observation_template.json).

Cada registro conserva:

- posición medida del observador;
- múltiples lecturas GNSS originales;
- precisión horizontal;
- timestamp UTC y dispositivo;
- fotografías y registros con rutas relativas y SHA-256;
- orientación enlazada a evidencia cuando se usa;
- descripción redactada in situ;
- política de consentimiento/datos;
- revisión independiente y limitaciones.

El importador rechaza registros aprobados si falta cualquiera de esos campos,
si un hash no coincide o si la posición procede de un centro de celda. Solo
`approved` se convierte en F4.3 `human_in_situ` y sidecar F5.4; `pending` y
`rejected` se contabilizan pero no se importan.

## Comandos

Adquisición real limitada:

```bash
.venv-geo/bin/python scripts/acquire_f55_panoramax.py \
  --output-root results/generated/f5/f55/panoramax \
  --review-limit 5 \
  --asset-role thumb
```

Reanudación desde raw:

```bash
.venv-geo/bin/python scripts/acquire_f55_panoramax.py \
  --raw-response <raw-response.geojson> \
  --retrieved-at-utc <timestamp-original-Z> \
  --output-root results/generated/f5/f55/panoramax
```

Importar registros propios ya aprobados:

```bash
.venv-geo/bin/python scripts/import_f55_approved.py \
  --field-record <registro-aprobado-1.json> \
  --field-record <registro-aprobado-2.json> \
  --evidence-root <directorio-evidencias> \
  --output-dir results/generated/f5/f55/imported-field
```

Importar una cola Panoramax después de revisión:

```bash
.venv-geo/bin/python scripts/import_f55_approved.py \
  --panoramax-review <review-queue-revisada.json> \
  --evidence-root <directorio-del-snapshot> \
  --output-dir results/generated/f5/f55/imported-panoramax
```

## Flujo posterior

Cuando existan observaciones aprobadas:

1. validar F4.3 y F5.4;
2. congelar dataset y particiones;
3. generar/revisar cinco variantes;
4. ejecutar CrossText2Loc en 25 m y 50 m;
5. calcular Recall cuando haya celda inequívoca y Haversine/GeoRecall cuando haya GT geográfico evaluable;
6. comparar precisión y latencia por variante;
7. seleccionar provisionalmente con development;
8. confirmar con ubicaciones de evaluación independientes.

F5.5 no ejecutó ninguno de estos pasos porque hay cero observaciones aprobadas.

## Limitaciones y siguiente acción

- La fuente Panoramax es dinámica; el snapshot local preserva los bytes consumidos.
- CC BY-SA 4.0 exige atribución y puede condicionar derivados publicados.
- Cuatro items carecen de precisión horizontal.
- La metadata de cámara necesita revisión humana independiente.
- Los thumbnails pueden no mostrar contexto suficiente; se puede descargar SD de un item concreto si el revisor lo justifica, sin usar HD por defecto.
- Dos colecciones no proporcionan todavía 20-30 ubicaciones independientes.

La siguiente acción necesaria es revisar manualmente los cinco thumbnails y,
paralelamente, realizar cinco capturas propias con GNSS suficientemente preciso.
