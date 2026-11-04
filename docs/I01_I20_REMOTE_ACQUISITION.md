# Adquisición remota I01–I20

## Estado

Se adquirió un lote Mapillary limitado y precongelado para preparar I01–I20.
Existen veinte referencias técnicamente válidas, pero ninguna es todavía
`ELIGIBLE`: faltan ledger ciego, revisión humana de escenas, anotación y dos
revisores.

No se ejecutaron modelos, GPU, embeddings ni evaluación geográfica.

## Selección metadata-only

Se utilizó el inventario Mapillary D004 congelado de 1.655 imágenes. Antes de
descargar se excluyeron:

- IDs y secuencias utilizados en H26–H37;
- imágenes a menos de 75 m de las 37 referencias accesibles H01–H37;
- registros sin secuencia o dimensiones.

El preflight dejó 828 registros, 17 bloques y 35 secuencias. El shortlist se
congeló con:

- 20 slots `I01–I20`;
- 12 bloques de 150 m;
- máximo dos slots por bloque;
- un primario y dos reservas por slot;
- 60 IDs únicos;
- calidad Mapillary, resolución, fecha e ID como desempate;
- sin píxeles, rankings, OSM, candidatos o rendimiento esperado.

Freeze:

`i20-mapillary-selection-sha256-6f1e6d9b4bb8e51409438fcddebc6988f0afc70bb089f44096242288f44f5217`

Los bloques no estaban congelados en la fase anterior; solo estaban congeladas
las reglas. Esta selección materializa por primera vez los bloques y reservas.

## Adquisición

La campaña se vinculó al SHA-256 exacto del shortlist:

`967804408afefb984bef79fb56c384afd041889ccad3054019d577eef2294db2`

Límites:

- 60 descargas como máximo;
- miniatura 1.024 px;
- 8 MB por imagen;
- 480 MB acumulados;
- ejecución secuencial;
- API oficial y token no persistido;
- sin sustituciones adaptativas.

Resultado:

- 60/60 adquiridas;
- 53 nuevas;
- 7 reutilizadas desde caché con SHA-256 verificado;
- 7.704.672 bytes totales;
- 0 fallos.

Cada asset conserva proveedor, ID, secuencia, creador, atribución, licencia,
URL fuente, MIME, resolución, bytes, SHA-256, dHash, hash de metadata, fecha y
retención.

## Calidad geográfica

Las veinte referencias seleccionadas tienen coordenadas de cámara reportadas por
Mapillary y orientación de cámara cuando estaba disponible.

Limitaciones comunes:

- precisión horizontal no reportada;
- heading de fiabilidad desconocida;
- heading de cámara, no orientación corporal;
- coordenada de cámara aproximada, no GT GNSS verificado;
- no representa el centro de una celda ni la posición de un objeto visible.

El paquete geográfico está separado del paquete de anotación.

## Independencia accesible

Se cruzaron manifests explícitos de H01–H37:

- piloto visual H12/H14/H16/H18/H19/H22/H23/H25;
- fixture multicandidato H11;
- selector H16/H23;
- referencias/verificaciones H26–H37.

El índice accesible contiene 549 IDs históricos y 548 hashes exactos/perceptuales
distintos. En el shortlist de 60 se detectaron:

- 3 assets históricos exactos;
- 8 assets implicados en near-duplicates;
- una referencia primaria histórica sustituida por `reserve_1` en I08.

Después de aplicar las reservas congeladas:

- 20 referencias seleccionadas;
- 20 SHA-256 distintos;
- 20 dHash distintos;
- 0 referencias finales marcadas como duplicado exacto o perceptual;
- 15 secuencias para 20 referencias.

El dHash usa `dhash-9x8-grayscale-v1` y umbral Hamming ≤6. Este control no prueba
independencia de escena.

## Separación espacial y escenas

Se cubren 12 bloques. Existen nueve pares de referencias a menos de 75 m; el
mínimo es 14,59 m. Esto ocurre porque el protocolo admite hasta dos observaciones
por bloque y porque 75 m era objetivo, no garantía.

Los nueve pares, todas las referencias finales y sus campos de visión permanecen
en cola de revisión humana para comprobar:

- misma escena o lugar;
- objetos distintivos compartidos;
- encuadres solapados;
- continuidad de secuencia;
- independencia suficiente para el análisis.

No se han aprobado escenas visualmente.

## Ledger ciego

Se preparó un lote de 20 candidatos con:

- UUID opaco;
- compromiso SHA-256;
- MIME y longitud;
- alias HMAC-like no reversible de secuencia para el paquete;
- sin ID de proveedor, coordenadas ni metadata geográfica.

El lote está `unsigned_pending_independent_custodian`. No se ha consultado el
holdout y no existe una respuesta tri-state. Las 20 observaciones permanecen
`PENDING_BLIND_EXCLUSION`.

## Paquete de anotación

Contiene exactamente veinte imágenes de referencia y formularios vacíos. No
contiene coordenadas, secuencias, IDs de proveedor, rankings ni predicciones.

No se generaron descripciones automáticas. Los estados son:

- `PENDING_HUMAN_ANNOTATION`: 20;
- `PENDING_HUMAN_REVIEW`: 20;
- `ELIGIBLE`: 0.

Dos revisores humanos siguen siendo obligatorios. El modelo no puede sustituir
su independencia.

## Presupuesto medido

| Recurso | Consumo |
|---|---:|
| Inventario local consultado | 1.655 registros |
| Metadata requests | 60 |
| Descargas nuevas | 53 |
| Reutilizaciones de caché | 7 |
| Bytes del lote | 7.704.672 |
| Tamaño aproximado del lineage | 10 MB |
| GPU | 0 s |
| Inferencias | 0 |
| Embeddings | 0 |
| Evaluaciones | 0 |

Panoramax no se utilizó: el proyecto solo dispone de normalización offline, no
de cliente remoto, y el snapshot local es insuficiente. No se consultaron otras
fuentes.

## Próximos gates

1. Custodio independiente firma y ejecuta una única consulta ciega por lote.
2. Revisión humana de escena/FOV y de los nueve pares próximos.
3. Anotación española ciega de las veinte referencias supervivientes.
4. Dos revisiones humanas y adjudicación.
5. Freeze de anotación y GT aproximado.
6. Solo si quedan al menos doce observaciones, solicitar autorización separada
   para rankings CT2L y, si se desea Atlas real, para vistas candidatas y VLM.

No debe ejecutarse evaluación mientras `eligible=0`.
