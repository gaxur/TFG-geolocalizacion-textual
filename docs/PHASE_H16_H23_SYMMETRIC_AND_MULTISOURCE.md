# Reranking simétrico y cobertura multifuente H16/H23

## Auditoría de la promoción histórica

`topn_promotion.py` aplica el bonus visual solo si el rango pertenece a un bloque
de reserva abierto. Los candidatos Top-10 reciben modificador cero aunque tengan
evidencia mayor. La comparación H23 fue por tanto:

```text
rank 12: CT2L + 0,2 × evidencia
rank 10: CT2L + 0
```

El contrato histórico representa promoción desde reserva, no un reranking global.
Se conserva sin cambios para reproducibilidad.

## Reranking simétrico v1

Contrato nuevo:

`h16-h23-symmetric-visual-reranking-policy-v1`.

Para todos los 50 candidatos:

```text
score = minmax(CT2L Top-50) + 0,2 × evidencia positiva efectiva
```

Sin foto, fallo, conflicto o `unverifiable` producen modificador cero. Evidencia
negativa permanece desactivada. El orden usa score descendente, rango CT2L y
`candidate_id`.

### Resultado parcial

La variante simétrica elimina la entrada rank 12/salida rank 10 de H23. No cambia
la membresía Top-10 en ninguna consulta. Sin embargo, reordena dentro del Top-10:

- H16 rank 3 sube a Top-1 en ambos modelos;
- distancia Top-1 H16: 407,42 m → 906,34 m;
- H23 conserva Top-1;
- media Top-1: 302,11 m → 551,57 m;
- GeoRecall@1/5/10 a 50/100 m permanece 0/2.

Por tanto, eliminar la asimetría no mejora la geografía en la evidencia parcial.
La evidencia visual positiva parece poco discriminativa, especialmente por el
desajuste interior/exterior de H16 y la cobertura incompleta.

Artefactos:

- `partial-symmetric-reranking-v1.json`, SHA-256
  `37824c9523411f7d83fe45d3caaa4e9e7f4707aeee68ccce3592f689143432d7`;
- `partial-symmetric-geography-v1.json`.

## Proveedores visuales

### Mapillary

Inventario congelado de 5.337 imágenes en D004+buffer 100 m. Incluye coordenada,
heading, secuencia, tipo de cámara, resolución, fecha y quality score. Cubre 98/100
slots H16/H23 y 78/79 candidatos únicos a 100 m. La nueva descarga sigue sin
autorización.

### Panoramax

API federada STAC/GeoJSON documentada por Panoramax. El snapshot histórico local
contiene diez items D004, posición, precisión cuando existe, fecha, azimut,
colección, productor, licencia y URLs de assets. En el análisis reproducible:

- 9/100 slots a 100 m;
- 5/79 candidatos únicos;
- ninguno añade cobertura sobre Mapillary;
- snapshot D004 estricta, no buffer 100 m.

D073 retiró Panoramax como GT/evidencia activa. Puede reutilizarse en una variante
metadata-only nueva, no reinterpretarse como aprobación GT.

### KartaView

La API histórica OpenStreetCam/KartaView no respondió en esta sesión y no existe
snapshot local reproducible. Las condiciones actuales y atribución siguen por
aclarar. Estado: `unavailable_not_frozen`, no cobertura cero.

### Wikimedia Commons

MediaWiki Action API permite `geosearch`, incluido namespace File, coordenada,
radio y paginación. Los metadatos estructurados del namespace File son CC0, pero
cada fotografía conserva licencia propia y posibles obligaciones de atribución,
ShareAlike y restricciones no copyright.

Geosearch no garantiza que la coordenada sea la posición de cámara: puede ser la
ubicación del objeto. Un adaptador debe exigir `location_kind=camera` para
cobertura de observador. La búsqueda semántica por nombre/categoría debe ser una
modalidad separada de la búsqueda geométrica. No existe aún snapshot local, por
lo que su cobertura no se cuantifica.

## Arquitectura multifuente

`ImageProvider` normaliza inventarios a:

- proveedor e ID original/global;
- coordenada de cámara;
- precisión;
- fecha;
- heading;
- secuencia/colección;
- tipo y resolución;
- licencia, atribución y URL;
- `location_kind=camera|object|unknown`.

El manifest multifuente debe mantener inventarios separados por proveedor y unir
solo en el análisis. No mezcla imágenes con el protocolo Mapillary v2.

Selección geométrica:

- parte de candidatos CT2L, nunca GT;
- usa EPSG:25830;
- conserva fuente y criterio de asociación;
- no infiere visibilidad de proximidad;
- no deduplica entre proveedores sin píxeles, solo marca posibles duplicados.

## H16 interior

Commons podría aportar interiores, retablos o cúpulas, pero una foto de un edificio
no representa automáticamente la posición del observador. La consulta geométrica
debe aplicarse a todos los candidatos y aceptar solo ubicaciones de cámara. Una
búsqueda por nombres/entidades OSM es una variante semántica separada. Panoramax
y Mapillary actuales no resuelven la cobertura interior.

## H23 orientación

Una variante futura puede comparar heading de cámara con bearing cámara-candidato
y FOV. Esto solo establece qué zona del entorno podría aparecer en imagen; no
recupera la orientación original del usuario. Las relaciones izquierda/derecha
requieren además un frame del observador comparable. La abstención actual se
mantiene hasta versionar y validar ese protocolo.
