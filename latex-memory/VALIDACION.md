# Validación de la memoria LaTeX

Fecha de revisión: 8 de octubre de 2026.

## Compilación observada

Desde `latex-memory/` se ejecutó `latexmk -pdf main.tex` con pdfLaTeX de MiKTeX, latexmk 4.88 y Biber 2.22. Tras resolver la interacción entre TikZ y las abreviaturas activas del español de Babel y corregir el desbordamiento de identificadores largos, se completó la compilación hasta obtener `main.pdf` (35 páginas en esta versión). Una ejecución posterior de `latexmk -pdf -silent main.tex` confirmó la estabilización de referencias.

`main.blg` registra 11 claves citadas, lectura de `bibliografia.bib` y escritura de `main.bbl`, sin advertencias de Biber. El último `main.log` no muestra advertencias, referencias indefinidas ni cajas overfull/underfull. Los índices incluyen siete capítulos, bibliografía y anexos A--C; el anexo ficticio está desactivado con `\ejemplosfalse` y las citas ficticias no forman parte de `bibliografia.bib`.

## Alcance de la comprobación

La compilación acredita la integración técnica de los `.tex`, figuras TikZ, tablas y bibliografía; no comprueba por sí misma hechos científicos, ejecución de las pruebas Python ni validez final de las conclusiones. Antes de la entrega deben confirmarse autor, dirección, departamento, curso y fecha en `metadata.tex`, tipología aplicable, texto inglés del título y uso previo de IA. Es necesario volver a revisar visualmente la portada y la maquetación final una vez completados esos metadatos y se añadan resultados futuros.

El registro original del 25 de septiembre de 2026 describía una revisión estática anterior y declaraba la compilación pendiente; la compilación de esta versión supersede aquella observación sin modificar los documentos técnicos del TFG.
