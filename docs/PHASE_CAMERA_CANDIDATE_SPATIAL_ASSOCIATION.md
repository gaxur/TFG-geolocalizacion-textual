# Asociación geométrica cámara-candidato v1

## Datos disponibles

- centros y polígonos 50×50 m del catálogo en EPSG:25830/WGS84;
- posición de cámara Mapillary, sin precisión horizontal declarada;
- heading y procedencia, secuencia, tipo, resolución y quality score;
- sin FOV, pitch ni incertidumbre de orientación;
- F3: objetos OSM que intersectan la celda, predicados topológicos, tipo y
  distancia centro–geometría; geometría completa no serializada, solo bbox.

No puede comprobarse con estos datos qué objeto de los píxeles corresponde a qué
geometría OSM. F3 aporta contexto cartográfico, no visibilidad.

## Contrato nuevo

`camera-candidate-spatial-association-v1` calcula:

- cámara y centro en EPSG:25830;
- distancia centro;
- distancia a superficie del cuadrado;
- interior/borde/exterior;
- bearing cámara-centro;
- diferencia angular circular;
- cono-celda por clipping;
- FOV conocido, omnidireccional, hipotético o ausente;
- sensibilidad 60/90/120°;
- celdas competidoras en toda la galería 50 m.

FOV 90° es una hipótesis experimental, no metadata Mapillary. La intersección
solo significa compatibilidad potencial.

Clasificaciones:

- `camera_inside_candidate`;
- `camera_outside_view_compatible`;
- `orientation_incompatible`;
- `insufficient_orientation_metadata`;
- `spatially_ambiguous`;
- `not_eligible`.

No se excluyen automáticamente cámaras exteriores ni asociaciones ambiguas.

## Retrospectiva de 99 asociaciones

| Categoría | Asociaciones | Candidatos | Fotos físicas |
|---|---:|---:|---:|
| Cámara dentro | 21 | 10 | 16 |
| Orientación hipotéticamente incompatible | 38 | 19 | 9 |
| Compatible pero ambigua | 40 | 14 | 23 |

Las 99 tienen al menos una celda competidora bajo la galería/FOV hipotético; la
categoría primaria mantiene interior o incompatibilidad cuando corresponde.

Con FOV 60/90/120°, las asociaciones perspectiva con intersección positiva son
39/41/48 y las disjuntas 40/38/31. La sensibilidad impide tratar 90° como verdad.

## Evidencia compartida

- 41 imágenes físicas;
- 23 compartidas entre asociaciones;
- 18 exclusivas;
- 2B: 262/305 soportes sobre imágenes compartidas;
- 8B: 249/299;
- jobs soportados menos pares físicos imagen-claim únicos: 126 en 2B y 115 en 8B.

Un mismo output imagen-claim se proyecta sobre candidatos distintos porque el
prompt no incluye candidato. No son confirmaciones independientes. Se propone
diagnosticar:

```text
evidencia exclusiva = soporte de imagen asociada a un único slot/candidato
```

Esto no penaliza automáticamente lo compartido; mide capacidad discriminativa.

## Comparación de selectores metadata-only

| Selector | Asociaciones | Assets únicos | Slots cubiertos | Grupos medios | Ambiguas |
|---|---:|---:|---:|---:|---:|
| Histórico fijo | 766 | 432 | 98/100 | 5,67 | no calculadas en plan histórico |
| Adaptativo cobertura | 568 | 323 | 98/100 | 5,68 | no usa geometría nueva |
| Adaptativo geométrico | 568 | 315 | 98/100 | 5,68 | 305 |

La variante geométrica ahorra ocho assets frente a la adaptativa y cambia 704
asociaciones, pero mantiene dos slots sin cobertura y reduce bins de orientación
medios. No se declara mejor: no hay nueva inferencia ni evaluación prospectiva.

## Integración adaptativa

La prioridad geométrica se aplica después de equidad max-min y nueva secuencia:

1. déficit de grupos e imágenes;
2. nueva secuencia;
3. cámara dentro/borde;
4. panorámica/FOV compatible;
5. menos celdas competidoras;
6. distancia a superficie;
7. centro/quality/resolución/IDs.

Para conservar completitud del inventario buffer100 histórico, v1 mantiene
`center_distance<=radio` como gate y usa superficie/FOV solo como prioridad. Un
selector por superficie a 100 m requeriría buffer conservador ≈135,36 m y nueva
adquisición autorizada.

## H16 interior

Los claims altar, retablo, escultura, hornacinas, pinturas, cúpula y púlpito
requieren fuente interior. Mapillary exterior debe parar tras agotar presupuesto,
no ampliar radio. Commons se estudiará en protocolo separado, con búsqueda
geométrica para todos los candidatos, `location_kind=camera` y licencias por
fichero. La búsqueda por nombre/entidad será un brazo semántico distinto.

## H23 orientación

Heading y bearing permiten saber si la celda podría estar delante de la cámara.
No permiten reconstruir orientación del observador ni posición izquierda/derecha
de objetos. Un protocolo futuro requerirá FOV, crop/yaw efectivo y anotación de
objetos en imagen; la abstención actual sigue activa.
