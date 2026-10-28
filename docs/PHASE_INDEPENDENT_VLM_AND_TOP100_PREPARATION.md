# Preparación de validación independiente y reserva Top-100

## Auditoría estadística corregida

En los 72 pares ampliados:

- 51 pares: ambos modelos correctos;
- 3: solo 2B correcto;
- 9: solo 8B correcto;
- 9: ambos incorrectos;
- 12 discordancias de corrección y 12 predicciones diferentes.

Por tanto, 2B acierta 54/72 y 8B 60/72. La redacción anterior que combinaba 12
discordancias con 4/9 era inconsistente y queda corregida. McNemar exacto sigue
siendo `p=0,146`; bootstrap agrupado por consulta: delta +0,083,
IC `[+0,028; +0,139]`. Es development asistido por Codex, no confirmación.

## Estado del test independiente

No existe un test independiente reutilizable. H01–H25, SV, sintético OSM, las 24
imágenes Mapillary y H11 visual fueron usados o inspeccionados. Se prepararon:

- `schemas/independent_human_observation.schema.json`;
- `config/independent_h26_collection_template.json`;
- `docs/INDEPENDENT_H26_COLLECTION_PROTOCOL.md`.

La plantilla está vacía deliberadamente. Recomendación: 12 observaciones
development H26–H37 y 24 test sellado H38–H61, agrupadas por bloques espaciales,
con evidencia propia, posición del observador y orientación verificadas. La
anotación visual final debe ser ciega, con dos revisores, sin propuestas AI
visibles.

No se puede preparar todavía un paquete Codex final porque faltan las nuevas
observaciones, claims, rankings y fotografías candidatas. Cuando existan, el
constructor portable actual puede reutilizarse tras congelar P0–P5.

## Reserva Top-100

Se congelaron 60 rankings Top-100 exhaustivos desde el plan saneado, sin abrir
referencias. Los 60 prefijos Top-10 coinciden exactamente con el baseline.

Para `en_cartographic + madrid-50m`:

| K | Recall exacto | GeoRecall 50 m |
|---:|---:|---:|
| 1 | 0/15 | 2/15 |
| 5 | 1/15 | 4/15 |
| 10 | 3/15 | 7/15 |
| 20 | 5/15 | 8/15 |
| 50 | 6/15 | 9/15 |
| 100 | 10/15 | 11/15 |

La sustitución podría mejorar como máximo GeoRecall@10 de 7/15 a 11/15 en esta
muestra exploratoria si identificase perfectamente candidatos 11–100. No es un
resultado del VLM.

## Cobertura Mapillary Top-100

Para 1.500 slots Top-100:

- 805 cubiertos a 25 m;
- 1.255 a 50 m;
- 1.481 a 100 m.

Hay 251 candidatos únicos y 247 tienen una cámara a ≤100 m. Esto hace viable una
reserva visual progresiva, pero no demuestra visibilidad ni autoriza descargas.
El plan se divide en bloques 1–10, 11–20, 21–50 y 51–100, sin GT y sin saltar
retrospectivamente a candidatos favorables.

## Reranking ejecutado

La sensibilidad positiva H11 con `lambda_pos` 0/0,05/0,10/0,20 y
`lambda_neg=0` no cambió GeoRecall@1/5/10, ni distancia Top-1. 2B no cambió orden;
8B solo intercambió rangos 9/10 con 0,20. El candidato más próximo estaba a
237,26 m; H11 era irrecuperable a 50 m dentro del Top-10.

No se ejecuta descarte/sustitución real: faltan claims, imágenes y anotaciones de
la reserva, contradicción suficientemente validada y parámetros congelados en un
development separado.

## Próxima acción humana

1. Decidir D004 frente a Madrid ampliado antes de H26+.
2. Recoger 12 development + 24 test con protocolo de campo.
3. Congelar rankings Top-100 sin GT.
4. Revisar nuevo alcance Mapillary y preparar paquetes ciegos.
5. Anotar test sin propuestas 2B/8B/Codex visibles.
6. Congelar políticas en development y abrir test una sola vez.
