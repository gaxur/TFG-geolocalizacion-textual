# Resultados

Se podrán versionar aquí métricas, manifests o CSV/JSON **pequeños** cuando
sean relevantes, revisados y se conozcan sus condiciones de publicación.
Guardar volcados extensos, cachés y salidas generadas en `generated/`, `raw/`,
`large/` o `cache/`, que están ignorados. El frontend consume resultados reales
de la API; no contiene un modo sintético. Las pruebas técnicas y los experimentos
se registran por separado en `docs/EXPERIMENTS.md`, y sus artefactos voluminosos
permanecen locales.

Registrar cada ejecución en [EXPERIMENTS.md](../docs/EXPERIMENTS.md).

Los resúmenes pequeños y saneados de reproducciones cerradas se guardan en
`reproductions/`. Los directorios brutos `cross_text2loc_docker/` y
`cross_text2loc_wait_run/` permanecen locales: pueden contener logs, telemetría,
rutas privadas y resultados derivados del dataset que no deben redistribuirse.

El smoke de `compose.mvp.yaml` escribe su evidencia ligera local en
`results/generated/mvp3/stack-smoke.json`. Esa ruta está ignorada y no debe
interpretarse como evaluación de precisión: registra healthchecks, Top-K,
repetibilidad e integración navegador → proxy → GPU. Véase
[MVP.md](../docs/MVP.md).
