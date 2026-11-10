# Contexto cartográfico local de 2 km

El PMTiles visual se genera desde el PBF OSM local fijado, sin cambiar D004 ni
las galerías científicas:

```bash
python scripts/build_madrid_pmtiles.py \
  --output results/generated/map-assets-context-2000m/madrid-context-2000m.pmtiles \
  --margin-m 2000 --min-zoom 11 --max-zoom 17
```

Identidad esperada:

- SHA-256: `c170faa62cf5e664d3481f19bca0efe86dc9e1df8ea7c981479b3d81de61e2ba`;
- tamaño: `12068745` bytes;
- provenance versionada: `madrid-context-2000m.pmtiles.provenance.json`.

El binario PMTiles es regenerable y permanece ignorado por Git. El despliegue lo
monta mediante `MVP_MAP_CONTEXT_DIR`.
