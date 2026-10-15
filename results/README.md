# Resultados

Se podrán versionar aquí métricas, manifests o CSV/JSON **pequeños** cuando
sean relevantes, revisados y se conozcan sus condiciones de publicación.
Guardar volcados extensos, cachés y salidas generadas en `generated/`, `raw/`,
`large/` o `cache/`, que están ignorados. El prototipo de `frontend/` continúa
usando datos simulados; los experimentos reales se registran por separado en
`docs/EXPERIMENTS.md` y sus artefactos voluminosos permanecen locales.

Registrar cada ejecución en [EXPERIMENTS.md](../docs/EXPERIMENTS.md).

Los resúmenes pequeños y saneados de reproducciones cerradas se guardan en
`reproductions/`. Los directorios brutos `cross_text2loc_docker/` y
`cross_text2loc_wait_run/` permanecen locales: pueden contener logs, telemetría,
rutas privadas y resultados derivados del dataset que no deben redistribuirse.
