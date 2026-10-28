# Corrección versionada de claims y variante H16/H23 v2

## Causa técnica

El extractor v1 recorría patrones por orden de vocabulario, no por orden textual.
Los atributos solo se asociaban al último objeto anterior y las relaciones al
primer objeto posterior de toda la oración. Además, dos menciones `building` no
tenían identidad diferenciada. Esto produjo `facing→dome`, `white→street` y
`stone→column` y no podía representar `choir/altarpiece`.

## Extractor v2

`visual-atomic-claims-v2` y `visual-atomic-rules-v2` se añaden en paralelo; v1 se
conserva intacto para reproducir resultados históricos.

V2:

- ordena menciones por span;
- crea `visual-entity-sha256-*` por tipo y span;
- asocia atributos prenominales al sustantivo posterior local;
- asocia atributos posnominales al sustantivo anterior local;
- limita relaciones a su oración y al siguiente marcador egocéntrico;
- permite sujeto anterior cuando la construcción es retrospectiva;
- usa `unknown` si no existe sujeto local;
- añade `altarpiece` y el atributo literal `dark`.

Resultados corregidos:

- `facing` → `altar`;
- `In front of me` → `altarpiece`;
- `white` → primera entidad `building`;
- `stone` → segunda entidad `building`;
- relaciones izquierda/derecha apuntan a esos dos IDs distintos.

## Variante inglesa v2

El original versionado confirma `retablo oscuro`. La variante H16 v1 decía
`dark choir`; se conserva. V2 reemplaza solo esa aparición por `dark altarpiece`:

- control: `H16-en-cartographic-corrected-h11h25-v2`;
- SHA-256 textual:
  `6a532157d04dfabbeb204fd48682eaa5d7322a3ad27ec340c02e9a304a0ee5cb`.

H23 conserva su texto exacto como control de reproducibilidad, pero adopta claims
v2 con entidades.

## Ranking CT2L v2

Se ejecutó CT2L congelado sin GT sobre `madrid-50m`, Top-100 exhaustivo:

- ranking ID:
  `h16-h23-top100-v2-sha256-ed47b146937f96d857194ab9692bc36b40b94e71cb4ddfb9f392fce67fa9ed53`;
- checkpoint SHA-256: `d0c2f684...`;
- embeddings visuales: `f4-madrid-embeddings-sha256-199dae...`.

H16 cambia Top-10, conjunto Top-50 y orden Top-100. H23 reproduce exactamente
Top-10, conjunto Top-50 y Top-100 v1. Por ello no se reutiliza el fixture v1.

## Linaje experimental v2

- variante/ranking: `results/generated/f5/h16-h23-corrected-v2/`;
- fixture: `results/generated/mapillary/h16-h23-multicandidate-top50-v2/fixture.json`;
- protocolo: `config/h16_h23_top50_experiment_v2.json`;
- revisión canónica:
  `results/generated/mapillary/h16-h23-multicandidate-top50-v2/reviews/h16-h23-top50-claims-review-v2.json`;
- formulario:
  `results/generated/mapillary/h16-h23-multicandidate-top50-v2/review-claims.html`;
- visor:
  `results/generated/mapillary/h16-h23-multicandidate-top50-v2/photo-viewer.html`.

V2 contiene 29 claims: 19 H16 y 10 H23. La migración transfiere cero decisiones
porque el canónico v1 tenía 27/27 pendientes. Claims nuevos o corregidos requieren
decisión humana.

El nuevo plan fotográfico contiene 432 IDs únicos, 41 disponibles y 391 pendientes.
No se descargó ninguna imagen ni se ejecutó Qwen3-VL.
