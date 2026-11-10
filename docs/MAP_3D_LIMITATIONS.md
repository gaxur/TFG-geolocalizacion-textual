# Alcance visual del mapa 3D

La base visual activa es un artefacto nuevo de contexto, D004 más un margen de
2.000 m. La cámara limita sus centros a un margen interior aproximado de 1.000 m
y usa zoom mínimo 14,5 para mantener cartografía alrededor del viewport. Esto no
modifica la región científica D004 ni el catálogo de candidatos.

```text
results/generated/map-assets-context-2000m/madrid-context-2000m.pmtiles
SHA-256: c170faa62cf5e664d3481f19bca0efe86dc9e1df8ea7c981479b3d81de61e2ba
```

El PMTiles original de 250 m permanece intacto. El nuevo artefacto usa el mismo
PBF OSM local y conserva provenance, ODbL, toolchain y lineage de las celdas F1.

El PMTiles visual contiene huellas y algunos atributos OSM, pero no incluye una
malla fotogramétrica, imágenes de fachada, texturas, materiales, geometría de
tejados ni atributos de relojes. Por ello el modo 3D es una representación
cartográfica aproximada:

- usa `height` cuando existe;
- estima `building:levels × 3 m` cuando hay plantas;
- usa 9 m como fallback visual;
- diferencia los tres casos mediante color.

No es técnicamente correcto afirmar que estas extrusiones muestran el edificio
real. Una torre puede verse como volumen, pero su reloj, ventanas, esculturas y
fachada no pueden reconstruirse desde este PMTiles.

Mostrar esos detalles exigiría una fuente adicional con geometría y textura
calibradas, por ejemplo una malla 3D/fotogramétrica o modelos 3D individualizados,
además de licencia, procedencia, cobertura, tamaño y atribución compatibles. Las
fotografías Mapillary de la cohorte no son texturas de fachada: una sola imagen no
aporta malla, oclusiones ni calibración suficiente para proyectarla correctamente.
No se incorporará esa fuente como sustitución silenciosa del mapa OSM.
