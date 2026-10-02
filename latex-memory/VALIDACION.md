# Validación de la infraestructura

Fecha: 25 de septiembre de 2026.

## Revisión estática

- Revisados los 17 archivos LaTeX activos: estructura, paquetes, opciones y contenido inicial.
- Comprobadas 17 rutas de `input`, `include` y `addbibresource`: todos los destinos existen.
- Comprobadas 15 etiquetas únicas, cuatro referencias cruzadas activas y dos claves citadas existentes en el `.bib`.
- Comprobado el equilibrio básico de llaves y entornos. Esto no equivale a interpretar TeX.
- Comprobados los enlaces relativos de los documentos Markdown.
- Comprobado que los capítulos contienen únicamente estructura y comentarios TODO.
- Verificados por comparación binaria el logotipo y la fuente de portada conservada frente al ZIP oficial.
- Verificados los interruptores de agradecimientos y ejemplos por inspección del código.
- Las modificaciones se limitan a `TFG/`. No se ha cambiado la definición del proyecto ni se han incorporado credenciales.

## Compilación pendiente

Los comandos `pdflatex --version`, `biber --version` y `latexmk --version` fallan con «comando no reconocido». Tampoco se encontraron instalaciones en las ubicaciones habituales de TeX Live y MiKTeX comprobadas. No se ha instalado software global ni una distribución portátil.

Por ello, **no se ha generado `main.pdf`, no se ha ejecutado Biber y no se puede certificar la ausencia de errores o avisos de compilación**. La revisión visual de portada, paginación, índices y tipografía también queda pendiente. No se ha subido el proyecto a una cuenta de Overleaf.

## Verificación reproducible con LaTeX disponible

Desde `TFG/`, ejecutar:

```powershell
latexmk -pdf main.tex
```

Comprobar en `main.blg` que Biber leyó `bibliografia.bib` y escribió `main.bbl`. Revisar en el PDF las dos entradas EJEMPLO, las cuatro referencias cruzadas, los índices y el acrónimo. Revisar `main.log` hasta que no queden citas o referencias indefinidas, peticiones de nuevas pasadas ni desbordamientos importantes.

Probar después `\agradecimientostrue` y `\ejemplosfalse` en `metadata.tex`, recompilando desde cero. Sin ejemplos ni fuentes reales citadas, el aviso de bibliografía vacía es esperable. Volver a las opciones deseadas para seguir redactando.

Las instrucciones de instalación, compilación manual con Biber y uso en Overleaf están en [README.md](README.md). Esta validación pendiente no se presenta como una compilación satisfactoria.
