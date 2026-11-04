# Cierre técnico A/B H16/H23

## Presupuesto deduplicado

| Métrica por modelo | 2B | 8B |
|---|---:|---:|
| Jobs lógicos A | 8.227 | 8.227 |
| Jobs lógicos B | 8.227 | 8.227 |
| Tareas físicas A∪B | 9.613 | 9.613 |
| Compartidas A/B | 2.453 | 2.453 |
| Reutilizables exactas | 845 | 845 |
| Nuevas | 8.768 | 8.768 |
| Generate A∪B | 7.625 | 7.625 |
| Generate reutilizables | 669 | 669 |
| Generate nuevas | 6.956 | 6.956 |
| Abstenciones automáticas | 1.988 | 1.988 |
| GPU estimada | 3.237 s | 10.186 s |

Invariantes:

```text
8.227 + 8.227 - 2.453 = 14.001 jobs lógicos deduplicados por proyección
9.613 = 845 reutilizables + 8.768 nuevas
9.613 = 7.625 generate + 1.988 abstenciones
```

La diferencia 14.001→9.613 corresponde a proyecciones lógicas que comparten una
tarea física imagen-claim-modelo. Para assets pendientes, la identidad es
provisional por ID y solo será final tras SHA-256.

## E2E sintético real

Se ejecutó en `TemporaryDirectory` usando componentes del pipeline:

- autorización ficticia local;
- `MapillaryCache.store` con bytes sintéticos;
- hashes y rechazo de bytes conflictivos;
- `build_physical_plan`;
- reutilización exacta;
- fake verifier por callback;
- `run_resumable` con interrupción/reanudación;
- proyección a brazos;
- `aggregate_candidate_evidence`;
- `apply_symmetric_reranking` sobre 50 candidatos;
- `finalize_json_atomic`;
- `evaluate_synthetic_rankings` después del freeze.

Resultado:

```text
16 jobs lógicos
12 tareas físicas
4 jobs deduplicados
3 assets físicos
reanudación ejercitada
candidate set preservado
GT ausente antes de evaluación
evaluación marcada sintética/no oficial
```

Reporte local SHA-256:

`231e86429e5998c08fc9a29a3b6d754d917d2459a7fbed2d4422478981b8ab71`.

## Invariantes científicas

- mismos candidatos/claims en ambos brazos;
- assets compartidos almacenados una vez;
- tareas idénticas ejecutadas una vez por modelo;
- IDs 2B/8B incompatibles entre sí;
- proyecciones auditables por brazo/candidato;
- deduplicación por secuencia en agregado;
- ausencia y `unverifiable` neutrales;
- reranking simétrico y baseline restaurable;
- ranking-set content-addressed y atómico;
- evaluador recibe solo rankings ya congelados;
- referencias sintéticas nunca aparecen antes del evaluador.

## Qué sigue pendiente de datos reales

- SHA-256 definitivo de 474 imágenes;
- cuotas y respuestas reales API;
- fallos/reintentos reales de descarga;
- duración real completa;
- utilidad visual de assets nuevos;
- rankings A/B completos;
- evaluación geográfica real.

## Checklist final

- [x] manifests congelados y validados;
- [x] presupuesto físico deduplicado;
- [x] dry-run sin red/modelos;
- [x] adquisición fail-closed;
- [x] checkpoint/reanudación;
- [x] proyección A/B;
- [x] agregación y reranking reales en fixture sintética;
- [x] freeze antes de evaluación;
- [x] prueba negativa de GT;
- [ ] revisión autenticada de términos;
- [ ] autorización firmada/completada;
- [ ] descarga e inferencia real.

## Dictamen

```text
Estado técnico: TECHNICALLY_READY
Estado autorización: PENDING_AUTHORIZATION
```
