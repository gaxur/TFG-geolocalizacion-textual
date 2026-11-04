# Diagnóstico para mejorar Qwen3-VL-8B tras H26–H37

## Resultado confirmado

Top-100 eleva el techo oracle a 10/12 consultas con candidato a menos de 50 m,
pero no mejora el ranking final: ningún candidato de ranks 51–100 entra en
Top-10. La política Top-50 y Top-100 seleccionan β=0,1 y producen las mismas
métricas. El coste Top-100 añade 8.600 inferencias 8B sin beneficio geográfico.

## Causas

- El candidato más próximo tiene rank medio 50,3; varios gaps CT2L son demasiado
  grandes para una suma visual lineal estable.
- 66,7 % de las tareas físicas son `unverifiable`.
- Los 194 claims se marcaron como distintivos; no existe ponderación humana real
  de genericidad.
- No hay claims `visible_text` ni OCR literal, aunque los rótulos son las pistas
  más discriminativas de muchas consultas.
- 55 relaciones se tratan como orientacionales, aunque varias son intrínsecas.
- Solo se usa una imagen por candidato; la mayoría dispone de decenas de vistas y
  varias secuencias en el inventario.
- 44,6 % de asociaciones Top-100 son espacialmente ambiguas y solo 49,4 % tienen
  orientación comparable.
- Una imagen puede proyectarse sobre muchos candidatos y consultas; el soporte
  urbano genérico no identifica una celda.

## Hipótesis descartada

Una reponderación offline por rareza IDF, tipo semántico y contradicción no añade
GeoRecall y reproduce la mejora mínima de 0,37 m. Se detiene por criterio de
parada: la información perdida no puede recuperarse ajustando solo pesos.

## Experimentos priorizados

1. **Comparación pairwise 8B de bajo coste.** Rank 10 contra ranks 11–30 y contra
   una shortlist profunda seleccionada por evidencia visual, sin GT. Salida
   estructurada y máximo dos promociones.
2. **Claims atómicos con OCR.** Separar objeto, atributo, texto visible y marco de
   relación. Requiere nuevas inferencias sobre una muestra piloto, no toda la
   campaña.
3. **Multivista.** Dos o tres secuencias por candidato para los casos con una sola
   vista no informativa. El inventario ofrece varias secuencias para 176/184
   candidatos Top-100, pero requiere nueva selección, overlap gate y presupuesto.
4. **OSM/F3 como prior estructural.** Experimento offline de bajo coste para
   claims cartografiables; no sustituye visibilidad.
5. **Fuentes adicionales.** Panoramax no añade cobertura espacial a Mapillary en
   el snapshot local; Commons puede aportar semántica/monumentos, pero necesita
   snapshot y autorización. KartaView sigue no medible.

H38–H61 permanece sellado. Atlas v3 congelado no se modifica; cualquier mejora
posterior usa un linaje experimental nuevo.

## Resultados del linaje v2

- Reponderación semántica/IDF/contradicción: no añade GeoRecall y reproduce la
  mejora Top-1 media de 0,37 m. Hipótesis descartada.
- Comparación pairwise 8B: 294 llamadas físicas para 355 pares lógicos; 236
  outputs truncados se registran como `unverifiable` sin reparación. Ninguna de
  las 12 políticas globales supera baseline. Hipótesis descartada bajo este
  contrato.
- Prior OSM/F3: la variante OSM aislada γ=0,35 reduce la distancia Top-1 media en
  40,17 m y mejora dos consultas sin degradar Top-1, pero pierde un hit
  GeoRecall@10 a 50 m. No satisface conjuntamente las métricas.
- Fusión visual-OSM v3 con escalas comparables: reproduce la mejora visual
  histórica, sin ganancia adicional. Hipótesis lineal descartada.

## Piloto multivista/OCR

La hipótesis siguiente incorpora nueva información en lugar de nuevos pesos:
dos vistas adicionales y secuencias distintas para ranks 1–20, tipado de claims,
OCR literal y evidencia estructurada. El plan autorizado contiene 437
asociaciones tras excluir tres pares por el gate automático, 117 assets y 7.064
jobs: 5.887 llamadas 8B, 1.177 abstenciones y 726 tareas OCR. La ejecución se
realiza con checkpoint exclusivo; sus resultados pertenecen al linaje
exploratorio y no modifican Atlas v3 congelado.
