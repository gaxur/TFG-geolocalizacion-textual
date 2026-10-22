# F4.5: robustez lingüística técnica de CrossText2Loc

## Objetivo y límites

F4.5 estudia cómo cambia el ranking al modificar de forma controlada el texto.
No mide precisión geográfica: las consultas son sondas técnicas sin ground truth
verificado. Un ranking estable puede ser incorrecto y un cambio ante una
contradicción puede ser razonable sin que conozcamos la ubicación correcta.

El checkpoint, el encoder textual, el preprocesamiento y las matrices visuales
permanecen congelados. Cada texto se compara exhaustivamente con 253 candidatos
de 50 m y 1.115 candidatos de 25 m, sin usar coordenadas para filtrar.

## Dataset controlado

El manifest es `config/madrid_f45_linguistic_robustness.json`:

```text
query_set_id: f4-madrid-linguistic-queries-sha256-0f202067a08aa96acfb16035fb31945e7c23b713848d0f2175140b1dd3ec4038
grupos: 3
variantes: 27
comparaciones anchor-variante por galería: 24
```

Cada grupo parte de una consulta inglesa de F4.2. Las variantes son paráfrasis,
sinónimos, expansión de redacción, acortamiento, eliminación de atributos,
aumento de ambigüedad, contradicción y traducción al español. Todas están
marcadas `technical_controlled`, se revisaron manualmente y declaran las unidades
semánticas preservadas, eliminadas o cambiadas.

Las relaciones se separan en:

- `approximately_equivalent`: intenta conservar los hechos;
- `information_loss`: elimina precisión o atributos;
- `semantic_change`: cambia deliberadamente un hecho.

No se agregan las tres familias como si todas debieran ser invariantes.

## Métricas de estabilidad

Dentro de cada galería y para cada par anchor-variante se calculan:

- coincidencia Top-1;
- número de candidatos compartidos en Top-5 y Top-10;
- Jaccard@5 y Jaccard@10;
- distancia Haversine entre los dos Top-1;
- rango del Top-1 del anchor dentro del Top-10 variante;
- reciprocal rank censurado a Top-10;
- desplazamiento medio de rango entre candidatos compartidos;
- variación absoluta de score para candidatos compartidos;
- delta del mejor score y del margen Top-1/Top-2.

Los score son similitudes coseno, no probabilidades. Un candidato ausente de
Top-10 no recibe un rango inventado. La distancia entre salidas no es error
geográfico.

## Ejecución

El runner batch `scripts/run_f4_linguistic_rankings.sh` carga el checkpoint una
vez por galería y reutiliza `exhaustive_rank` y los validadores F4. Se generaron
27 Top-10 por galería.

```text
50 m: 8,29 s de batch; encoding acumulado 280,80 ms; ranking acumulado 14,78 ms
25 m: 10,28 s de batch; encoding acumulado 289,42 ms; ranking acumulado 144,44 ms
```

Los tiempos acumulados internos excluyen la carga del modelo y no constituyen un
benchmark de latencia de servicio.

Ranking sets:

```text
50 m: f4-madrid-rankings-sha256-2f40090139259177b7dc3d19d8a9d75e3dedfd97ba66e87c8b2758c7fa0e7136
25 m: f4-madrid-rankings-sha256-6d3bd2f0c7fd1ad0aab0ab59a1ef19cca8867d9930c2786db1fab60d8f645724
```

Informes:

```text
50 m: f4-madrid-linguistic-robustness-sha256-2421b0fc1033581be42255953fd990242270996c3d01e422d7591f740dbafd31
25 m: f4-madrid-linguistic-robustness-sha256-923677b89c1e1b217a3642080b700ac1c6b875ae787d07ae3a76a69085221dad
```

## Resultados observados

### Por relación semántica

| Galería | Relación | n | Top-1 igual | Jaccard@10 medio | Distancia Top-1 media |
|---|---|---:|---:|---:|---:|
| 50 m | Aproximadamente equivalente | 12 | 0,167 | 0,184 | 314,9 m |
| 50 m | Pérdida de información | 9 | 0,000 | 0,067 | 387,6 m |
| 50 m | Cambio semántico | 3 | 0,333 | 0,578 | 192,5 m |
| 25 m | Aproximadamente equivalente | 12 | 0,000 | 0,085 | 434,5 m |
| 25 m | Pérdida de información | 9 | 0,000 | 0,006 | 484,6 m |
| 25 m | Cambio semántico | 3 | 0,667 | 0,356 | 37,2 m |

La mayor coincidencia observada para contradicciones no significa que el modelo
las trate mejor. Con solo tres anchors, y sin ubicación verdadera, es una
observación descriptiva que puede depender de los textos y del solapamiento de
las galerías.

### Traducción inglés-español

Ninguna de las tres traducciones conserva Top-1 en ninguna galería.

| Galería | Top-1 igual | Jaccard@5 medio | Jaccard@10 medio | Distancia Top-1 media |
|---|---:|---:|---:|---:|
| 50 m | 0/3 | 0,074 | 0,055 | 207,7 m |
| 25 m | 0/3 | 0,000 | 0,000 | 314,5 m |

Esto no demuestra que el español tenga menor precisión. Solo compara tres
traducciones técnicas con anchors ingleses y el checkpoint procede de Nueva
York. El efecto del idioma está confundido con redacción, tokenización y muestra.

### Check HTTP histórico del MVP

Antes del contrato experimental F5.11 se ejecutó también
`scripts/check_mvp_bilingual.py` contra la API desplegada. Reutilizó los tres
pares inglés-español de F4.5 sobre ambas galerías y comprobó el transporte HTTP,
no precisión geográfica.

| Grupo | Galería | Top-1 igual | Compartidos Top-10 | Jaccard@10 | Distancia entre Top-1 |
|---|---|---:|---:|---:|---:|
| Plaza | 50 m | No | 0 | 0,000 | 111,9 m |
| Plaza | 25 m | No | 0 | 0,000 | 160,0 m |
| Parque | 50 m | No | 1 | 0,053 | 461,0 m |
| Parque | 25 m | No | 0 | 0,000 | 727,7 m |
| Intersección | 50 m | No | 2 | 0,111 | 50,1 m |
| Intersección | 25 m | No | 0 | 0,000 | 56,0 m |

Las 12 peticiones terminaron correctamente. El informe local histórico se guardó
en `results/generated/mvp3/bilingual-check.json`, fuera de Git. Estos valores
describen inestabilidad del ranking: no determinan qué idioma localiza mejor.

F5.11 sustituyó aquel contrato HTTP por una entrada original exclusivamente
española y dos modos: texto original o Qwen `en_cartographic`. Por ello el check
bilingüe ya no es una prueba operativa del MVP actual y se conserva solo como
antecedente F4.5.

## Redacción de consultas cartográficas

Para una galería de imágenes OSM conviene priorizar elementos con posible
representación cartográfica: forma de plazas y parques, calles que desembocan en
un espacio, cruces, zonas peatonales, anchura relativa de vías y densidad de
edificios. Colores, materiales, escaparates, logotipos, carteles, relojes y
detalles de fachada pueden carecer de equivalente en el raster y actuar como
ruido.

Esta observación motivó posteriormente las variantes cartográficas F5, pero no
autoriza eliminar pistas visuales sin conservar el original ni demuestra que una
transformación mejore la precisión. Las variantes se evalúan como rankings
separados; el MVP F5.11 no fusiona resultados ni promedia coordenadas.

### Casos de mayor desplazamiento

- En 50 m, la variante de sinónimos de la intersección desplazó el Top-1 unos
  955,2 m respecto al anchor, con Jaccard@10 de 0,333.
- En 25 m, la paráfrasis de la intersección desplazó el Top-1 unos 919,1 m, con
  Jaccard@10 de 0,250.
- La traducción del caso parque desplazó el Top-1 461,0 m en 50 m y 727,7 m en
  25 m.

Estos son cambios de salida, no errores respecto a la ubicación real.

## Reproducción

1. Validar el query set:

```bash
./.venv-geo/bin/python scripts/validate_f4_linguistic_query_set.py \
  --query-set config/madrid_f45_linguistic_robustness.json
```

2. Ejecutar `scripts/run_f4_linguistic_rankings.sh` una vez por galería,
   proporcionando los bundles visual, catálogo, selección y embeddings
   correspondientes.
3. Congelar con `scripts/freeze_f4_linguistic_rankings.py`.
4. Analizar con `scripts/analyze_f4_linguistic_robustness.py`.

Los resultados se guardan fuera de Git bajo `results/generated/f4/f45/`.

## Limitaciones y siguientes pasos

- Solo existen tres anchors; las 27 variantes no son 27 observaciones
  independientes.
- Las equivalencias semánticas son anotaciones manuales técnicas.
- Top-10 censura desplazamientos más allá de la décima posición.
- No existen métricas de precisión geográfica disponibles.
- D007, D013, D016, D029 y D030 siguen abiertas.
- F4.6 deberá definir el siguiente experimento sin reutilizar estas sondas como
  test final ni seleccionar configuración por la partición reservada.
