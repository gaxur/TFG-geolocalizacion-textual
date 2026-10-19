# Cierre técnico de F4

## Resultado

F4 queda técnicamente cerrada para integración en el MVP mediante la interfaz
residente descrita en [CROSSTEXT2LOC.md](CROSSTEXT2LOC.md#interfaz-residente-f46).

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

El backend implementado consume `CrossText2LocRetriever` y no reimplementa el
modelo ni el ranking. MVP.1 añadió FastAPI, MVP.2 conectó Leaflet y MVP.3 cerró
el despliegue mediante `compose.mvp.yaml`; véase
[MVP.md](MVP.md). Estas capas permanecen fuera del
alcance científico de F4. LLM, preselección OSM y F5 continúan pendientes.

El cierre es técnico, no empírico: no demuestra precisión de geolocalización en
Madrid. Permanecen abiertas D007, D013, D016, D024, D029 y D030.
