# Protocolo remoto Mapillary H26-H61

## Alcance y corrección metodológica

H26-H61 se realizará completamente en remoto. No requiere desplazamiento,
fotografías propias ni mediciones GNSS. D004 y la galería principal de 50 m se
mantienen. La bbox B no se usa ni se amplía Madrid.

La unidad de referencia es una **cámara Mapillary de terceros**. Su coordenada
reportada aproxima la posición del observador, pero no es una medición
centimétrica ni una posición corporal independiente. La precisión permanece
desconocida salvo que un metadato explícito indique otra cosa. Este protocolo
sustituye para H26-H61 el supuesto presencial de la plantilla v1, que se conserva
como legado y no obliga a rehacer artefactos históricos.

## Particiones

- H26-H37: 12 consultas development.
- H38-H61: 24 consultas de test independiente sellado.
- Bloques de 150 m calculados en EPSG:25830.
- Exclusión objetivo de H01-H25/SV y separación entre referencias nuevas: 75 m.
- Máximo dos referencias por bloque y una columna de guardia.
- Development y test no comparten bloques.

El selector usa exclusivamente el inventario regional congelado y metadatos de
cámara. No recibe rankings CrossText2Loc, resultados VLM, errores del baseline,
distancia a candidatos de galería, píxeles ni `quality_score`. La disponibilidad
de una secuencia Mapillary permite construir una consulta, pero la cobertura del
candidato correcto no interviene en la selección.

## Referencia y verificación

### Imágenes de referencia

Se usan solo para seleccionar la ubicación, redactar la descripción española,
extraer y revisar claims, y documentar la coordenada y el heading de cámara. No
se entregan al VLM.

### Imágenes de verificación

Se reservan solo para evaluar candidatos CrossText2Loc con Qwen3-VL. Deben tener
otro `image_id` y otra `sequence_id` respecto a la referencia. Los conjuntos de
IDs de referencia y verificación son globalmente disjuntos.

La separación por secuencia es solo un control metadata-only. Tras una descarga
autorizada se exigen SHA-256, hash perceptual y revisión humana del solapamiento.
Recortes, transformaciones, duplicados exactos, imágenes casi idénticas o vistas
con solapamiento invalidante se rechazan. Una consulta sin evidencia independiente
se conserva como `no_coverage` o exploratoria; nunca reutiliza silenciosamente su
referencia.

## Inventario congelado actual

La selección v2 generada solo con artefactos locales contiene:

| Elemento | Cantidad |
|---|---:|
| Referencias | 36 |
| Verificaciones planificadas | 43 |
| IDs únicos totales | 79 |
| Consultas con dos secuencias metadata-only | 19 |
| Consultas con una secuencia metadata-only | 5 |
| Consultas sin secuencia independiente a 50 m | 12 |

Estos recuentos no acreditan utilidad visual ni independencia pixel a pixel. El
inventario y los paquetes locales están en
`results/generated/mapillary/remote-h26-h61-v2/`, fuera de Git.

## Anotación remota

`scripts/build_remote_annotation_package.py` genera tres paquetes estáticos:

- `human`: descripción, claims, orientación, incertidumbres y decisión humana.
- `codex`: añade instrucciones para propuestas locales `AI-proposed`.
- `blind-test`: oculta propuestas IA y se destina a revisión independiente.

La interfaz muestra la fotografía de referencia cuando esté autorizada, sus
metadatos, una representación local de D004 y un enlace opcional a OSM. Exporta
JSON canónico; la persona revisora no edita estructuras complejas a mano.

Codex puede proponer descripciones, claims, objetos y ambigüedades, pero sus
salidas conservan `human_validated: false` hasta revisión. Para H38-H61 se
recomiendan dos revisores distintos, ciegos a rankings, cosenos y resultados 2B/8B.

## Freeze y apertura del test

1. Congelar selección espacial, inventario y roles de imagen.
2. Obtener autorización específica y adquirir sin sustitución retrospectiva.
3. Calcular hashes y revisar independencia visual.
4. Anotar H26-H37 y calibrar K, prompt, umbrales y política solo en development.
5. Congelar checkpoints, inputs, parámetros y política de promoción.
6. Anotar H38-H61 con paquete ciego y dos revisores cuando sea viable.
7. Sellar el test por SHA-256.
8. Abrirlo una sola vez para la comparación final; repeticiones posteriores se
   etiquetan como análisis exploratorio.

## Evaluación e incertidumbre

La distancia se calcula en EPSG:25830 y distingue coordenada reportada por
Mapillary, referencia aproximada del observador, centro de celda y candidato
recuperado. El GT no entra en retrieval, verificación, promoción o descarte.

La evaluación primaria a 50 m incluirá una bandera de precisión desconocida y
se acompañará de sensibilidad a 25/50/75/100 m. Si una revisión detecta que la
incertidumbre impide interpretar 50 m, la consulta se informa separadamente; no
se inventa una precisión ni se corrige con el candidato recuperado.

## Limitaciones frente a campo

- La persona que redacta no estuvo físicamente en el lugar.
- La vista depende del encuadre, fecha, recorrido y cobertura de contribuidores.
- La coordenada de cámara puede tener error desconocido.
- El heading de cámara no equivale a orientación corporal y su fiabilidad puede
  ser desconocida.
- Referencia y verificación proceden del mismo proveedor y área, aunque se
  separen por IDs, secuencias, hashes y revisión.
- El muestreo excluye lugares sin Mapillary y por tanto no representa todo D004.
- Una imagen remota permite una descripción de lo visible en esa captura, no de
  una experiencia peatonal completa ni del estado actual de la calle.

## Adquisición pendiente

No se ha descargado ninguna fotografía nueva. La autorización del piloto de 24
miniaturas no se reutiliza. El plan v2 solicita aprobación para 79 IDs exactos,
miniaturas de hasta 1.024 px, retención local, transferencia privada, anotación y
comparación fija 2B/8B sin entrenamiento ni dataset público.

Estimación basada en las 24 miniaturas del piloto: 8.750.231 bytes. Máximo duro:
632.000.000 bytes. La primera cifra es una extrapolación, no una garantía.

## Archivos

- Schema canónico: `schemas/remote_mapillary_observation.schema.json`.
- Plantilla: `config/remote_h26_h61_campaign_template.json`.
- Selector: `src/tfg_phase0/remote_mapillary_campaign.py`.
- Preparación: `scripts/prepare_remote_mapillary_campaign.py`.
- Plan offline: `scripts/plan_remote_mapillary_acquisition.py`.
- Anotación: `scripts/build_remote_annotation_package.py`.
- Validación: `scripts/validate_remote_campaign.py`.
