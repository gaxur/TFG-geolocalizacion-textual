# Índices espaciales y vectoriales: opciones de implementación

## Estado y alcance

Este documento describe dos índices para etapas distintas del proyecto:

| Índice | Datos que organiza | Uso previsto | Estado en el TFG |
|---|---|---|---|
| STRtree de Shapely | Geometrías OSM | Acelerar las asociaciones geométricas entre objetos OSM y celdas en F3 | Implementado y validado en F3 conforme a D050 |
| HNSW | Embeddings vectoriales | Posible aceleración aproximada del ranking texto–imagen de CrossText2Loc | Alternativa experimental; no seleccionada ni implementada |

No son intercambiables: STRtree genera pares espaciales candidatos para comprobar
predicados geométricos; HNSW busca vectores próximos. Ninguno reemplaza al otro,
la generación geográfica de candidatos ni la evaluación. La preparación de estos
índices no modifica los pesos congelados de CrossText2Loc.

## STRtree para las asociaciones geométricas de F3

D050 ya fija STRtree como índice espacial temporal de F3. Su propósito es
reducir las comparaciones geométricas: el árbol devuelve las geometrías OSM cuyos
sobres espaciales pueden intersectar una celda; después se comprueba la
intersección exacta con GEOS. El índice no define el resultado canónico: las
asociaciones siguen las reglas geométricas de D050 y se ordenan por identidad
OSM antes de escribirse.

Un patrón de implementación con Shapely 2.x sería:

```python
from shapely import STRtree

# Mantener una correspondencia estable entre cada posición y su objeto OSM.
type_order = {"node": 0, "way": 1}
osm_rows = sorted(osm_rows, key=lambda row: (type_order[row.osm_type], int(row.osm_id)))
osm_geometries = [row.geometry for row in osm_rows]
tree = STRtree(osm_geometries)

for cell in sorted(cells, key=lambda item: item.candidate_id):
    # query devuelve posiciones cuyos sobres envolventes intersectan la celda.
    # Se ordenan antes de ejecutar los predicados exactos.
    positions = sorted(set(int(i) for i in tree.query(cell.geometry)))
    for position in positions:
        osm = osm_rows[position]
        if osm.geometry.intersects(cell.geometry):
            write_association(osm, cell, exact_predicates=True)
```

Es un esquema orientativo que debe adaptarse a los contratos F1/F2 y a D049/D050;
no es código implementado. La producción real deberá además calcular y
serializar los predicados y distancias definidos por D050, propagar el contexto
permitido de relations, validar los outputs y registrar la versión/hash de
Shapely y GEOS. Se fijarán ambas versiones tras el preflight para Python 3.12 y
Linux `aarch64`. No se persistirá el orden interno devuelto por STRtree.

## HNSW como alternativa para la recuperación CrossText2Loc

HNSW podría estudiarse si la comparación exacta de una consulta contra una
galería grande de embeddings visuales se vuelve demasiado lenta. Para vectores
normalizados, el producto escalar equivale a la similitud coseno; un índice HNSW
configurado para producto interno puede aproximar la búsqueda de los vectores de
imagen más similares al embedding de texto. Una implementación local posible es
`hnswlib`; Milvus es otra opción de servicio, pero no se selecciona ninguna en
este documento.

La ruta de referencia seguirá siendo la comparación exhaustiva:

```python
scores = image_embeddings @ text_embedding
topk_positions = scores.argsort()[::-1][:k]
```

Una integración exploratoria con `hnswlib` podría seguir este patrón. Si la
preselección no retiene candidatos, la consulta devuelve una lista vacía y no
invoca el índice.

```python
import hnswlib
import numpy as np

vectors = np.asarray(image_embeddings, dtype=np.float32)
query = np.asarray(text_embedding, dtype=np.float32).reshape(1, -1)

index = hnswlib.Index(space="ip", dim=vectors.shape[1])
index.init_index(max_elements=num_candidates, M=M, ef_construction=ef_construction)
index.add_items(vectors, ids=internal_labels)
index.set_ef(ef_search)

# allowed_labels contiene solo las etiquetas que corresponden a los
# candidate_id admitidos por la preselección geográfica de esta consulta.
labels, distances = index.knn_query(
    query,
    k=min(k, len(allowed_labels)),
    filter=lambda label: int(label) in allowed_labels,
)
similarities = 1.0 - distances[0]  # distancia que devuelve hnswlib en espacio ip
```

El fragmento es ilustrativo, no una configuración aprobada: `M`,
`ef_construction` y `ef_search` deben determinarse mediante mediciones, y el
filtrado por etiquetas depende del backend elegido. Cada etiqueta interna debe
mapearse de forma versionada a un `candidate_id`; también se conservarán el hash
del checkpoint, el preprocesamiento, la dimensión, la métrica, la versión del
índice y sus parámetros.

La restricción geográfica debe aplicarse dentro de la búsqueda aproximada cuando
el backend lo permita. Recuperar primero un Top-K global y filtrar después por
`candidate_id` puede dejar menos de K candidatos válidos y perder buenos
resultados. Si no hay un filtro eficiente para la galería permitida, se usará la
comparación exacta sobre ese subconjunto. Para un catálogo pequeño, esta última
opción es preferible hasta que las mediciones justifiquen el índice.

## Criterios para evaluar HNSW antes de adoptarlo

HNSW permanece como hipótesis de optimización, no como decisión del TFG. Antes
de incorporarlo se deberá:

1. Medir latencia y memoria de la comparación exacta sobre una galería y carga
   representativas.
2. Comparar HNSW con esa misma galería, consultas, checkpoint y preselección.
3. Medir `Recall@K` del índice aproximado frente al ranking exacto, además del
   resultado geográfico de extremo a extremo.
4. Medir el efecto del filtro por `candidate_id`, la latencia de construcción y
   actualización, y el tamaño del artefacto.
5. Registrar versiones, parámetros, hashes y resultados en
   [`EXPERIMENTS.md`](EXPERIMENTS.md).

La coordenada real de una consulta no participará en la construcción de la
galería ni en la preselección. Si las mediciones no muestran una ventaja útil,
se conservará el ranking exhaustivo. El índice, en caso de estudiarse, se
aplicaría solo a embeddings visuales de CrossText2Loc; la extracción vectorial
de GOTPR opera sobre embeddings de grafos y es un componente separado.

## Referencias del proyecto

- [Decisión D050 y contrato F3](PHASE3_GEOMETRIC_ASSOCIATIONS.md): asociaciones
  geométricas y uso del índice espacial temporal.
- [Dataset de Madrid](MADRID_DATASET.md): flujo F1–F3 y preselección online.
- [Requisitos de modelos y datos](DATASET_MODEL_REQUIREMENTS.md): interfaces y
  estado auditado de CrossText2Loc y GOTPR.
