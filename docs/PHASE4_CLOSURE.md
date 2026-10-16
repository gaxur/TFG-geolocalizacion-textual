# Cierre técnico de F4

## Resultado

F4 queda técnicamente cerrada para integración en el MVP mediante la interfaz
residente descrita en [CROSSTEXT2LOC_RETRIEVAL_INTERFACE.md](CROSSTEXT2LOC_RETRIEVAL_INTERFACE.md).

Se verificó en NVIDIA GB10:

- una única carga del checkpoint;
- dos galerías residentes, 25 m y 50 m;
- una sola codificación textual para una petición multigalería;
- Top-10 con IDs, WGS84 y similitud coseno;
- igualdad exacta con los rankings F4.4 existentes;
- repetición determinista de candidatos y scores;
- consulta inglesa y española;
- rechazo de consultas tras `close()`;
- memoria CUDA real después de carga y consulta.

El smoke local está en `results/generated/f4/f46-smoke-final.json`, fuera de Git.

## Frontera con el MVP y F5

El futuro backend debe consumir `CrossText2LocRetriever`; no debe reimplementar
el modelo ni el ranking. La API HTTP, frontend, LLM, preselección OSM y F5 quedan
fuera de F4.

El cierre es técnico, no empírico: no demuestra precisión de geolocalización en
Madrid. Permanecen abiertas D007, D013, D016, D024, D029 y D030.
