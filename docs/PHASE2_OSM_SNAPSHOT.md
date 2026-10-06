# Diseño de Fase 2: snapshot OSM reproducible

## Estado

La infraestructura de Fase 2 está **implementada y validada con fixtures
locales**, pero no se ha llamado a Overpass, no se ha descargado OSM y no se ha
creado ningún snapshot real. Las decisiones canónicas son D043-D048 de
[DECISIONS.md](DECISIONS.md).

## Alcance aprobado

- D043 fija Overpass como fuente primaria para una adquisición controlada de la
  bbox D004 y excluye su uso como dependencia query-time.
- D044 fija OSM XML como raw inmutable y prohíbe sobrescribir snapshots.
- D045 define los mínimos de integridad y provenance.
- D046 separa raw, derivados, imágenes, embeddings e índices y excluye el raw
  voluminoso de Git.
- D047 vincula catálogo y preselección al snapshot y excluye ground truth,
  imágenes, embeddings e índices de Fase 2.
- D048 fija endpoint configurable, consulta, bordes, timeouts, reintentos,
  identidad content-addressed, escritura atómica y validación.

La bbox continúa siendo la definida en D004:

```yaml
north: 40.4200
south: 40.4120
east: -3.6990
west: -3.7090
```

## Flujo previsto

```text
configuración de adquisición versionada
  → consulta Overpass exacta para D004
  → respuesta OSM XML temporal
  → validación estructural y conteos
  → escritura atómica del raw inmutable
  → SHA-256 y tamaño
  → provenance
  → osm_snapshot_id
```

Las fases posteriores consumirán el raw local o derivados explícitos. No se
consultará Overpass durante cada petición de usuario.

## Contenido raw

La adquisición debe preservar inicialmente nodes, ways, relations, members y
tags necesarios para reconstruir geometrías completas. No aplicará un
vocabulario semántico ni filtrará categorías por su utilidad prevista. La
normalización y los filtros se diseñarán en fases posteriores.

## Almacenamiento previsto

La organización conceptual fijada por D044-D048 es:

```text
data/raw/osm/snapshots/<osm_snapshot_id>/
  source.osm
  provenance.json

data/processed/osm/<osm_snapshot_id>/
  ... derivados posteriores ...
```

El raw no se incorpora a Git. La provenance pequeña se evaluará por separado
antes de versionarla. Ningún derivado sobrescribirá el raw.

## Provenance mínima

D045 exige registrar fuente, endpoint, UTC de adquisición, bbox, consulta,
formato, tamaño, SHA-256, versión del mecanismo, conteos, licencia, atribución y
resultado de la adquisición. La provenance no contendrá credenciales ni
convertirá una URL pública en autorización de redistribución.

## Licencia

Los datos OSM están bajo ODbL 1.0. Cualquier memoria o publicación deberá incluir
una atribución equivalente a:

> © OpenStreetMap contributors. Datos disponibles bajo la Open Database License
> (ODbL). https://www.openstreetmap.org/copyright

La publicación de raw o bases derivadas requerirá revisar las obligaciones del
artefacto concreto conforme a
[LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md).

## Fuera de alcance

Fase 2 no incluye:

- procesamiento geométrico de Fase 3;
- renderizado, tiles o imágenes OSM;
- CrossText2Loc o embeddings;
- índice geoespacial o preselección;
- LLM, GOTPR, VLM o diálogo;
- ground truth o datos de evaluación.

D007 permanece pendiente y no se modifica.

## Operación fijada

D048 es la referencia canónica para la consulta Overpass QL exacta, semántica
`seed`/`closure`, endpoint configurable, timeouts, reintentos, formato de
`osm_snapshot_id`, publicación atómica y validaciones. Este documento no duplica
esos parámetros.

Antes de una adquisición real todavía se deberá comprobar la política y
disponibilidad vigentes del endpoint y obtener autorización de ejecución. La
publicación de provenance o derivados seguirá requiriendo la revisión ODbL de
D045-D046. Estas comprobaciones operativas no reabren D048 ni autorizan por sí
solas una llamada de red.

## Materialización

- `config/madrid.yaml` contiene los parámetros operativos fijados por D048.
- `schemas/osm_snapshot.schema.json` define la provenance versionada.
- `src/tfg_phase0/osm_snapshot.py` genera la consulta, valida OSM XML, aplica la
  política de reintentos, construye la provenance y publica snapshots
  inmutables.
- `scripts/acquire_osm_snapshot.py` expone la adquisición, pero no se ha
  ejecutado contra un endpoint real.
- `tests/fixtures/osm/valid.osm` y `tests/test_phase2_osm_snapshot.py` validan el
  flujo sin Internet mediante transporte inyectado.

Los tests no invocan el transporte real. La primera adquisición continúa
requiriendo una autorización separada.
