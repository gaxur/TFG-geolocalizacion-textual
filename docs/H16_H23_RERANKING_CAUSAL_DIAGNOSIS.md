# Diagnóstico causal del reranking visual H16–H23

## Alcance

Este diagnóstico reutiliza exclusivamente los resultados congelados de
H16–H23. No ejecuta nuevas inferencias ni usa ground truth para calcular
puntuaciones. Las dos consultas son development seleccionadas
retrospectivamente y no constituyen validación independiente.

## Fórmula anterior

El reranking normaliza la similitud CT2L mediante min-max sobre Top-50 y aplica:

```text
score = CT2L_normalizado + 0,2 × evidencia_positiva
```

La evidencia positiva es la proporción ponderada de claims soportados: 1 para
claims distintivos y 0,5 para genéricos. Una secuencia puede soportar cada claim
una vez; conflicto, `unverifiable`, fallo y ausencia son neutrales. La evidencia
negativa se calcula, pero su peso es cero.

## Causas confirmadas

1. El margen entre el peor Top-10 y el mejor candidato externo quedó entre 0,030
   y 0,063 después del bonus. Ningún candidato externo superó la frontera.
2. En varios casos ranks 10 y 11 recibieron la misma evidencia, por lo que el
   bonus no alteró su diferencia CT2L.
3. El reranker anterior no descuenta soporte compartido: una fotografía ambigua
   puede elevar varios candidatos vecinos a la vez.
4. El número de secuencias independientes se registraba, pero no aumentaba la
   fiabilidad del score.
5. Las contradicciones 8B no reducían puntuación porque `negative_weight=0`.
6. La cobertura no fue el bloqueo principal: 49/50 candidatos tenían cobertura.
7. No existía límite de promociones; se ordenaban los 50 candidatos globalmente.

## Sensibilidad

Se evaluaron pesos predefinidos `0`, `0,1`, `0,2`, `0,5`, `1` y `2` sin GT. Los
pesos altos producen cruces Top-10 y cambios Top-1, pero de forma muy sensible a
consulta, modelo y selector. Esto descarta «subir el peso» como primera solución:
crea movimiento, no evidencia de mejora geográfica.

El artefacto reproducible es
`results/generated/mapillary/h16-h23-reranking-diagnostics-v1/diagnostic.json`,
SHA-256 `27f6487090e1d63c9d70baa7a6d53cd59c6f5ec291ac6d6cc9d7f6a3dcf5608e`.

## Contradicciones

El prompt exige incompatibilidad visible y trata ausencia, oclusión, distancia y
duda como `unverifiable`. El parser rechaza contradicciones basadas en visibilidad
insuficiente. Qwen3-VL-2B produjo cero contradicciones en H16/H23; 8B produjo 126
en las tareas físicas finales. El contrato y parser permiten los tres veredictos,
pero 2B mostró un comportamiento conservador en esta campaña. Se añadieron
fixtures positivos, negativos y ambiguos; no se fuerzan contradicciones por
ausencia.

## Recuperabilidad

El diagnóstico posterior al freeze confirma candidatos a menos de 50 m dentro
del Top-50 v2: H16 en rank 23 a 46,68 m y H23 en rank 37 a 40,19 m. Las celdas
asignadas/más próximas aparecen después de Top-50, en ranks 62 y 56 de Top-100.
El reranking Top-50 podía mejorar el umbral de 50 m, pero no promover la celda más
próxima. Ampliar Top-N sería otra variante de recuperación.

## Mejora implementada

El reranker discriminativo experimental conserva CT2L como base y usa frecuencia
inversa por soporte imagen-claim compartido, compatibilidad espacial, cero para
orientación incompatible, descuento por celdas competidoras y *noisy-or* sobre
secuencias independientes. Falta de evidencia y `unverifiable` son neutrales; la
contradicción mantiene peso cero por defecto.

Con peso positivo 0,2, el diagnóstico H16/H23 no cambia Top-1. Solo H23 con el
selector geométrico produce una entrada Top-10 para ambos modelos. Este resultado
development no demuestra mejora ni selecciona la política.

## Próximo protocolo válido

La calibración corresponde a H26–H37. H38–H61 debe permanecer sellado hasta
congelar selección, política, pesos y artefactos. No se ejecutó una nueva campaña
masiva porque esas consultas todavía no disponen del conjunto visual/anotado
necesario para un piloto independiente.
