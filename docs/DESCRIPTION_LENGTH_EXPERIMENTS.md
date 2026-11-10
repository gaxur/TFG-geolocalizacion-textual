# Experimentos de longitud de descripción

## Alcance congelado

El manifest canónico está en
`results/generated/description-length-experiments/manifest.json` y tiene SHA-256
`cfd54ee90ec80baac1dc076fbf5b3d2428a02932a5e26262b120055707fe4bbf`.
Contiene 24 variantes pareadas y 48 condiciones preparadas, no autorizadas ni
ejecutadas.

| Longitud | Intervalo | Variantes | Palabras observadas | Tokens CLIP observados |
|---|---:|---:|---:|---:|
| Corta | 15–30 | 8 | 21–24 | 38–49 |
| Media | 45–70 | 8 | 49–53 | 91–107 |
| Larga | 85–120 | 8 | 89–105 | 168–207 |

Los tokens se contaron con `clip.tokenize`, contexto 300, incluyendo SOT/EOT,
sin cargar pesos ni ejecutar Qwen o CT2L.

## Procedencia

- H26, H27, H28, H29, H31, H33, H36 y H37 son development.
- La variante larga es exactamente la descripción oficial congelada.
- Corta y media seleccionan únicamente hechos de esa descripción oficial.
- No se consultaron imagen, ranking, GT, H38–H61 ni resultados VLM para redactar.
- Los textos oficiales y sus hashes no se modificaron.
- Las sesiones usan IDs `X-HXX-short`, `X-HXX-medium` y `X-HXX-long`.

## Estrategias

El nombre `literal_conversion` no existe en el código. La implementación real y
congelada es `literal_concatenation`, mediante `build_canonical_query` y política
`literal-clarifications-newest-first-300-v1`. La otra estrategia es
`translate_en_cartographic`, prompt `f53b-text-transform-v2` y revisión humana
obligatoria.

Cada una de las 24 variantes tiene dos condiciones sobre `madrid-50m`, 253
candidatos, coseno exhaustivo y desempate por ID. Ninguna condición se ha
ejecutado. La autorización lote permanece pendiente en
`config/dialogue_length_experiments_authorization.request.json`.

## Tabla de variantes

La tabla exacta de identificador, texto, palabras, tokens, hashes, imagen y
procedencia se encuentra en el array `variants` del manifest. Se genera de forma
determinista con:

```bash
python scripts/prepare_description_length_experiments.py \
  --cohort /ruta/al/checkout-experimental/results/generated/dialogue-development-h26-h37-v3/cohort.json \
  --output results/generated/description-length-experiments
```

El frontend obtiene ese mismo manifest desde `GET /api/v1/dialogue/variants` y
no mantiene una copia divergente.
