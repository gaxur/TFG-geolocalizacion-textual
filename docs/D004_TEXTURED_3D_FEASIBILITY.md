# Viabilidad de edificios 3D texturizados en D004

## Resultado

No se incorporó una capa de texturas reales porque ninguna fuente auditada
cumple a la vez estas condiciones:

- cubrir D004;
- incluir fachadas o malla fotogramétrica real;
- permitir recorte estricto a D004;
- integrarse con MapLibre sin sustituir el MVP;
- funcionar sin credenciales o facturación nuevas;
- permitir caché, reproducción local y redistribución compatibles con el TFG;
- conservar licencia, atribución y provenance verificables.

Aplicar una fotografía de calle sobre una extrusión OSM sin calibración produciría
una fachada falsa. No se ha implementado esa aproximación.

## Área autorizada

La capa texturizada solicitada estaría limitada a:

```text
Oeste: -3.709
Sur:    40.412
Este:  -3.699
Norte: 40.420
```

El PMTiles de contexto de 2 km seguiría siendo únicamente cartografía de fondo.
La región científica, candidatos, embeddings y rankings no cambiarían.

## Activos locales

Los dos checkouts no contienen archivos CityGML, glTF/GLB, OBJ/MTL, 3D Tiles,
I3S descargado, LAS/LAZ, PLY o mallas fotogramétricas. El PMTiles visual contiene
huellas y atributos OSM, pero no texturas, ventanas, relojes, esculturas o
geometría detallada de cubiertas.

Hay fotografías Mapillary y metadata de secuencias, pero no existen intrínsecos
de cámara, pose completa 6-DoF, profundidad, correspondencias multivista ni
asociación calibrada entre imagen y plano de fachada. No son un modelo 3D listo
para texturizar.

## Ayuntamiento de Madrid

Se revisó el recurso oficial **Edificios 3D Madrid**:

- ficha: <https://www.arcgis.com/home/item.html?id=e914b8e723274b13ad69a4348029c0a4>;
- servicio I3S:
  <https://tiles-eu1.arcgis.com/UrtTdLP2PYSxwtI6/arcgis/rest/services/EdificiosMadrid_LOD1v2/SceneServer/layers/0>;
- reutilización comercial y no comercial permitida con atribución al Ayuntamiento
  de Madrid y conservación de metadata.

La capa cubre Madrid y usa geometría de cubiertas procedente de vuelo
fotogramétrico, extruida hasta el terreno. Su renderer es un relleno blanco simple.
Aunque el formato I3S admite coordenadas UV y JPEG/DDS, la metadata no demuestra
que esta capa contenga fachadas fotográficas. Por tanto, mejora geometría, pero no
cumple el requisito de texturas reales.

También se revisó la malla municipal texturizada:

<https://tiles-eu1.arcgis.com/UrtTdLP2PYSxwtI6/arcgis/rest/services/VUELOS_2019_TEXTURAS/SceneServer/layers/0>

Es una `IntegratedMesh` con JPEG/DDS, pero su extensión es:

```text
Oeste: -3.7092723
Sur:    40.4369974
Este:  -3.6679728
Norte: 40.4690452
```

No intersecta D004. No puede utilizarse para este MVP.

## Google Photorealistic 3D Tiles

Es la opción con mayor probabilidad de ofrecer apariencia real en D004:

<https://developers.google.com/maps/documentation/tile/3d-tiles>

Requiere:

- proyecto Google Cloud;
- facturación habilitada;
- Map Tiles API habilitada;
- API key restringida por API y origen HTTP;
- conexión permanente;
- logo Google Maps;
- atribuciones dinámicas agregadas de cada tesela visible;
- respeto estricto de `Cache-Control` y `ETag`.

Sus políticas prohíben descarga masiva, precarga, caché persistente, uso offline,
extracción de geometría y creación de modelos derivados:

<https://developers.google.com/maps/documentation/tile/policies>

No existe una clave autorizada en el worktree. Tampoco se puede verificar la
cobertura y calidad concreta de D004 sin realizar una solicitud autenticada.

### Biblioteca propuesta

La integración MapLibre recomendada sería:

- `maplibre-gl-three`;
- Three.js;
- `3d-tiles-renderer`;
- una `CustomLayerInterface` de MapLibre con `renderingMode: "3d"`.

Referencia oficial:

<https://maplibre.org/maplibre-gl-js/docs/examples/add-3d-tiles-3d-objects-and-models-using-threejs/>

Otra opción sería `Tile3DLayer` de deck.gl:

<https://deck.gl/docs/api-reference/geo-layers/tile-3d-layer>

Se prefiere Three.js para este caso porque permite aplicar cuatro planos de
clipping a todos los materiales y ocultar estrictamente los triángulos situados
fuera de D004. Limitar la cámara o descartar teselas no basta: una tesela puede
cruzar el límite y mostrar geometría exterior.

### Controles obligatorios

Una implementación futura debería:

1. activarse solo mediante configuración explícita;
2. mantener la clave fuera del repositorio;
3. mostrar únicamente geometría recortada por los cuatro planos de D004;
4. ocultar las extrusiones OSM dentro de D004 para evitar solapamiento;
5. conservar el PMTiles OSM en el contexto exterior;
6. mostrar logo y atribución dinámica de Google sin solaparlos con OSM;
7. no enviar teselas, capturas o geometría al VLM, CT2L o embeddings;
8. no guardar teselas en `results/`, caches persistentes o artefactos del TFG;
9. limitar cuotas y presupuesto desde Google Cloud;
10. registrar versión de bibliotecas y prueba visual, pero no copiar contenido.

## Cesium y deck.gl

Cesium OSM Buildings y MapTiler proporcionan geometría extruida o estilizada, no
fachadas reales de Madrid. Cesium ion exige token y sus datos servidos tampoco son
un artefacto offline reproducible. CesiumJS sí ofrece clipping de polígonos, pero
añadir un segundo motor completo y sincronizar su cámara con MapLibre introduce
más complejidad que `maplibre-gl-three`.

deck.gl soporta Google 3D Tiles e I3S municipal mediante `Tile3DLayer`, pero no
ofrece una propiedad pública de recorte geométrico exacto por bbox. Haría falta
un shader o stencil personalizado.

## Mapillary

Mapillary se conserva como fuente de evidencia fotográfica separada, no como
textura. Reconstruir D004 exigiría adquirir imágenes originales solapadas,
calibrar cámaras, ejecutar SfM/MVS, eliminar personas y vehículos, asociar mallas
a edificios y revisar CC BY-SA/condiciones de API y retención. No es una mejora
pequeña ni de bajo riesgo.

## Decisión operativa

El MVP mantiene:

- PMTiles OSM de contexto de 2 km;
- extrusiones cartográficas explícitas/estimadas;
- D004 resaltada en rojo;
- ausencia de afirmaciones sobre fachadas reales.

La capa fotorealista queda **bloqueada**, no descartada. Para desbloquearla se
necesita autorización expresa para crear un proyecto Google Cloud con facturación,
una API key restringida y una prueba online de cobertura D004. Solo después se
debe implementar y validar el clipping estricto antes de mostrarla al usuario.
