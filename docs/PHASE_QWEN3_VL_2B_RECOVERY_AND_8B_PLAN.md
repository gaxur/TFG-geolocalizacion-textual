# Recuperación de Qwen3-VL-2B y plan controlado para 8B

## Diagnóstico de los intentos anteriores

Los fallos v1–v3 no demostraban por sí solos incapacidad visual:

- v1 obligaba al modelo a copiar IDs largos y agotó 192 tokens;
- v2 eliminó IDs, pero todas las respuestas usaron fences y muchas serializaron
  `limitations` como string;
- v3 guio el JSON, pero una explicación >120 caracteres invalidaba el veredicto;
- las 10 decisiones crudas `supported` de v3 correspondían a soportes humanos,
  aunque ninguna sobrevivió al contrato completo;
- ninguna versión produjo `contradicted`.

El preprocesamiento multimodal era correcto: `AutoProcessor.apply_chat_template`
recibía una imagen PIL RGB y texto, sin resize manual. Las miniaturas tienen hasta
1.024 px, una limitación real para OCR/detalles, pero no se detectó una pérdida de
imagen causada por integración.

## Contrato v4

La decisión se separa de la explicación.

Primera generación guiada:

```json
{"verdict":"supported|contradicted|unverifiable"}
```

Los IDs se añaden en código. La explicación se solicita en una segunda llamada y
no puede invalidar o cambiar la clase. Esto distingue:

- validez de decisión;
- calidad semántica del veredicto;
- validez y consistencia de explicación.

## Diagnóstico pequeño

Se congelaron 10 pares de development: 5 soportes, 2 contradicciones y 3
abstenciones humanas. Las etiquetas se usaron para muestreo, no se enviaron al
modelo.

Resultado:

| Humana | `supported` | `contradicted` | `unverifiable` |
|---|---:|---:|---:|
| `supported` | 4 | 0 | 1 |
| `contradicted` | 0 | 0 | 2 |
| `unverifiable` | 0 | 0 | 3 |

El diagnóstico obtuvo 10/10 decisiones JSON válidas y justificó ejecutar v4 en
los 60 pares. Ya mostraba el límite principal: ausencia de contradicciones.

## Evaluación v4 completa

| Medida | Resultado |
|---|---:|
| Decisiones válidas | 60/60 (100 %) |
| Accuracy | 51/60 (85,0 %) |
| Macro-F1 | 0,557 |
| Falsos `supported` | 6 |
| Falsos `contradicted` | 0 |
| Abstenciones correctas | 39 |
| Abstenciones incorrectas | 3 |
| Explicaciones generadas | 57 |
| Explicaciones inconsistentes con decisión | 16 |

Matriz:

| Humana | `supported` | `contradicted` | `unverifiable` |
|---|---:|---:|---:|
| `supported` | 12 | 0 | 1 |
| `contradicted` | 0 | 0 | 2 |
| `unverifiable` | 6 | 0 | 39 |

Por clase:

| Clase | Precision | Recall | F1 |
|---|---:|---:|---:|
| `supported` | 0,667 | 0,923 | 0,774 |
| `contradicted` | no definida | 0,000 | 0,000 |
| `unverifiable` | 0,929 | 0,867 | 0,897 |

Recursos:

- carga: 25,37 s;
- ejecución de 60 pares, incluida explicación: 45,31 s;
- decisión media: 0,493 s;
- explicación media: 0,289 s;
- pico CUDA asignado/reservado: 4.482 / 4.538 GB;
- pico RSS: 5,23 GB.

## Interpretación

El 2B queda recuperado como verificador **positivo/abstencionista** experimental:
formato fiable y sensibilidad alta a soportes, pero 6/18 soportes predichos son
falsos. No detecta contradicciones, por lo que no puede habilitar descarte ni
penalización negativa. Las explicaciones tampoco son aptas para justificación
automática: 16 contradicen el veredicto congelado.

Una posible señal positiva para reranking debe ignorar explicaciones
inconsistentes, conservar fallos neutrales y validarse en un conjunto nuevo. H11
no debe usarse para escoger pesos y presentarse después como evaluación.

## Qwen3-VL-8B

Modelo propuesto, no descargado:

- ID: `Qwen/Qwen3-VL-8B-Instruct`;
- revisión: `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`;
- licencia: Apache-2.0;
- parámetros BF16: 8.767.123.696;
- cuatro shards: 17.534.339.512 B; repositorio aproximado 17,546 GB.

Hardware observado:

- NVIDIA GB10, Blackwell `sm_121`, memoria unificada;
- RAM total 121 GiB, disponible ~100 GiB;
- PyTorch NGC 2.11/CUDA 13.1 y Transformers 5.9 compatibles con la clase;
- disco libre: ~7,1 GB, insuficiente.

BF16 aislado parece viable en memoria con una estimación prudente de 20–26 GiB
y margen recomendado 28–32 GiB. No debe coexistir inicialmente con CrossText2Loc
o Qwen textual. El bloqueo actual es almacenamiento: se requieren al menos
22–25 GB libres, preferiblemente 30 GB, considerando temporales.

Cuantización no es la primera opción: bitsandbytes no está instalado y ARM64 con
CUDA 13.1 no está validado; 4/8 bits introducirían otra variable científica y
posible degradación visual. El primer smoke autorizado debería ser BF16, una
imagen, batch 1, SDPA y contrato v4.

## Integración desacoplada

`src/tfg_phase0/visual_verifier.py` define una interfaz `VisualVerifier` y
configuración por modelo. El pipeline puede cambiar entre 2B/8B sin modificar:

- asociación Mapillary;
- claims;
- agregación por secuencia;
- artefacto de reranking;
- evaluación offline.

Verificación, reranking, descarte y sustitución permanecen módulos distintos. El
2B actual puede seguir estudiándose para evidencia positiva, pero no para
descarte. H11 y el MVP permanecen sin ejecutar/modificar.

## Siguiente paso sujeto a autorización

1. liberar o proporcionar 25–30 GB sin borrar artefactos científicos;
2. autorizar explícitamente modelo/revisión 8B y descarga de 17,55 GB;
3. verificar hashes de los cuatro shards;
4. smoke BF16 aislado con contrato v4;
5. diagnóstico en los mismos 10 pares y comparación 2B/8B;
6. solo si mejora, ejecutar los 60 pares con mismas métricas.

No se presupone que 8B vaya a mejorar contradicciones.

## Resultado posterior del 8B

El modelo 8B fue autorizado, descargado y verificado en BF16. El smoke funcionó,
pero las diez decisiones diagnósticas fueron idénticas a las del 2B, incluida la
ausencia total de `contradicted`. Requirió 3,98× el pico CUDA, 3,94× el tiempo de
carga y 2,34× el tiempo de ejecución. No se ejecutaron los 60 pares con 8B y se
mantiene el 2B como modelo de desarrollo. Véase
[PHASE_QWEN3_VL_8B_DIAGNOSTIC.md](PHASE_QWEN3_VL_8B_DIAGNOSTIC.md).
