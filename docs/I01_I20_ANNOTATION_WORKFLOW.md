# Flujo humano I01–I20

## Estado

Las interfaces están preparadas, pero no existe ninguna anotación, revisión,
adjudicación o respuesta de custodio completada. Las veinte observaciones siguen
`PENDING_BLIND_EXCLUSION` y ninguna es `ELIGIBLE`.

## Abrir las interfaces

Desde la raíz del repositorio, servir únicamente el paquete requerido:

```bash
python -m http.server 8765 --bind 127.0.0.1 \
  --directory results/generated/i01-i20-annotation-workflow-v1/annotation
```

Abrir `http://127.0.0.1:8765/annotate.html`.

Para escenas:

```bash
python -m http.server 8766 --bind 127.0.0.1 \
  --directory results/generated/i01-i20-annotation-workflow-v1/scene-review
```

Abrir `http://127.0.0.1:8766/review-scenes.html`.

La interfaz contiene los datos embebidos en el propio HTML; no usa `fetch` para
cargar `fixture.json`. Las fotografías sí se sirven desde `references/` mediante
rutas relativas. Si falla la inicialización o una promesa JavaScript, se muestra
un panel rojo visible en lugar de dejar la lista vacía.

### Corrección de carga parcial

La primera versión generada usaba `export.onclick`. `export` es una palabra
reservada de JavaScript, por lo que el navegador abortaba el parseo antes de
renderizar las tarjetas. Se sustituyó por referencias DOM explícitas mediante
`document.getElementById(...)` en todas las interfaces y se añadió un bootstrap
de errores visible.

No servir la raíz completa del repositorio. No subir las carpetas a servicios de
anotación, modelos remotos o almacenamiento no autorizado.

## Anotación

Ruta:

`results/generated/i01-i20-annotation-workflow-v1/annotation/annotate.html`

El descriptor introduce pseudónimo, descripción española y claims con span
literal. La página muestra en vivo el substring seleccionado. Registra
observabilidad, certeza, OCR, orientación e incertidumbre.

El botón exporta `i20-annotation-submitted.json`. Un borrador del mismo contrato
puede volver a cargarse. El navegador no congela la anotación: el JSON sigue
`annotation_open` y debe pasar validación Python, dos revisiones y adjudicación.

La revisión de escenas debe completarse primero. Si excluye o bloquea una
observación, regenerar las interfaces con:

```bash
python scripts/build_i20_annotation_interfaces.py \
  --acquisition-root results/generated/i01-i20-remote-acquisition-v1 \
  --output-root results/generated/i01-i20-annotation-workflow-v2 \
  --scene-review /ruta/i20-scene-review-frozen.json
```

El generador valida la revisión, elimina `EXCLUDE/REVIEW` del cohort humano y se
detiene si quedan menos de 12 observaciones. No se edita manualmente I01–I20.

## Revisión de escenas

Ruta:

`results/generated/i01-i20-annotation-workflow-v1/scene-review/review-scenes.html`

Contiene 12 pares: los nueve pares por debajo de 75 m y pares adicionales de la
misma secuencia. Solo muestra IDs I y archivos opacos. Para cada par registra:

- misma escena;
- objetos distintivos compartidos;
- solapamiento de campo de visión;
- mismo lugar con otro encuadre;
- `CLEAR`, `EXCLUDE` o `REVIEW`.

`CLEAR` no es válido con incertidumbre, misma escena o FOV solapado. La página
permite cargar un borrador y exporta `i20-scene-review-submitted.json`.

## Revisores A y B

Rutas:

- `review-a/review.html`
- `review-b/review.html`

Cada carpeta es independiente y no contiene el output de la otra. Primero se
carga el JSON de anotación presentado. Cada revisor evalúa fidelidad,
observabilidad, orientación, incertidumbre y todos los claims.

Outputs:

- `i20-review-a.json`
- `i20-review-b.json`

Los pseudónimos deben ser distintos. No compartir outputs entre revisores antes
de que ambos terminen.

## Adjudicación

Ruta:

`adjudication/adjudicate.html`

Se cargan anotación, revisión A y revisión B. La página calcula discrepancias en
decisión global y campos claim-level. Solo muestra observaciones discrepantes.

No permite introducir claims nuevos. Puede conservar/eliminar claims originales
o excluir la observación. Una reescritura sustancial exige nueva versión de
anotación y dos revisiones nuevas.

Output:

`i20-review-adjudicated.json`

## Validación

Ejemplo antes de cualquier freeze:

```bash
python scripts/validate_i20_annotation_workflow.py \
  --workflow-root results/generated/i01-i20-annotation-workflow-v1 \
  --geographic-package results/generated/i01-i20-remote-acquisition-v1/geographic-package.json \
  --annotation /ruta/i20-annotation-submitted.json \
  --scene-review /ruta/i20-scene-review-submitted.json \
  --review /ruta/i20-review-adjudicated.json \
  --output results/generated/i01-i20-annotation-workflow-v1/freeze-readiness.json
```

Sin ledger firmado devolverá código 2 y
`authentic_blind_ledger_receipt_missing`.

El validador exige:

- schemas Draft 2020-12;
- imágenes y hashes correctos;
- spans literales y claim IDs por contenido;
- escena completa y sin `REVIEW`;
- cohort activo exacto;
- dos revisores distintos por observación;
- cobertura de todos los claims;
- adjudicación de toda discrepancia;
- ausencia de claims o texto nuevos;
- ledger firmado y verificado;
- referencia geográfica congelada;
- mínimo 12 observaciones.

No modifica estados ni produce `ELIGIBLE`.

## Custodio independiente

El custodio recibe fuera del workspace:

`results/generated/i01-i20-remote-acquisition-v1/blind-ledger-submission-draft.json`

Antes de enviarlo debe completarse y firmarse conforme al schema de submission.
El custodio:

1. opera en host/almacenamiento separado;
2. tiene autorización para acceder al holdout;
3. ejecuta checks exactos, perceptuales, secuencia y escena;
4. resuelve casos ambiguos dentro de su frontera;
5. devuelve solo `CLEAR/EXCLUDE/REVIEW`;
6. firma la respuesta Ed25519;
7. entrega su clave pública de 32 bytes por canal autenticado;
8. emite atestación administrativa sin revelar contenido.

Para importar una respuesta real se añaden:

```text
--ledger-submission <submission firmado>
--ledger-response <respuesta firmada>
--custodian-public-key <32 bytes raw>
```

El workspace verifica firma, compromiso, cardinalidad, orden y ausencia de
campos adicionales. No genera claves, firmas o decisiones de sustitución.

## Separación de geografía

Las interfaces no contienen coordenadas, secuencias, IDs Mapillary, distancias,
rankings, candidatos, OSM o predicciones. Los nombres de archivo son
`ref-<opaco>.jpg`.

El paquete geográfico permanece en:

`results/generated/i01-i20-remote-acquisition-v1/geographic-package.json`

No debe entregarse al descriptor o a revisores de texto/escena. Antes del freeze
final deberá versionarse como paquete geográfico congelado y vincularse a las
referencias seleccionadas.

## Estado actual

`freeze-readiness.json` informa:

- 0 observaciones activas congeladas;
- anotación ausente;
- revisión de escenas ausente;
- revisores/adjudicación ausentes;
- ledger auténtico ausente;
- GT geográfico aún no congelado;
- `ready=false`.

## Variante semiautomática

Existe una variante paralela, sin alterar este workflow humano:

`results/generated/i01-i20-assisted-annotation-v1/`

Tras autorización puede generar borradores Qwen3-VL-8B para los 12 pares y 20
referencias. Las propuestas se importan en interfaces separadas, empiezan siempre
en `pending` y requieren `reviewed/corrected/rejected/unresolved` explícito. Véase
[I01_I20_ASSISTED_ANNOTATION.md](I01_I20_ASSISTED_ANNOTATION.md).
