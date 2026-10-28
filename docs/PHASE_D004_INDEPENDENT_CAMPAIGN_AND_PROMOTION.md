# D004: campaña independiente y promoción Top-100 preparada

## Viabilidad espacial H26–H61

D004 tiene 0,753 km² de polígono proyectado. Usando las 29 referencias históricas
H01–H25/SV y exclusión de 75 m queda una estimación de 0,415 km² elegible antes de
filtrar espacio público. Construcciones de capacidad reproducibles encuentran
aproximadamente 97 centros hexagonales con separación 75 m; no son observaciones
seleccionadas ni se materializan como datos.

Con bloques de 150 m:

- malla 6×6;
- capacidad estimada 62 con máximo dos por bloque;
- existe separación 12 development / 24 test dejando una columna de guardia;
- 29 bloques tienen ≥25 % de área elegible, 19 ≥50 %.

Por tanto, 36 observaciones caben geométricamente. El riesgo es diversidad
ambiental, no capacidad. Si el trabajo de campo no logra calles ordinarias,
avenidas, espacios abiertos y morfologías distintas sin relajar exclusiones, se
reactiva la propuesta B; no se reduce distancia para completar cuota.

La campaña fija:

- D004 y galería principal 50 m;
- bloques 150 m en EPSG:25830;
- exclusión/separación objetivo 75 m;
- máximo dos observaciones por bloque;
- guardia development/test;
- H26–H37 development y H38–H61 test sellado.

## Recogida práctica

La plantilla `independent_h26_collection_template.json` y schema se validan con
`validate_independent_campaign.py`. El recolector debe capturar GNSS múltiple,
precisión, orientación, fotografía propia, descripción in situ, consentimiento y
claims. El validador comprueba hashes, rutas, orden temporal, bloques y
solapamientos históricos.

El test final requiere dos anotadores sin propuestas AI visibles. Mapillary solo
se usa para candidatos y cualquier nueva descarga requiere revisión del alcance.

## Promoción Top-100

`topn_promotion.py` implementa una transformación pura y reversible:

- Top-100 de entrada, Top-10 activo;
- solo evidencia positiva en v1;
- `lambda_neg=0`;
- bloques 11–20, 21–50 y 51–100 abiertos explícitamente;
- máximo de promociones congelado;
- no foto, fallo, output inválido, abstención y conflicto son neutrales;
- cobertura nunca puntúa;
- candidatos desplazados permanecen en el orden Top-100;
- baseline restaurable desde el artefacto.

La configuración versionada está desactivada. No hay política real congelada ni
ejecución sobre candidatos de reserva, porque faltan fotografías, claims,
veredictos y calibración H26 development.

El evaluador posterior puede medir GeoRecall/Recall @1/5/10, distancia, candidatos
promovidos/desplazados y falsos descartes después del freeze. No selecciona
parámetros.

## MVP

Se prepararon settings y capability inactiva:

```text
ATLAS_VISUAL_PROMOTION_ENABLED=false
ATLAS_VISUAL_PROMOTION_FALLBACK=baseline
ATLAS_VISUAL_PROMOTION_REQUIRED=false
```

Con la opción desactivada:

- no se carga VLM/promoter;
- no se montan fotos/modelos/políticas;
- retrieval sigue Top-10;
- respuesta baseline no cambia;
- capability aparece experimental/no disponible.

Una activación futura usaría fallback explícito al baseline ante ausencia de
fotos, fallo VLM o evidencia insuficiente. No está implementada en la ruta HTTP.

## Estado

- Infraestructura D004 intacta.
- Promoción y evaluador: implementados y probados con fixtures sintéticas.
- Descarte: no implementado/activado.
- Sustitución real: bloqueada por datos humanos y visuales de reserva.
- MVP: sin cambios funcionales.
- Próxima dependencia: recogida H26 development y autorización Mapillary.
