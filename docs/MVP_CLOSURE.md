# Cierre técnico del MVP

## Estado

MVP.1, MVP.2 y MVP.3 proporcionan un recorrido técnico funcional desde una
descripción textual hasta un Top-K de candidatos de Madrid visible en un mapa.
El cierre significa que la aplicación puede construirse, arrancarse, probarse y
detenerse de forma reproducible en la PGX. No significa que el modelo esté
científicamente validado para Madrid.

## Funcionalidades completadas

- Entrada de una descripción textual.
- Selección entre galerías de 25 m y 50 m.
- Selección Top-3, Top-5 o Top-10.
- Imágenes OSM y embeddings precalculados fuera de la ruta de inferencia.
- CrossText2Loc con pesos preentrenados congelados.
- Ranking exhaustivo con desempate determinista por `candidate_id`.
- Una instancia residente del modelo y un worker Uvicorn.
- API FastAPI con liveness, readiness, capabilities, retrieval y errores
  contractuales.
- Frontend estático de producción servido por Nginx.
- Proxy `/api` del mismo origen hacia FastAPI.
- Mapa Leaflet, bbox del piloto, coordenadas WGS84 y marcadores Top-K.
- Sincronización entre candidatos y mapa.
- Healthchecks de API y frontend.
- Despliegue conjunto mediante Docker Compose.
- Browser-check reproducible con Chromium ARM64 aislado.
- Smoke extremo a extremo con la GPU GB10 y ambas galerías.

## Evidencia técnica de cierre

La ejecución de `scripts/smoke_mvp3_stack.sh` comprobó:

- frontend estático y proxy del mismo origen;
- API y frontend saludables;
- galerías de 253 candidatos a 50 m y 1.115 candidatos a 25 m;
- Top-5 real de 50 m y Top-3 real de 25 m;
- coordenadas válidas;
- IDs, orden y scores idénticos al repetir la consulta;
- un único proceso Uvicorn con `--workers 1`;
- Leaflet, marcadores, selección y vista móvil desde Chromium ARM64;
- cierre ordenado y ausencia de contenedores temporales residuales.

Estas comprobaciones son técnicas. No utilizan una ubicación real validada para
medir acierto y, por tanto, no son métricas de precisión geográfica.

## Limitaciones

- El checkpoint se preentrenó en Nueva York, no en Madrid.
- La fidelidad del perfil de render OSM sigue siendo una cuestión experimental.
- No existe todavía evaluación madrileña suficiente con *ground truth*
  independiente y validado.
- El frontend acepta español, pero su precisión no está validada.
- La similitud coseno y su escala porcentual no son probabilidades calibradas.
- El Top-1 es el primer candidato del ranking, no una ubicación confirmada.
- Las coordenadas son centros de candidatos del catálogo, no una regresión
  continua de la posición del observador.
- No se ha realizado entrenamiento, *fine-tuning* ni modificación del modelo.
- F5, LLM, GOTPR, fotografías, VLM, diálogo y refinamiento métrico permanecen
  fuera del MVP.
- El despliegue es local y experimental; no está endurecido para Internet.

## Conclusión

El resultado es un **MVP funcional integrado**, adecuado para probar operación,
contratos, interacción y reproducibilidad. La siguiente fase científica deberá
definir y ejecutar una evaluación válida en Madrid antes de formular cualquier
afirmación sobre precisión, utilidad real o generalización del modelo.
