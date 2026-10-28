# Reserva CrossText2Loc Top-100 y techo geográfico

## Congelación sin GT

Se generaron 60 rankings Top-100 exhaustivos desde el `plan.json` saneado:

```text
15 consultas × 2 variantes × 2 galerías = 60 rankings
```

El ranker no abrió dataset, referencias o evaluación. Reutilizó checkpoint y
embeddings visuales congelados. Los 60 prefijos Top-10 coinciden exactamente con
el artefacto histórico, incluidos scores (`max_delta=0`).

Reserva:

```text
h11-h25-topn-sha256-92c2ecc639f4e4d650e55be0b7376f73f06279a23c4f59e210a812a14ad43c14
```

Artefactos en:

```text
results/generated/f5/h11-h25-independent/top100/
```

## Techo GeoRecall exploratorio

La referencia se abrió solo después de congelar Top-100. Son coordenadas de
enlace con incertidumbre desconocida, no GT oficial.

Para `en_cartographic + madrid-50m`, GeoRecall a 50 m:

| K | Hits/15 |
|---:|---:|
| 1 | 2 |
| 5 | 4 |
| 10 | 7 |
| 20 | 8 |
| 50 | 9 |
| 100 | 11 |

Entre rangos 11–100 hay margen máximo para recuperar cuatro consultas adicionales
respecto a Top-10. Top-20 añade una, Top-50 añade dos y Top-100 añade cuatro.
Estas cifras son techo de composición, no resultado VLM/sustitución.

Ninguna política puede recuperar a 50 m las cuatro consultas sin candidato
adecuado dentro del Top-100.

## Cobertura Mapillary de la reserva

Sobre las 15 filas `en_cartographic + madrid-50m`:

| Radio | Slots cubiertos | Candidatos únicos cubiertos |
|---:|---:|---:|
| 25 m | 805/1500 | 126/251 |
| 50 m | 1255/1500 | 207/251 |
| 100 m | 1481/1500 | 247/251 |

La cobertura es proximidad metadata-only, no visibilidad. Candidatos sin cámara
deben permanecer neutrales.

## Plan progresivo

La reserva se divide de forma predeclarada:

```text
Top-10 activo
11–20
21–50
51–100
```

Cada bloque debe completarse antes de abrir el siguiente, sin GT. El plan no
autoriza descargas y no selecciona candidatos por referencia. Antes de sustitución
faltan claims revisados, fotografías, veredictos y una política calibrada en
development independiente.

## Limitaciones

- H11–H25 es development e inspeccionado.
- Referencias de enlace, no GT oficial.
- No hay reserva visual descargada completa.
- No hay política de descarte segura.
- No hay test H26+ todavía.
