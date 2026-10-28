# Propuesta de ampliación controlada de Madrid

## D004 actual

D004 es la bbox piloto aceptada, no la extensión definitiva de Madrid:

```text
norte 40.4200
sur   40.4120
este  -3.6990
oeste -3.7090
```

La cuadrícula se construye en EPSG:25830 y conserva solo celdas completas dentro
de la bbox. La envolvente proyectada usada por el generador mide aproximadamente
855,48 × 894,76 m, 0,765 km². La superficie del cuadrilátero proyectado es
aproximadamente 0,753 km²; ambas cifras describen geometrías ligeramente
distintas y no deben mezclarse.

Artefactos D004 actuales:

| Componente | 25 m | 50 m |
|---|---:|---:|
| Candidatos | 1.115 | 253 |
| PNG | 231,49 MB | 52,22 MB |
| Embeddings | 3,52 MB | 0,80 MB |
| Render limpio | 989,67 s | 355,39 s |
| Embeddings | 46,88 s | 16,52 s |

F2 contiene 25.537 nodes, 4.240 ways y 498 relations contextuales en 8,42 MB.
F3 contiene bundles separados 25/50 m. F4 usa un PBF regional Geofabrik de
Madrid, no el snapshot F2.

## Propuesta principal: B balanced

```text
norte 40.4320
sur   40.4020
este  -3.6880
oeste -3.7200
```

Justificación:

- amplía el casco histórico hacia Palacio/Argüelles y sur de Chamberí;
- incorpora transiciones Atocha/Embajadores;
- alcanza el borde Retiro/Salamanca;
- mezcla calle medieval, cuadrícula decimonónica, avenidas, plazas, parque,
  residencial, institucional y entornos ferroviarios;
- incrementa hard negatives urbanos sin llegar a una escala municipal difícil de
  controlar.

Estimaciones reproducidas con el generador F1 actual:

| Medida | Valor |
|---|---:|
| Área proyectada | 9,041 km² |
| Candidatos 25 m | 14.204 |
| Candidatos 50 m | 3.448 |
| PNG 25 m | ~2,95 GB |
| PNG 50 m | ~0,71 GB |
| Render total | ~4 h 51 min |
| Embeddings total | ~13,7 min |
| OSM raw estimado | ~101 MB |

El PBF regional actual cubre esta bbox y puede reutilizarse si se acepta su fecha
2026-10-14. El snapshot Overpass F2 no cubre la ampliación y debe readquirirse.

## Alternativa mínima: A compact

```text
norte 40.4250
sur   40.4070
este  -3.6940
oeste -3.7140
```

- 3,390 km²;
- 5.268 candidatos 25 m;
- 1.275 candidatos 50 m;
- ~1,36 GB PNG combinados;
- ~1 h 48 min de render;
- OSM raw estimado ~37,9 MB, nominalmente bajo el límite actual de 50 MB.

Es el fallback si B falla en adquisición OSM, almacenamiento o throughput.

## Opción C

La bbox `40.3950,-3.7250,40.4400,-3.6800` produciría 30.127/7.431 candidatos
y ~7,79 GB de PNG. Se reserva para escalabilidad posterior, no para H26+ inicial.

## Regeneración necesaria

Cambiar bbox cambia el `grid_hash` y todos los `candidate_id`. Debe regenerarse:

1. F1: catálogos 25/50 m y manifests.
2. F2: snapshot OSM XML y provenance.
3. F3: asociaciones, geometrías y contextos.
4. F4: selecciones, PNG y manifests visuales.
5. Embeddings y sidecars de orden.
6. Configuración runtime y smokes.
7. Rankings y evaluación H26+.

No se reutilizan como bundles canónicos los manifests, PNG o embeddings D004.

## Componentes reutilizables

- generadores, schemas y validadores F1–F4;
- EPSG:25830 y política `full_cell_within_bbox`;
- reglas D049 y STRtree;
- PBF regional F4 dentro de su cobertura;
- renderer OSM Carto, estilo, fuentes y assets;
- checkpoint CrossText2Loc, CLIP y runtime;
- contratos VLM, Mapillary, Top-N y evaluación.

El checkpoint sigue siendo zero-shot de Nueva York y no se ajusta.

## Gates antes de ejecutar

1. Aprobar bbox B y versión de región/catálogo.
2. Aprobar 50 m como primera galería; 25 m se materializa después si aporta valor.
3. Revisar adquisición Overpass: B supera previsiblemente `max_raw_bytes=50 MB`;
   fijar límite y estrategia robusta antes de red.
4. Confirmar almacenamiento; queda margen limitado tras modelos VLM.
5. Renderizar una muestra espacial estratificada antes de galería completa.
6. Validar nuevos IDs, cobertura y perfil visual.
7. Congelar bloques espaciales y split antes de H26.
8. Revisar autorización de nueva adquisición Mapillary.

No se ha modificado D004 ni se ha ejecutado ninguna regeneración.
