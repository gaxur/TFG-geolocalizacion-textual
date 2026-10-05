# Contratos de la Fase 0

Este documento describe la infraestructura contractual inicial. No genera
datos, no descarga OSM, no carga modelos y no fija parámetros experimentales.

## Estructura

```text
config/madrid.yaml
schemas/
  region_config.schema.json
  manifest.schema.json
  llm_geo_query.schema.json
  evaluation_example.schema.json
  experiment_parameters.schema.json
src/tfg_phase0/
  config.py
  validation.py
  provenance.py
tests/test_phase0.py
```

`config/madrid.yaml` utiliza el subconjunto JSON de YAML 1.2. Se ha elegido así
para que la Fase 0 no introduzca todavía un parser o dependencia de proveedor.

## Contratos

- **Región:** conserva la bbox D004, EPSG:4326 y el CRS proyectado EPSG:25830.
- **Manifest:** relaciona `candidate_id`, coordenadas y referencias opcionales a
  imágenes, embeddings y scenes. No inventa el formato interno de CrossText2Loc
  ni GOTPR.
- **LLM:** solo admite intención geográfica estructurada. No incluye campos para
  Overpass QL, coordenadas inventadas o `candidate_id`.
- **Evaluación:** separa texto, split, procedencia, coordenada observada,
  asignación derivada al catálogo y reproducibilidad.
- **Parámetros experimentales:** permite valores `null`; no convierte los
  valores provisionales de D003, D021, D024, D029, D030 o D031 en defaults.

## Validación

La biblioteca estándar de Python proporciona el validador básico utilizado por
los tests. Los ficheros `.schema.json` son la especificación portable para
incorporar más adelante un validador JSON Schema completo si el proyecto lo
necesita.

## Reproducibilidad

`provenance.py` produce JSON canónico y hashes SHA-256 de parámetros. Las fases
posteriores deberán añadir snapshot OSM, versión de catálogo, versión de código,
checkpoint y hashes de artefactos cuando esos recursos existan.

La evolución de estos contratos para construir la cuadrícula y el manifest
físico se documenta en [PHASE1_GEOGRAPHIC_CATALOG.md](PHASE1_GEOGRAPHIC_CATALOG.md).
