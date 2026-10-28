# Revisión humana y visor H16/H23 Top-50

## Rutas canónicas

Revisión canónica:

`results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/h16-h23-top50-claims-review.json`

Historial de revisiones sustituidas:

`results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/history/`

Formulario:

`results/generated/mapillary/h16-h23-multicandidate-top50-v1/review-claims.html`

Visor fotográfico:

`results/generated/mapillary/h16-h23-multicandidate-top50-v1/photo-viewer.html`

## Revisar claims

Servir el repositorio:

```bash
python scripts/serve_annotation_forms.py --bind 127.0.0.1 --port 8765
```

Abrir:

```text
http://127.0.0.1:8765/results/generated/mapillary/h16-h23-multicandidate-top50-v1/review-claims.html
```

El formulario permite cargar un borrador JSON previo. El botón descarga siempre:

`h16-h23-top50-claims-review.json`

Una exportación con claims pendientes es un borrador válido, pero no abre el gate.
El formulario no guarda directamente en el repositorio: esto evita que una página
local sobrescriba silenciosamente la revisión canónica.

H16 contiene la discrepancia `retablo oscuro` frente a `dark choir`. El formulario
la muestra como advertencia. No se acepta automáticamente. Si se corrige el texto
inglés, debe crearse una nueva variante y una nueva versión de fixture, claims,
plan y protocolo; no se modifica el protocolo congelado.

## Importar la revisión

Suponiendo que el navegador guardó el JSON en `~/Descargas/`:

```bash
python scripts/import_h16_h23_claim_review.py \
  --exported "$HOME/Descargas/h16-h23-top50-claims-review.json" \
  --fixture results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json \
  --protocol config/h16_h23_top50_experiment.json \
  --canonical results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/h16-h23-top50-claims-review.json \
  --history-dir results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/history
```

El importador exige 27 decisiones humanas, IDs y claims exactos, variante
`en_cartographic`, fixture, protocolo y hashes correctos. Antes de reemplazar el
canónico copia su versión anterior en `reviews/history/` y después escribe de
forma atómica. Rechaza borradores incompletos, claims manipulados y revisiones de
otro protocolo.

## Validar y comprobar preflight

Validación completa:

```bash
python scripts/validate_h16_h23_claim_review.py \
  --review results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/h16-h23-top50-claims-review.json \
  --fixture results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json \
  --protocol config/h16_h23_top50_experiment.json \
  --require-complete
```

Preflight:

```bash
python scripts/preflight_h16_h23_experiment.py \
  --protocol config/h16_h23_top50_experiment.json \
  --fixture results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json \
  --plan results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json \
  --claim-review results/generated/mapillary/h16-h23-multicandidate-top50-v1/reviews/h16-h23-top50-claims-review.json \
  --authorization config/h16_h23_mapillary_authorization.template.json \
  --output results/generated/mapillary/h16-h23-multicandidate-top50-v1/preflight.json
```

La mera existencia del archivo no abre `claims_review`; el preflight ejecuta el
validador estricto con `require_complete`.

## Visor fotográfico

Regenerar sin descargar:

```bash
python scripts/render_h16_h23_photo_viewer.py \
  --fixture results/generated/mapillary/h16-h23-multicandidate-top50-v1/fixture.json \
  --plan results/generated/mapillary/h16-h23-multicandidate-top50-v1/acquisition-plan.json \
  --output results/generated/mapillary/h16-h23-multicandidate-top50-v1/photo-viewer.html
```

Con el mismo servidor local, abrir:

```text
http://127.0.0.1:8765/results/generated/mapillary/h16-h23-multicandidate-top50-v1/photo-viewer.html
```

El visor ordena H16/H23 por rango CT2L y candidato. Muestra IDs, distancia,
secuencia, imágenes compartidas, disponibles, pendientes y candidatos sin
cobertura. Solo muestra un `<img>` cuando el fichero existe y su SHA-256 coincide.

Estado local actual:

- 100 slots de candidato;
- 98 con cobertura metadata-only;
- 32 imágenes únicas históricas disponibles y verificadas;
- 379 imágenes pendientes;
- 89 asociaciones candidato-imagen disponibles;
- 683 asociaciones pendientes;
- `data/cache/mapillary/` todavía no existe porque no se autorizó adquisición.
