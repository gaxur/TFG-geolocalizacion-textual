# Validación del quality gate y estrategia multimodal posterior

## Estado real del quality gate

El componente de calidad existe y está probado como runner offline, pero no está
activado en el backend principal.

`backend/atlas_api/lifespan.py` continúa instanciando únicamente
`PrecomputedVisualPostprocessor`. El modelo HTTP tampoco admite todavía
`source=quality_gated` ni el detalle `quality_pipeline`. Activarlo en producción
antes del smoke rompería el contrato FastAPI.

Por tanto:

- `VisualPostprocessor.apply()` es el punto arquitectónico correcto;
- la ejecución real inicial debe hacerse mediante el runner offline autorizado;
- la conexión backend se pospone hasta validar contrato, latencia y evidencia;
- Atlas v3 permanece inalterado.

## Defectos corregidos

La revisión encontró y corrigió:

- validación frontend que impedía promociones desde ranks 11–N;
- fallback baseline cuando no existe ninguna imagen `ACCEPT`;
- validación semántica de resultados cacheados;
- off-by-one en sustituciones;
- neutralización de fallos esperables del resolver;
- posibilidad de usar cache hits tras agotar descargas;
- verificación del sidecar de caché Mapillary;
- proyección a claims ligada a `candidate_id + image_id + image_sha256`,
  `quality_run_id` y `quality_task_id`;
- recomputación del `run_id` tras añadir recursos reales.

Pendientes antes de backend:

- ampliar contrato HTTP para `quality_gated`;
- exponer tiempos de postprocesamiento;
- derivar capabilities desde `visual.metadata`;
- verificar snapshot local completo del processor/modelo, no solo shards;
- cerrar correctamente recursos si falla startup;
- integrar factoría/configuración real sin alterar el camino precalculado.

## Smoke 8B preparado

Directorio:

`results/generated/visual-quality-gate-v1/h11-five-candidate-smoke/`

Selección pre-píxel:

- fixture histórica H11 de desarrollo;
- candidatos lexicográficamente primeros con al menos tres assets locales
  íntegros;
- cinco candidatos;
- tres imágenes por candidato;
- intercalado por secuencia;
- sin claims, GT, evaluación, H26–H37, H38–H61 o I01–I20.

Plan:

`visual-quality-reserve-plan-sha256-fd21be1e129012d135eb13416f4a7b0634ad421dc7499890bcaa41a89b958967`

Presupuesto:

| Recurso | Valor |
|---|---:|
| Candidatos | 5 |
| Assets | 15 |
| Bytes locales | 1.952.084 |
| Llamadas máximas de calidad | 15 |
| Claims | 0 |
| Red | 0 |
| Reranking | 0 |
| Evaluación | 0 |
| Tiempo estimado incluyendo carga | 118,7 s |
| Pico CUDA estimado | 18,1 GB |

La autorización está `approved=false` y `gpu_authorized=false`.

## I01–I20

Las veinte referencias son accesibles e íntegras. La auditoría CPU registró:

- 20/20 decodificadas;
- 0 avisos extremos de oscuridad/sobreexposición;
- 0 avisos de contraste global muy bajo;
- 0 avisos de dimensiones pequeñas;
- 0 avisos de varianza de bordes extremadamente baja.

Estas métricas son descriptivas y no sustituyen inspección humana. No se ha
ejecutado VLM ni se ha sustituido ninguna imagen.

Interfaces:

- anotación: `results/generated/i01-i20-annotation-workflow-v1/annotation/annotate.html`;
- escenas: `results/generated/i01-i20-annotation-workflow-v1/scene-review/review-scenes.html`.

Orden humano:

1. revisar los 12 pares de escena;
2. congelar decisiones humanas;
3. regenerar cohort `CLEAR`;
4. anotar descripciones y claims;
5. revisores A/B;
6. adjudicación;
7. custodio ledger;
8. freeze geográfico;
9. validar mínimo 12.

Estado: 0 `ELIGIBLE`.

## Diagnóstico A–H

### A. Candidato ausente del Top-100

H33 no tiene candidato a menos de 100 m; H29 no lo tiene a menos de 50 m. Un
reranker Top-100 no puede resolver esos umbrales. Es un fallo de recuperación,
pero minoritario: 11/12 consultas sí tienen candidato a 100 m.

### B. Candidato presente y mal ordenado

Es el problema dominante en H26–H37. El rank medio del candidato más próximo es
50,3; H34 aparece en rank 92, H30 en 78, H27 en 69 y H37 en 63. La evidencia
posterior no vence de forma segura el gap CT2L.

### C. Objeto ausente de OSM/F3

H32 menciona `Alonzo`, ausente de F3. La categoría peluquería no sustituye una
identidad ausente. La ausencia no es contradicción, pero limita la discriminación.

### D. F3 ambiguo

Starbucks aparece en varias celdas y nombre/categoría pertenecen al mismo nodo.
Los bolardos repetidos son una familia correlacionada. Intersección con celda no
demuestra visibilidad ni posición del observador.

### E. Imagen Mapillary técnicamente insuficiente

El selector v3 registró 89/627 asociaciones con `quality_score < 0,5`. Esa
metadata no mide directamente blur, exposición o visibilidad. El quality gate
propuesto medirá utilidad técnica, no relevancia geográfica.

### F. Imagen nítida sin objeto

Commons produjo 0/8 targets visibles y 0/8 soporte específico. El problema fue
el encuadre/selección temática, no necesariamente la nitidez. No debe repetirse
esa campaña.

### G. Evidencia visual útil con asociación espacial débil

En H28 se ve el paso, pero no la farmacia; la vista era espacialmente ambigua.
Una imagen puede contener evidencia correcta y proyectarse a varias celdas.

### H. Evidencia correcta no explotada

H36 contiene `El Escarpín`, único y cercano; permitió el único hit nuevo seguro
de v5. La evidencia existe, pero no generaliza: toda la mejora v5 depende de esa
consulta.

## Fuentes complementarias

| Fuente | Incremento | Cobertura/precisión | Riesgo | Decisión |
|---|---|---|---|---|
| Mapillary | Fachadas, rótulos, atributos visuales | Amplia D004; precisión de cámara desconocida | Asociación ambigua y soporte compartido | Reutilizar assets existentes antes de ampliar |
| Panoramax | Fotos con metadata/licencia por item | 10 items locales; no añade candidatos frente a Mapillary | Cobertura muy baja | No adquirir |
| OSM + Wikidata | Identidad, aliases, patrimonio, tipos | Buena cartografía; coordenada de entidad, no cámara | Nombre/proximidad no prueban visibilidad | Estudio offline conservador |
| Wikidata sin enlace OSM | Semántica adicional | Cobertura sistemática no auditada | Homónimos/entity linking | No integrar sin ablación |
| Commons | Vistas temáticas | 0 cámaras elegibles; 0/8 targets visibles | Asociación temática falsa | Mantener detenido |
| KartaView | Potencial street-level | Sin snapshot local reproducible | Cobertura/términos desconocidos | No implementar |
| OpenAerialMap | Vista aérea | Sin cobertura Madrid medida | No valida perspectiva peatonal | Solo hipótesis aérea específica |

No se justifica nueva adquisición ahora.

## Estrategia multimodal conceptual

No se propone otra suma de pesos ajustada. Se propone una jerarquía de evidencia
y seguridad congelable:

### Estado por candidato

1. **CT2L base:** siempre presente y nunca penalizado por falta de evidencia.
2. **OSM/F3 específico:** identidad/nombre globalmente poco ambiguo o conjunción
   de objetos independientes y espacialmente compatibles.
3. **Visual válido:** solo imágenes `ACCEPT` y asociaciones con fiabilidad
   explícita.
4. **Cobertura:** número de secuencias independientes y claims observables.
5. **Abstención:** ausencia, REVIEW, REJECT, out-of-frame y falta de cobertura son
   neutrales.

### Evidencia positiva

Puede promover únicamente cuando:

- OSM/F3 es específico o existen al menos dos familias independientes;
- la imagen es `ACCEPT`;
- el claim está `supported` con evidencia específica;
- la asociación no es altamente compartida o se descuenta por ambigüedad;
- la promoción está dentro de una reserva congelada.

### Contradicción

Solo puede ser negativa cuando:

- la imagen es `ACCEPT`;
- el claim es observable y está explícitamente contradicho;
- orientación/FOV son comparables;
- existe independencia suficiente;
- la contradicción ha sido validada antes de habilitar peso negativo.

El peso negativo permanece deshabilitado hoy.

### Ausencia y no verificable

No cambian CT2L. Incluye:

- objeto ausente de OSM;
- sin imagen;
- imagen REVIEW/REJECT;
- claim fuera de campo;
- asociación incierta;
- output inválido;
- presupuesto agotado.

### Protección contra regresiones v4

- no promover por nombre de cadena repetida;
- no sumar tags del mismo objeto como evidencias independientes;
- agrupar mobiliario correlacionado;
- bloquear sustitución nominal silenciosa;
- exigir acuerdo mínimo CT2L o corroboración independiente;
- Top-1 protegido por defecto;
- máxima una promoción fuerte por consulta;
- fallback exacto ante cobertura insuficiente.

Esta es una especificación conceptual. No se fijan pesos ni se implementa sobre
H26–H37 o I01–I20.

## Plan escalonado

1. **Smoke quality gate:** cinco candidatos H11, 15 calls máximas, sin claims.
2. **Validación humana:** revisar decisiones y sustituciones; medir falsos
   rechazos técnicos.
3. **I01–I20:** completar escenas, anotación, ledger y reviews hasta ≥12.
4. **Freeze:** seleccionar una única política candidata usando solo evidencia
   previa no I01–I20; si no existe soporte suficiente, mantener Atlas v3.
5. **One-shot:** ejecutar políticas congeladas sobre I01–I20 elegible.

Los pasos 1 y 5 requieren autorizaciones separadas. Los pasos 2 y 3 requieren
personas independientes.

## Criterios de parada

- quality gate: parar si rechaza imágenes humanas utilizables o no mejora
  cobertura técnica después de sustitución;
- multimodal: parar si la ganancia depende de un caso o introduce regresión
  individual material;
- I01–I20: no evaluar con menos de 12 elegibles;
- fuentes: no adquirir si no demuestran cobertura incremental metadata-only;
- no abrir H38–H61 para resolver incertidumbres de desarrollo.
