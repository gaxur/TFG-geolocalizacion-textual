# Integración funcional VLM posterior a CrossText2Loc: etapa 1

## Arquitectura implementada

El ejecutor genérico `run_visual_fixture_v4.py` consume una fixture sin GT con:

- ranking CrossText2Loc congelado;
- IDs, centros, cosenos y rango base;
- claims revisados;
- manifest de assets y asociaciones Mapillary;
- modelo elegido explícitamente (`qwen3-vl-2b` o `qwen3-vl-8b`).

El request VLM contiene solo claim e imagen. No contiene rango, score,
coordenadas, query ID o GT. Los fallos quedan separados. Las relaciones sin
orientación comparable se abstienen por política. La agregación deduplica por
secuencia y el reranking es otro artefacto, desactivado por defecto.

## H11: prueba funcional

Configuración:

- 10 candidatos CT2L `es_original`, galería 50 m;
- 44 assets únicos y 48 asociaciones;
- 12 claims aprobados;
- 576 pares por modelo;
- 144 abstenciones de orientación y 432 llamadas VLM reales.

| Resultado | 2B | 8B |
|---|---:|---:|
| Jobs | 576 | 576 |
| Outputs inválidos | 0 | 0 |
| `supported` | 248 | 268 |
| `contradicted` | 0 | 0 |
| `unverifiable` | 328 | 308 |
| Carga | 24,42 s | 97,88 s |
| Ejecución | 197,24 s | 595,27 s |
| Pico CUDA asignado | 4,63 GB | 18,08 GB |
| Pico RSS | 5,23 GB | 18,51 GB |

Con reranking desactivado, ambos artefactos conservan exactamente los diez IDs,
orden, cosenos y rangos originales. No se abrió GT ni se evaluó distancia H11.
La evidencia positiva agregada difiere entre modelos en tres candidatos, pero no
puede interpretarse como mejora sin anotación humana H11 y lambdas congelados.
La evidencia negativa es cero para ambos.

## Prueba multiconsulta

Se prepararon fixtures técnicas H18 y H22 desde rankings reales, sin GT. Esto
detectó y corrigió una dependencia de idioma: el ranking puede usar
`en_cartographic`, mientras los claims se compilan desde `es_original`. H18/H22
conservan 10 candidatos, cobertura completa a 100 m y producen 11/10 claims.
No se ejecutó VLM porque faltan claims revisados y manifests autorizados por
consulta.

## Nuevo conjunto humano

Se preparó:

```text
results/generated/mapillary/visual-reranking-expanded-v1/annotations.html
```

Incluye H18, H22, H23 y H25, 24 claims, 12 imágenes existentes y 72 pares. No se
usaron predicciones VLM ni GT para seleccionar. Es ampliación de development, no
test independiente, porque las consultas e imágenes ya se inspeccionaron en
fases anteriores.

## Diseño estadístico y parada

Las unidades claim-imagen no son independientes: comparten consulta, candidato,
secuencia e imagen. Se informarán:

- intervalos Wilson para proporciones;
- McNemar exacto sobre pares 2B/8B;
- bootstrap emparejado por consulta;
- métricas por clase y consulta;
- resultados de una imagen frente a agregación multiimagen.

Para una comparación confirmatoria se necesita un conjunto no usado para prompts
o políticas, con varias consultas y suficientes ejemplos por clase. Como objetivo
operativo inicial, al menos 30 contradicciones inequívocas, 30 soportes y 30
abstenciones distribuidos en ≥10 consultas; no garantiza potencia universal, pero
evita concluir con las dos contradicciones actuales. Si el intervalo agrupado de
la diferencia 8B−2B incluye mejoras y empeoramientos materialmente relevantes,
la conclusión será evidencia insuficiente, no equivalencia.

Criterios de parada:

1. detener un modelo por fallos contractuales sistemáticos o recursos inviables;
2. no ampliar si ambos producen decisiones idénticas y el intervalo agrupado no
   puede estrecharse con los datos accesibles;
3. no habilitar descarte sin recall/precision de contradicción evaluables;
4. no habilitar reranking positivo hasta congelar pesos en development y medir
   consultas distintas;
5. conservar CT2L si el ranking no mejora o introduce regresiones.

## Estado

La integración técnica está operativa offline. Reranking real, descarte,
sustitución y MVP siguen desactivados. H11 es prueba funcional de desarrollo, no
resultado geográfico. La próxima dependencia es anotación humana ampliada.

Los resultados ejecutados se documentan en
[PHASE_VLM_INTEGRATION_STAGE1_RESULTS.md](PHASE_VLM_INTEGRATION_STAGE1_RESULTS.md).
