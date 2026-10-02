# Infraestructura LaTeX para el TFG — EINA / Unizar

Proyecto modular en español, sin contenido real de la memoria. Los datos desconocidos están marcados como TODO. El correo institucional no se usa para inferir identidad y no se necesita para compilar.

**Estado:** revisión estática realizada; compilación y ejecución de Biber pendientes por ausencia de herramientas locales. No se ha instalado software. Véase [VALIDACION.md](VALIDACION.md).

## Organización

```text
TFG/
├── main.tex
├── config.tex
├── metadata.tex
├── bibliografia.bib
├── latexmkrc
├── README.md
├── VALIDACION.md
├── .gitignore
├── preliminares/
│   ├── portada.tex
│   ├── resumen.tex
│   └── agradecimientos.tex
├── capitulos/
│   ├── 01_introduccion.tex
│   ├── 02_estado_del_arte.tex
│   ├── 03_analisis.tex
│   ├── 04_diseno.tex
│   ├── 05_implementacion.tex
│   ├── 06_evaluacion.tex
│   └── 07_conclusiones.tex
├── anexos/
│   ├── anexo_a.tex
│   ├── anexo_b.tex
│   ├── anexo_c.tex
│   └── ejemplos.tex
├── imagenes/
│   └── logo_uz.png
└── recursos/
    ├── FUENTES.md
    ├── modelos_latex.zip
    └── portada_unizar_original.tex
```

`main.tex` monta los preliminares, índices, capítulos, bibliografía y anexos. `config.tex` contiene paquetes y diseño. Los capítulos contienen solo títulos y comentarios TODO. Los ejemplos se concentran en el último anexo y son eliminables mediante una opción. No se ha elegido ni modificado el alcance científico del TFG.

`recursos/modelos_latex.zip` se conserva en el equipo actual como referencia,
pero los ZIP no se versionan en el monorepo: después de clonar, su procedencia
y enlace de recuperación figuran en [FUENTES.md](recursos/FUENTES.md). Los
fuentes `.tex` y el logotipo necesarios para la memoria sí se mantienen en Git.

## Fuentes oficiales y formato

Consulta [FUENTES.md](recursos/FUENTES.md) para conocer requisitos EINA, enlaces, fecha de revisión y procedencia de la portada y el logotipo. El modelo oficial descargado se conserva como referencia; `preliminares/portada.tex` es la adaptación activa. No compiles `recursos/portada_unizar_original.tex` como documento principal.

Se utiliza `report`, A4 a una cara, 11 pt, Latin Modern en el cuerpo y Carlito en portada. Márgenes del cuerpo de 2,5 cm, interlineado 1,1, encabezado con capítulo y pie con página. La numeración es continua: la portada es la página 1, con cifra oculta; el resumen comienza en 2. No se reinicia en capítulos ni anexos. Bibliografía IEEE numérica por orden de primera cita.

## Requisitos e instalación

Motor de referencia: **pdfLaTeX**, con **Biber** y **latexmk**. Usa versiones de BibLaTeX y Biber de la misma distribución actualizada. No se necesitan Python, Pygments, `shell-escape`, fuentes del sistema ni un generador externo de glosarios.

Instala una distribución desde [LaTeX Project](https://www.latex-project.org/get/):

- **Windows:** TeX Live con instalación completa es una opción sencilla. Alternativamente, MiKTeX; instala Biber, latexmk y los paquetes faltantes desde MiKTeX Console. Para latexmk con MiKTeX puede ser necesario instalar Perl.
- **macOS:** MacTeX.
- **Linux:** TeX Live desde la distribución o el instalador oficial. Una instalación completa evita localizar paquetes individualmente.

Descarga el instalador oficial, selecciona los componentes, termina la instalación y abre una terminal nueva para actualizar el PATH. Estas son instrucciones para que decidas instalarlo; no se ejecutan automáticamente.

Paquetes utilizados: `inputenc`, `fontenc`, `babel` (español e inglés), `carlito`, `lmodern`, `microtype`, `geometry`, `setspace`, `graphicx`, `xcolor`, `booktabs`, `tabularx`, `longtable`, `array`, `amsmath`, `amssymb`, `caption`, `listings`, `acronym`, `csquotes`, `biblatex`, `biblatex-ieee`, `fancyhdr`, `xurl`, `hyperref`, `bookmark` y `cleveref`. Una instalación mínima debe incluir también fuentes y patrones de separación silábica en español.

Comprueba en una terminal:

```powershell
pdflatex --version
biber --version
latexmk --version
```

## Compilar localmente

Ejecuta siempre desde la carpeta `TFG`, de modo que las rutas relativas se resuelvan igual que en Overleaf:

```powershell
cd TFG
latexmk -pdf main.tex
```

El archivo `latexmkrc` configura pdfLaTeX y las repeticiones; latexmk detecta Biber a partir del `.bcf`. El resultado es `main.pdf`.

Compilación manual equivalente, **sin usar BibTeX**:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
biber main
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
```

La primera pasada genera `main.bcf`; Biber lee `bibliografia.bib` y genera `main.bbl`; las siguientes resuelven citas, índices y referencias. Si sigue pidiendo otra pasada, repite pdfLaTeX o utiliza latexmk. Las citas del anexo de ejemplos aparecen en la bibliografía aunque esta preceda al anexo.

Para limpiar auxiliares conservando el PDF:

```powershell
latexmk -c main.tex
```

`latexmk -C main.tex` elimina también el PDF generado. Ninguno de estos comandos debe ejecutarse sobre los recursos oficiales de referencia.

## Overleaf

1. Comprime el contenido de `TFG/` en un ZIP, conservando subcarpetas. Puedes omitir `recursos/`, que contiene solo referencias documentales, y los archivos generados. Incluye `imagenes/logo_uz.png`, los `.tex`, `bibliografia.bib` y `latexmkrc`.
2. En Overleaf, crea un proyecto mediante **Upload Project** y carga el ZIP.
3. Selecciona `main.tex` como documento principal, **pdfLaTeX** como compilador y una versión reciente de TeX Live.
4. Pulsa **Recompile**. Overleaf gestiona las pasadas de Biber mediante latexmk. Si hay auxiliares antiguos, utiliza **Recompile from scratch**.

Referencia: [gestión bibliográfica con BibLaTeX en Overleaf](https://www.overleaf.com/learn/latex/Bibliography_management_with_biblatex). Esta preparación no presupone ninguna suscripción institucional ni acceso a tu cuenta.

## Metadatos y opciones

Completa en [metadata.tex](metadata.tex): título castellano, título inglés, nombre completo del autor, director/es, departamento, curso, fecha, palabras clave y keywords. Utiliza el título académico aprobado. Los valores de universidad, escuela y grado ya están configurados con los datos proporcionados.

Escapa caracteres reservados en textos: `\&`, `\%`, `\_`, `\#`. Usa `\url{...}` para direcciones. Mantén títulos y nombres como texto sencillo para que también sirvan en los metadatos PDF. Revisa visualmente la portada si los nombres o títulos ocupan varias líneas.

- `\agradecimientosfalse`: no incluye agradecimientos. Cambia a `\agradecimientostrue` cuando quieras redactarlos.
- `\ejemplostrue`: incluye el anexo de demostración y sus citas ficticias. Cambia a `\ejemplosfalse` para retirarlo; elimina además las entradas ficticias del `.bib` antes de la entrega y añade fuentes reales citadas.

Redacta el resumen y abstract en [preliminares/resumen.tex](preliminares/resumen.tex); las palabras clave se obtienen de los metadatos. Se colocan en la misma página bilingüe con ambos títulos. Los agradecimientos opcionales tienen su propio archivo.

## Imágenes y logotipos

Coloca imágenes en `imagenes/`; usa nombres sin espacios ni tildes y formatos PDF, PNG o JPEG. No ignores todos los PDF en Git: pueden ser figuras fuente.

```latex
\begin{figure}[htbp]
  \centering
  \includegraphics[width=.8\linewidth]{mi_figura.png}
  \caption{Descripción y procedencia de la figura.}
  \label{fig:mi-figura}
\end{figure}
```

Antes de compilar ese ejemplo, crea el archivo indicado. Referencia la figura con `\cref{fig:mi-figura}`. Sitúa `\label` después de `\caption`. Para tablas usa `booktabs` y pon el caption encima.

El logotipo universitario auténtico ya está incluido. Si necesitas reponerlo, usa el ZIP enlazado en [FUENTES.md](recursos/FUENTES.md), extrae su `img/logo_uz.png` y colócalo en `imagenes/logo_uz.png`. La ruta se configura en `\logoUniversidadTFG`. Si falta, la portada muestra un TODO y sigue siendo editable. No se han dibujado ni añadido logotipos de EINA o de empresas.

## Capítulos y anexos

Para añadir un capítulo, crea `capitulos/08_nombre.tex` con `\chapter{Título}`, un `\label{cap:nombre}` único y sus secciones. Añade `\include{capitulos/08_nombre}` a `main.tex` antes de la bibliografía. Los archivos incluidos no llevan preámbulo ni `\begin{document}`.

Para añadir un anexo, crea otro `.tex` con `\chapter{Título}` y `\label{anx:nombre}`; inclúyelo después de `\appendix`. Las letras se asignan automáticamente. Puedes renombrar los títulos iniciales o retirar anexos vacíos cuando definas su contenido. `\include` inicia página y facilita el trabajo por capítulos; `\input` se usa para configuración y preliminares.

## Bibliografía, acrónimos y código

Añade entradas verificadas a [bibliografia.bib](bibliografia.bib), con claves únicas. Cita mediante `\cite{clave}`. Para artículos utiliza `@article`, `author`, `title`, `journaltitle`, `date` y los campos reales disponibles; para libros, `@book` y `publisher`; para recursos web, `@online`, `url` y `urldate`. No inventes datos bibliográficos faltantes. Solo se imprimen entradas citadas, salvo que añadas `\nocite{clave}` expresamente.

Las dos referencias iniciales están marcadas como EJEMPLO en título, autor y nota; no son fuentes académicas reales. Puedes desactivar los ejemplos sin borrar el archivo `.bib`; una bibliografía vacía puede generar un aviso hasta que cites fuentes reales.

Define acrónimos en [anexos/anexo_b.tex](anexos/anexo_b.tex) con `\acro{SIGLA}{desarrollo}`. Usa `\ac{SIGLA}`: la primera aparición se expande y las siguientes muestran la sigla. `\acs` fuerza la sigla y `\acl` la forma larga. La lista solo imprime términos utilizados, después de las pasadas de LaTeX, sin herramientas externas.

Los fragmentos de código usan `listings`, con captions, numeración y mapeo de caracteres españoles. Consulta [anexos/ejemplos.tex](anexos/ejemplos.tex) para figura, tabla, ecuación, cita, referencia cruzada, código, acrónimo, URL y nota al pie. Para ficheros externos usa `\lstinputlisting[language=Python,caption={Descripción},label={lst:archivo}]{recursos/archivo.py}` después de crear el archivo.

## Registro del uso de IA

Completa la sección correspondiente de la introducción y [anexos/anexo_c.tex](anexos/anexo_c.tex) con el uso real, incluyendo la asistencia en esta infraestructura. Los comentarios guían el registro; no afirman comprobaciones ni actividades que todavía no hayas realizado. Consulta [FUENTES.md](recursos/FUENTES.md) para el formulario institucional independiente.

## Git y revisión antes de entregar

[.gitignore](.gitignore) excluye auxiliares como `.aux`, `.bbl`, `.bcf`, `.blg`, `.fdb_latexmk`, `.fls`, `.log`, `.out`, `.run.xml`, `.synctex.gz`, `.toc`, listas e índices, y el PDF generado `main.pdf`. Conserva `.tex`, `.bib`, `latexmkrc`, imágenes, PDFs fuente y recursos institucionales.

Antes de entregar: busca TODO y EJEMPLO, retira las demostraciones, completa metadatos y resúmenes, comprueba la portada, compila hasta resolver referencias y revisa el PDF completo. Revisa `main.log` y `main.blg`: no deben quedar citas o referencias indefinidas, peticiones de Biber ni cajas desbordadas. Un aviso `Overfull` requiere revisar el elemento afectado; no ocultes los avisos con tolerancias globales. Confirma la normativa enlazada y la tipología del trabajo con tu dirección.
