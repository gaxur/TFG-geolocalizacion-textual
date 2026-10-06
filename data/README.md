# Datos locales (no versionados)

Las carpetas `cvg_text/` y `madrid/` reservan espacio para futuros datasets en
la DGX. Su contenido está ignorado por Git. No contienen datos en este commit.

| Carpeta | Uso previsto |
|---|---|
| `cvg_text/` | Anotaciones e imágenes originales utilizadas en la reproducción de Nueva York |
| `madrid/` | Datos y candidatos de Madrid cuando se apruebe su preparación |

Los snapshots OSM raw de Fase 2 se almacenan localmente bajo
`raw/osm/snapshots/<osm_snapshot_id>/`; están ignorados por Git. Cada directorio
contendrá `source.osm`, `provenance.json` y `sha256.txt`. Los derivados se
mantendrán separados bajo `processed/osm/<osm_snapshot_id>/`.

Las rutas efectivas del loader oficial se configuran en el `config.yaml` del
clon local de CVG-Text y no se presuponen iguales a la disposición interna de
ningún ZIP. Documentar la procedencia, licencia, revisión y hashes de los
artefactos adquiridos en [EXPERIMENTS.md](../docs/EXPERIMENTS.md).
