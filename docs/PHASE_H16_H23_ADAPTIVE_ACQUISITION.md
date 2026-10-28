# Auditoría de distancias y adquisición visual adaptativa

## Selector Mapillary actual

El inventario regional se obtuvo sobre D004 con buffer de 100 m calculado en
EPSG:25830, pero la asociación histórica H16/H23 no usa ese CRS. Para cada
candidato toma únicamente latitud/longitud del centro de celda y aplica Haversine
con radio único `<=100 m`.

No usa:

- borde o superficie de la celda;
- geometría OSM;
- FOV;
- intersección de heading con celda;
- pertenencia del objeto visible al candidato.

El heading sí se usa para prioridad:

1. panorámicas;
2. perspectivas alineadas ≤45°;
3. ≤90°;
4. resto o heading ausente.

Después ordena por distancia, quality score y `image_id`. Una primera pasada
elige secuencias distintas; una segunda rellena hasta ocho permitiendo repetir.
Una fotografía puede asociarse a varios candidatos y se descarga una sola vez.

Una asociación significa “cámara a ≤100 m del centro”, no “objeto visible
pertenece a la celda”.

## Distancias post hoc EPSG:25830

Se analizaron las 99 asociaciones parciales existentes sin modificar su selección.
La celda 50 m se reconstruye como cuadrado centro±25 m.

| Banda centro | Fotos físicas | Asociaciones | Candidatos | Secuencias | Dentro de celda |
|---|---:|---:|---:|---:|---:|
| 0–25 m | 13 | 17 | 9 | 10 | 17 |
| 25–50 m | 16 | 24 | 11 | 15 | 4 |
| 50–100 m | 23 | 58 | 23 | 23 | 0 |
| 100–150 m | 0 | 0 | 0 | 0 | 0 |
| >150 m | 0 | 0 | 0 | 0 | 0 |

Los conteos físicos no suman 41 porque una imagen puede aparecer en más de una
banda al asociarse a candidatos diferentes. Solo 21/99 asociaciones sitúan la
cámara dentro de la celda.

### Veredictos por banda

2B:

| Banda | Supported | Contradicted | Unverifiable | Abstención orientación |
|---|---:|---:|---:|---:|
| 0–25 | 49 | 0 | 202 | 52 |
| 25–50 | 76 | 0 | 326 | 84 |
| 50–100 | 180 | 0 | 733 | 190 |

8B:

| Banda | Supported | Contradicted | Unverifiable | Abstención orientación |
|---|---:|---:|---:|---:|
| 0–25 | 53 | 4 | 194 | 52 |
| 25–50 | 64 | 1 | 337 | 84 |
| 50–100 | 182 | 6 | 725 | 190 |

No debe interpretarse causalmente: cambian consultas, candidatos, claims y
número de jobs entre bandas.

El bundle F3 aporta distancia centro–geometría OSM intersectante y tags, no
distancia cámara–objeto visible. La geometría completa de ways/áreas no está
serializada, solo `metric_bbox`; por ello no se presenta como prueba de
visibilidad.

## Riesgo de radios grandes

El radio 100 m excede ampliamente la celda 50×50 m. Una cámara puede mostrar un
objeto de otra celda y generar soporte positivo contaminado. Heading al centro
reduce algunos casos, pero no mide FOV ni localiza el objeto en la imagen.

Ampliar a 150 m requiere:

- inventario regional con buffer 150 m;
- protocolo y autorización nuevos;
- mayor control de celda/heading/FOV;
- análisis de contaminación entre candidatos.

No se recomienda como cuarta ronda principal antes de validar 25/50/100 m.

## Adaptive visual acquisition v1

Variante propuesta, no autorizada:

`config/h16_h23_adaptive_visual_acquisition_v1.json`.

Rondas hipotéticas:

| Ronda | Radio | Imágenes acumuladas | Grupos acumulados |
|---|---:|---:|---:|
| 1 | 25 m | 2 | 2 |
| 2 | 50 m | 4 | 4 |
| 3 | 100 m | 8 | 8 |

El planner usa inventario metadata-only y reparte oportunidades mediante max-min
por secuencias. No recibe claims, veredictos, `supported`, píxeles ni GT. La
adquisición finaliza antes de ejecutar Qwen3-VL.

Límites propuestos: 3 rondas, 100 m, 8 imágenes/grupos por candidato, 432 assets,
391 nuevos, 11.080 jobs por modelo, 3.128 GB y 8 MB por asset. Son hipótesis
compatibles con el plan actual, no parámetros validados.

## Estrategias

### A. Fija

Hasta ocho imágenes a 100 m para todos. Simple y prospectiva, pero puede dejar
desigualdad de secuencias y gastar frames redundantes.

### B. Adaptativa por cobertura

Rondas 25/50/100, presupuesto max-min por grupos independientes. No mira outputs
VLM. Es la estrategia principal propuesta.

### C. Adaptativa por supported

Asigna más presupuesto a candidatos con poco o mucho soporte. Puede perseguir
coincidencias accidentales y concentrar recursos en candidatos incorrectos. Solo
debe estudiarse como control sesgado y no seleccionar la política principal.

## Cobertura mínima

Para candidato `c`:

```text
C_c = min(1, grupos independientes válidos / objetivo de grupos de la ronda)
```

Hipótesis inicial no validada: `C_c >= 0,5` para permitir modificador visual. Si
no se alcanza:

- conservar score CT2L;
- marcar evidencia insuficiente;
- no excluir ni penalizar;
- seguir informando imágenes, grupos, jobs y claims evaluados.

La cobertura mide oportunidad, no utilidad. `supported` no forma parte de ella.

## Interior H16 y multifuente

H16 debe marcarse `interior_required`. El planner Mapillary exterior no debe
ampliar indefinidamente radio. Una variante Commons/Panoramax interior debe usar
un run separado por proveedor, licencia y manifest. Commons por nombre/categoría
es búsqueda semántica y no debe mezclarse con geosearch geométrica.

## Orientación H23

Una variante futura puede combinar heading, bearing y FOV estimado para comprobar
si la celda cae en encuadre. No establece la orientación original del usuario y
no habilita automáticamente izquierda/derecha. La abstención actual permanece.
