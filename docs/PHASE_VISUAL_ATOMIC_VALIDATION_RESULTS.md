# Validación atómica de Qwen3-VL-2B frente a anotaciones humanas

## Protocolo

Se comparó `Qwen/Qwen3-VL-2B-Instruct`, revisión
`89644892e4d85e24eaac8bacfd4f463576704203`, con 60 anotaciones humanas
claim-imagen de H12, H14, H16 y H19. Las etiquetas se congelaron antes de la
inferencia y no se cargaron en el proceso VLM. No se usó GT, ranking, coseno o
coordenadas en los prompts.

La referencia contiene 13 `supported`, 2 `contradicted` y 45 `unverifiable`.
Los tres claims que requieren orientación se resolvieron por política externa
como `unverifiable`, sin invocar el modelo.

Los artefactos son:

- anotaciones humanas:
  `results/generated/mapillary/visual-reranking-development-v1/atomic-annotations.json`;
- primer intento con contrato largo:
  `qwen3-vl-2b-atomic-run.json`;
- intento compacto no guiado:
  `qwen3-vl-2b-atomic-run-v2-compact.json`;
- intento compacto guiado evaluado:
  `qwen3-vl-2b-atomic-run-v3-guided.json`;
- evaluación:
  `qwen3-vl-2b-atomic-evaluation-v3-guided.json`.

Los dos primeros intentos VLM se conservan como fallos contractuales: 0/57
salidas aceptadas. El primero se truncó al repetir IDs largos; el segundo produjo
fences Markdown y tipos incompatibles. No se repararon ni se usaron para métricas.

La variante v3 utilizó LM Format Enforcer 0.11.3 de forma efímera, con schema
compacto y validación semántica posterior. No cambia pesos ni decisiones
semánticas del modelo.

## Resultados v3

| Medida | Resultado |
|---|---:|
| Pares | 60 |
| Predicciones utilizables | 24/60 (40,0 %) |
| Del modelo | 21 |
| Abstenciones de orientación por política | 3 |
| Outputs inválidos/rechazados | 36 |
| Exactitud sobre los 60 pares | 22/60 (36,7 %) |
| Exactitud condicionada a output utilizable | 22/24 (91,7 %) |
| Macro-F1, contando outputs inválidos como fallo | 0,213 |
| Falsas contradicciones aceptadas | 0 |
| Falsos soportes aceptados | 0 |
| Abstenciones correctas | 22 |
| Abstenciones incorrectas | 2 |

La exactitud condicionada no debe interpretarse como fiabilidad global: el
modelo no produjo ningún `supported` o `contradicted` que superase el contrato.
Las 24 predicciones utilizables fueron todas `unverifiable`.

Matriz de confusión; filas humanas y columnas del sistema:

| Humana | `supported` | `contradicted` | `unverifiable` | inválido |
|---|---:|---:|---:|---:|
| `supported` | 0 | 0 | 1 | 12 |
| `contradicted` | 0 | 0 | 1 | 1 |
| `unverifiable` | 0 | 0 | 22 | 23 |

Por clase:

| Clase | Precision | Recall | F1 | Soporte |
|---|---:|---:|---:|---:|
| `supported` | no definida | 0,000 | 0,000 | 13 |
| `contradicted` | no definida | 0,000 | 0,000 | 2 |
| `unverifiable` | 0,917 | 0,489 | 0,638 | 45 |

## Fallos contractuales y recursos

De las 57 llamadas reales al modelo, 43 generaron JSON sintáctico y 14 quedaron
truncadas o incompletas. Tras aplicar el contrato semántico:

- 22 se rechazaron por evidencia de más de 120 caracteres;
- 13 excedieron el tamaño o quedaron truncadas;
- 1 no fue JSON completo.

Recursos:

| Medida | Resultado |
|---|---:|
| Carga del modelo | 25,09 s |
| Ejecución VLM | 270,20 s |
| Latencia media por llamada real | 4,69 s |
| Latencia máxima | 9,00 s |
| Pico CUDA asignado | 4.477.118.464 B |
| Pico CUDA reservado | 4.500.488.192 B |
| Pico RSS | 7.057.608.704 B |

## Interpretación para descarte

El resultado **no valida descarte automático**. Que no haya falsas
contradicciones aceptadas no demuestra seguridad: no se aceptó ninguna
contradicción, incluida la única contradicción humana que recibió una predicción
utilizable, que el sistema convirtió en `unverifiable`. Tampoco se aceptó ningún
soporte.

El modelo/contrato actual actúa como abstención parcial con una tasa de fallo del
60 %. No satisface el criterio previo de 100 % de outputs contractuales ni puede
separar candidatos compatibles de incompatibles. Usarlo para eliminar candidatos
introduciría una política basada en fallos de formato y ausencia de evidencia,
justo lo que el protocolo prohíbe.

## Decisión

Se mantiene Qwen3-VL-2B como apoyo exploratorio con revisión humana. Quedan
bloqueados:

- experimento H11 con reranking;
- descarte automático o reversible;
- sustitución de candidatos;
- integración en el MVP.

No se realiza una cuarta adaptación sobre esta misma fixture para evitar seguir
ajustando al conjunto de desarrollo. Una mejora futura debe diseñarse y congelarse
antes de otro conjunto humano, por ejemplo reduciendo la salida a un enum y una
evidencia acotada mediante generación guiada más restrictiva o evaluando otro
modelo con autorización expresa.

## Recuperación posterior del contrato de decisión

Por petición expresa se diagnosticó el acoplamiento entre clase y explicación y
se creó v4, donde `verdict` se genera de forma guiada e independiente. V4 obtuvo
60/60 decisiones válidas, accuracy 85,0 % y macro-F1 0,557. Detectó 12/13
soportes, con 6 falsos soportes, y 0/2 contradicciones. Las explicaciones separadas
fueron inconsistentes en 16 casos. El resultado recupera al 2B como verificador
positivo/abstencionista de development, pero no levanta el bloqueo de descarte.
Véase [PHASE_QWEN3_VL_2B_RECOVERY_AND_8B_PLAN.md](PHASE_QWEN3_VL_2B_RECOVERY_AND_8B_PLAN.md).
