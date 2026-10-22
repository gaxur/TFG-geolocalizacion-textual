# F5.9: H01 y H02 con referencias Street View

## Relación entre H01–H10 y H11–H25

H01–H10 constituye la muestra humana exploratoria de desarrollo de F5.9. Se
construyó en dos incrementos: H01–H02, que además incluyó traducciones inglesas
humanas, y H03–H10, orientado a relaciones egocéntricas. Sus resultados se
inspeccionaron para consolidar métricas y proponer la candidata Qwen de F5.10;
por tanto, no debe reutilizarse como validación independiente de esa propuesta.

H11–H25 es una campaña posterior y separada que compara únicamente
`es_original` frente a `en_cartographic`. No comparte panoramas ni referencias a
menos de 25 m con F5.7/H01–H10 según la auditoría previa. Aporta evidencia nueva,
pero sus coordenadas de enlace, revisión visual pendiente y el caso interior H16
impiden tratarla como Ground Truth oficial. Su protocolo y resultados están en
[PHASE_H11_H25_EVALUATION.md](PHASE_H11_H25_EVALUATION.md).

## Alcance y referencia

F5.9 incorpora dos descripciones humanas y sus traducciones inglesas aportadas
por el responsable. Es una evaluación exploratoria separada de F5.4. Las
posiciones de panorama no están verificadas de forma independiente y su
incertidumbre es desconocida.

Se conservan por separado la coordenada proporcionada o marcador y la coordenada
incluida en el enlace del panorama. La **coordenada de panorama** se usa como
referencia experimental porque representa el punto de vista asociado a la
descripción. No se declara posición de cámara verificada ni Ground Truth oficial.

| Caso | Distancia marcador–panorama | D004 | Cobertura 25/50 m de panorama |
|---|---:|---|---|
| H01 | 0,79 m | ambas coordenadas dentro | fuera de cobertura residual / fuera de cobertura residual |
| H02 | 4,57 m | ambas coordenadas dentro | `assigned` / `assigned` |

H01 está dentro de la bbox D004 pero en su franja norte no cubierta por las
celdas completas. Por ello admite Haversine y GeoRecall, pero no Recall exacto.
H02 admite ambas métricas. No se sustituye la referencia de H01 por una celda
cercana.

## Textos y controles

Qwen3-8B, revisión `b968826d...`, generó ocho derivados reales con los mismos
prompts y parámetros de F5.7. Las 12 entradas finales fueron:

1. `es_original`, humano.
2. `en_human_control`, traducción humana independiente.
3. `es_cartographic`, Qwen.
4. `en_conventional`, Qwen.
5. `en_toponym_preserved`, Qwen.
6. `en_cartographic`, Qwen.

`es_cartographic` fue idéntica al original en ambos casos. Las salidas inglesas
conservaron las relaciones egocéntricas y los nombres explícitos. Se protegieron
solo nombres presentes en el texto: `Cercanías`, `Pans & Company` y `Schweppes`.
No se usaron coordenadas, panorama, heading, pitch, OSM o candidatos para
enriquecer los prompts.

Qwen tardó 86,71 s en cargar; las ocho generaciones tuvieron 3,47 s de media y
3,34 s de mediana. Todas quedaron `generated` y pendientes de revisión semántica
humana.

## Resultados individuales

CrossText2Loc produjo 24/24 rankings reales mediante coseno exhaustivo, Top-10,
sin prefiltrado, reranking, VLM o fine-tuning.

| Caso | Galería | Control | Rango exacto | Geo@10 50 m | Geo@10 100 m | Top-1 | Mín. Top-10 |
|---|---|---|---:|---:|---:|---:|---:|
| H01 | 25 m | `es_original` | n/d | no | no | 422,70 m | 126,34 m |
| H01 | 25 m | `en_human_control` | n/d | sí | sí | 408,51 m | 30,19 m |
| H01 | 25 m | `es_cartographic` | n/d | no | no | 422,70 m | 126,34 m |
| H01 | 25 m | `en_conventional` | n/d | no | no | 408,51 m | 200,80 m |
| H01 | 25 m | `en_toponym_preserved` | n/d | no | no | 560,42 m | 373,95 m |
| H01 | 25 m | `en_cartographic` | n/d | no | no | 422,70 m | 372,78 m |
| H01 | 50 m | `es_original` | n/d | no | no | 426,74 m | 241,77 m |
| H01 | 50 m | `en_human_control` | n/d | no | sí | 763,28 m | 55,24 m |
| H01 | 50 m | `es_cartographic` | n/d | no | no | 426,74 m | 241,77 m |
| H01 | 50 m | `en_conventional` | n/d | no | sí | 763,28 m | 55,24 m |
| H01 | 50 m | `en_toponym_preserved` | n/d | no | no | 605,75 m | 379,62 m |
| H01 | 50 m | `en_cartographic` | n/d | no | no | 605,75 m | 241,77 m |
| H02 | 25 m | `es_original` | 9 | sí | sí | 25,22 m | 6,93 m |
| H02 | 25 m | `en_human_control` | fuera Top-10 | no | no | 390,94 m | 174,66 m |
| H02 | 25 m | `es_cartographic` | 9 | sí | sí | 25,22 m | 6,93 m |
| H02 | 25 m | `en_conventional` | fuera Top-10 | no | no | 390,94 m | 175,45 m |
| H02 | 25 m | `en_toponym_preserved` | fuera Top-10 | no | no | 390,94 m | 174,66 m |
| H02 | 25 m | `en_cartographic` | fuera Top-10 | no | no | 377,63 m | 174,66 m |
| H02 | 50 m | `es_original` | 3 | sí | sí | 41,56 m | 23,49 m |
| H02 | 50 m | `en_human_control` | fuera Top-10 | no | sí | 350,02 m | 81,52 m |
| H02 | 50 m | `es_cartographic` | 3 | sí | sí | 41,56 m | 23,49 m |
| H02 | 50 m | `en_conventional` | fuera Top-10 | no | sí | 350,02 m | 81,52 m |
| H02 | 50 m | `en_toponym_preserved` | fuera Top-10 | no | sí | 188,04 m | 81,52 m |
| H02 | 50 m | `en_cartographic` | 7 | sí | sí | 188,04 m | 23,49 m |

El JSON y el HTML conservan las 240 candidatas individuales con rango,
`candidate_id`, coordenadas, coseno original, distancia Haversine y pertenencia a
los radios de 50/100 m. El coseno no se interpreta como probabilidad.

## Inglés humano frente a Qwen

En H01, el inglés humano mejora claramente el mínimo Top-10 frente al español:
30,19 m frente a 126,34 m en 25 m, y 55,24 m frente a 241,77 m en 50 m. Qwen
`en_conventional` reproduce el resultado humano en 50 m, pero no en 25 m. Las
variantes protegida y cartográfica no reproducen la mejora.

En H02 ocurre lo contrario: el español alcanza 6,93/23,49 m y Recall exacto
Top-10 en ambas galerías; el inglés humano empeora a 174,66/81,52 m. Qwen
`en_conventional` y `en_toponym_preserved` reproducen aproximadamente ese peor
comportamiento. `en_cartographic` mejora respecto al inglés humano solo en 50 m,
recuperando la celda exacta en rango 7 y mínimo de 23,49 m.

Por tanto, **la traducción al inglés no mejora consistentemente la recuperación
Top-10**. Qwen reproduce algunas tendencias del inglés humano, pero tampoco de
forma estable entre casos y galerías. Dos observaciones no permiten seleccionar
idioma o variante definitiva.

## Artefactos

```text
results/generated/f5/f59-h01-h02/
├── inputs/{dataset.json,query-dataset.json,variant-template.json}
├── qwen/<run_id>/{derived-sidecar.json,run.json}
├── control-plan.json
├── rankings.json
└── final/{evaluation.json,report.html,manifest.json}
```

Evaluación:

```text
f59-exploratory-evaluation-sha256-3dabf819cfa2ba78e3b8b859683c4e70d060a462f888addf3178261d15a5e8ac
```

Todos los resultados son exploratorios. H01/H02 continúan pendientes de revisión
de correspondencia visual, orientación y posición de cámara. No se cambia la
variante predeterminada de la aplicación.

## Ampliación orientada H03–H10

La ampliación incorpora ocho descripciones humanas con izquierda, derecha,
delante/frente y, en H05/H10, detrás. Los ocho panoramas están dentro de D004 y
`assigned` en ambas galerías. Heading y pitch se conservan para auditoría, pero
no se envían a Qwen ni CrossText2Loc y no se convierten a cardinales.

Nombres propios anotados exclusivamente desde el texto:

- H05: `Hotel Anaco`.
- H06: `El Corte Inglés`.
- H09: `Pisco Sour Cocina Peruana`.
- H10: `La Vinoteca`.

Qwen generó 32/32 transformaciones. Las 40 variantes conservaron las relaciones
egocéntricas en la auditoría automática. Las variantes protegidas conservaron
literalmente los nombres. `en_conventional` tradujo `Pisco Sour Cocina Peruana`
a `Pisco Sour Peruvian Cuisine`; el cambio nominal se registra y no se presenta
como preservación literal.

Cinco de ocho `es_cartographic` fueron idénticas al original: H03, H04, H08,
H09 y H10. CrossText2Loc produjo 80/80 rankings y 800 candidatas individuales.

### Resultados agregados H03–H10

| Galería | Variante | Geo@10 50 m | Geo@10 100 m | R@10 exacto | Mín. Top-10 medio | Mediana |
|---|---|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 0,375 | **0,500** | 0,125 | 200,48 m | 150,87 m |
| 25 m | `es_cartographic` | 0,375 | **0,500** | 0,000 | 198,78 m | 149,14 m |
| 25 m | `en_conventional` | 0,375 | 0,375 | 0,125 | 166,03 m | 192,65 m |
| 25 m | `en_toponym_preserved` | 0,375 | 0,375 | 0,125 | 160,47 m | 185,12 m |
| 25 m | `en_cartographic` | 0,375 | 0,375 | 0,000 | **157,11 m** | **138,63 m** |
| 50 m | `es_original` | **0,375** | 0,500 | 0,125 | 132,60 m | 122,11 m |
| 50 m | `es_cartographic` | 0,250 | 0,500 | 0,125 | 138,41 m | 133,33 m |
| 50 m | `en_conventional` | **0,375** | 0,500 | **0,250** | 123,60 m | 139,50 m |
| 50 m | `en_toponym_preserved` | **0,375** | 0,375 | **0,250** | 146,69 m | 194,43 m |
| 50 m | `en_cartographic` | **0,375** | **0,625** | **0,250** | **115,27 m** | **76,91 m** |

Según el orden D075, no hay ganadora en 25 m a 50 m: todas empatan. A 100 m,
las variantes españolas lideran en 25 m, mientras `en_cartographic` lidera en
50 m. Esta inversión impide seleccionar una única transformación sin decidir
antes cómo resolver el compromiso de galería/radio.

### Resultados individuales H03–H10

La siguiente tabla muestra el mínimo Top-10 en metros; `✓50` implica también
`✓100`, `✓100` solo indica distancia entre 50 y 100 m y `—` supera 100 m.

| Caso | Galería | `es_original` | `es_cartographic` | `en_conventional` | `en_toponym_preserved` | `en_cartographic` |
|---|---|---:|---:|---:|---:|---:|
| H03 | 25 m | 52,85 ✓100 | 52,85 ✓100 | 214,37 — | 214,37 — | 106,34 — |
| H03 | 50 m | 38,89 ✓50 | 38,89 ✓50 | 214,95 — | 214,95 — | 214,95 — |
| H04 | 25 m | 347,35 — | 347,35 — | 238,59 — | 251,22 — | 251,22 — |
| H04 | 50 m | 188,15 — | 188,15 — | 188,15 — | 247,10 — | 247,10 — |
| H05 | 25 m | 277,50 — | 245,43 — | 170,93 — | 155,88 — | 170,93 — |
| H05 | 50 m | 243,98 — | 240,53 — | 188,54 — | 188,54 — | 62,96 ✓100 |
| H06 | 25 m | 5,20 ✓50 | 23,70 ✓50 | 5,20 ✓50 | 5,20 ✓50 | 23,70 ✓50 |
| H06 | 50 m | 16,15 ✓50 | 16,15 ✓50 | 16,15 ✓50 | 16,15 ✓50 | 16,15 ✓50 |
| H07 | 25 m | 44,04 ✓50 | 44,04 ✓50 | 300,01 — | 300,01 — | 305,59 — |
| H07 | 50 m | 28,61 ✓50 | 78,51 ✓100 | 90,85 ✓100 | 200,31 — | 90,85 ✓100 |
| H08 | 25 m | 39,99 ✓50 | 39,99 ✓50 | 17,36 ✓50 | 17,36 ✓50 | 17,36 ✓50 |
| H08 | 50 m | 56,07 ✓100 | 56,07 ✓100 | 23,41 ✓50 | 23,41 ✓50 | 23,41 ✓50 |
| H09 | 25 m | 248,89 — | 248,89 — | 38,90 ✓50 | 38,90 ✓50 | 38,90 ✓50 |
| H09 | 50 m | 188,66 — | 188,66 — | 28,17 ✓50 | 28,17 ✓50 | 28,17 ✓50 |
| H10 | 25 m | 588,00 — | 588,00 — | 342,87 — | 300,86 — | 342,87 — |
| H10 | 50 m | 300,29 — | 300,29 — | 238,56 — | 254,92 — | 238,56 — |

Qwen mejora especialmente H09 y, en 50 m, H05/H08. Empeora H03 y H07 con las
variantes inglesas. H04/H10 permanecen lejos en todas las variantes. H06 es
robusto en todas. Estos cambios no demuestran comprensión de orientación: pueden
deberse al idioma, vocabulario, longitud, nombres o coincidencia cartográfica.

### Comparación pareada frente a `es_original`

| Galería | Variante | Geo50 mejora/empeora | Geo100 mejora/empeora | Mín. Top-10 mejora/empeora | Delta medio mínimo |
|---|---|---:|---:|---:|---:|
| 25 m | `es_cartographic` | 0/0 | 0/0 | 1/1 | −1,70 m |
| 25 m | `en_conventional` | 1/1 | 1/2 | 5/2 | −34,45 m |
| 25 m | `en_toponym_preserved` | 1/1 | 1/2 | 5/2 | −40,00 m |
| 25 m | `en_cartographic` | 1/1 | 1/2 | 5/3 | −43,37 m |
| 50 m | `es_cartographic` | 0/1 | 0/0 | 1/1 | +5,81 m |
| 50 m | `en_conventional` | 2/2 | 1/1 | 4/2 | −9,00 m |
| 50 m | `en_toponym_preserved` | 2/2 | 1/2 | 4/3 | +14,09 m |
| 50 m | `en_cartographic` | 2/2 | 2/1 | 4/3 | −17,33 m |

### Agregado exploratorio común H01–H10

El control inglés humano H01/H02 se excluye para comparar las cinco variantes
comunes. H01 sigue fuera del denominador de Recall exacto, pero participa en
GeoRecall y Haversine.

| Galería | Variante | Geo@10 50 m | Geo@10 100 m | R@10 exacto | Mín. Top-10 medio | Mediana |
|---|---|---:|---:|---:|---:|---:|
| 25 m | `es_original` | **0,400** | **0,500** | **0,222** | 173,71 m | **89,60 m** |
| 25 m | `es_cartographic` | **0,400** | **0,500** | 0,111 | **172,35 m** | **89,60 m** |
| 25 m | `en_conventional` | 0,300 | 0,300 | 0,111 | 170,45 m | 188,12 m |
| 25 m | `en_toponym_preserved` | 0,300 | 0,300 | 0,111 | 183,24 m | 194,51 m |
| 25 m | `en_cartographic` | 0,300 | 0,300 | 0,000 | 180,43 m | 172,79 m |
| 50 m | `es_original` | **0,400** | 0,500 | 0,222 | 132,60 m | 122,11 m |
| 50 m | `es_cartographic` | 0,300 | 0,500 | 0,222 | 137,25 m | 133,33 m |
| 50 m | `en_conventional` | 0,300 | **0,600** | 0,222 | **112,55 m** | 86,19 m |
| 50 m | `en_toponym_preserved` | 0,300 | 0,400 | 0,222 | 163,47 m | 194,43 m |
| 50 m | `en_cartographic` | **0,400** | **0,600** | **0,333** | 118,74 m | **76,91 m** |

Para la prioridad estricta de 50 m, `es_original` es la opción más consistente:
lidera o empata en ambas galerías y no requiere Qwen. A 100 m en la galería de
50 m, `en_conventional` y `en_cartographic` mejoran hasta 0,600; no lo hacen en
25 m, donde caen a 0,300 frente al 0,500 español.

## Relación con F5.7 y F5.5c

F5.7 ya favorecía variantes españolas a 100 m y `es_cartographic`/variantes
inglesas a 50 m solo en la galería de 50 m, pero tenía cuatro referencias
aproximadas. F5.5c development favorecía `es_original` a 50 m y mostraba una
ventaja `es_cartographic` a 100 m en 50 m. H01–H10 refuerza la estabilidad del
español a 50 m y vuelve a mostrar ventajas inglesas dependientes de la galería a
100 m. Las poblaciones no se agregan: F5.5c sigue siendo sintético OSM y F5.7
usa otro conjunto documental aproximado.

## Decisión pendiente

La evidencia humana orientada sigue sin justificar una transformación Qwen única
para el MVP. Si D075 mantiene prioridad estricta de 50 m, `es_original` es la
candidata provisional más defendible por GeoRecall y simplicidad. Si se prioriza
100 m exclusivamente en la galería de 50 m, `en_cartographic` o
`en_conventional` merecen estudio adicional.

El experimento mínimo siguiente debería reservar nuevas observaciones humanas
con referencias verificadas y comparar previamente solo `es_original` frente a
la variante Qwen que el responsable elija como candidata. Para estudiar
orientación de forma causal harían falta pares controlados con el mismo lugar y
objetos, variando o eliminando relaciones egocéntricas con heading revisado. El
pipeline actual no consume heading y estos resultados no prueban comprensión de
izquierda/derecha/delante/detrás.

Artefactos adicionales:

```text
results/generated/f5/f59-h03-h10/
├── inputs/{dataset.json,query-dataset.json,variant-template.json}
├── qwen/<run_id>/{derived-sidecar.json,run.json}
├── variant-plan.json
├── rankings.json
└── final/{evaluation-h03-h10.json,evaluation-h01-h10.json,report-*.html,manifest.json}
```

Identidades:

```text
f59-oriented-evaluation-sha256-dee28ab40ca0bb04562dfff16a4fdb11a2535816a5f016081936c12ff3f4ace7
f59-h01-h10-evaluation-sha256-3628ec43f32de33d20bb96529e5218194641ae5344fc497680c78df056e992cf
```
