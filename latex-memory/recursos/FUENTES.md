# Fuentes oficiales y criterio de adaptación

Consulta: 25 de septiembre de 2026. Esta infraestructura es una adaptación, no una plantilla certificada por EINA.

## Normativa EINA

Fuentes: [portal vigente de TFE](https://eina.unizar.es/trabajos-fin-de-estudios) y [Anexo IV enlazado por EINA](https://eina.unizar.es/sites/eina/files/archivos/General/normativa/AnexosTFE/anexo_iv_instrucciones_tfg_tfm_eina.pdf), apartados 2.1–2.5.

| Indicación | Aplicación |
| --- | --- |
| Portada normalizada con datos académicos | Modelo de Biblioteca adaptado; datos en `metadata.tex`. |
| Títulos y resumen en castellano e inglés | Página bilingüe inmediatamente tras la portada. |
| Índice con anexos; numeración consecutiva | Índices automáticos y contador arábigo sin reinicios. Portada contada, cifra oculta como en el modelo oficial. |
| Figuras, tablas y bibliografía numeradas y citadas | Numeración automática, referencias cruzadas e IEEE. |
| Referenciar uso de IA y presentar declaración del Anexo VII | Sección inicial y registro en anexo C; el formulario oficial se cumplimenta aparte. |
| Tipo B: unas 20 páginas o máximo 10.000 palabras, excluidos índices, resumen y bibliografía | Vigilar durante la redacción; anexos de extensión libre. Confirmar tipología con la dirección. |
| Restricción de identidad corporativa empresarial | No se añaden marcas de empresas. El emblema universitario procede de la portada oficial. |

El portal cita el acuerdo de 02/12/2025; el Anexo IV se refiere al de 03/11/2025. Se conserva esta discrepancia de fechas sin atribuirle una resolución propia. No se usa la versión anterior de abril de 2025.

## Modelo oficial de portada

La [Biblioteca de Unizar](https://biblioteca.unizar.es/servicios/deposito-tfgtfm) enlaza [Modelos LATEX](https://biblioteca.unizar.es/sites/biblioteca/files/archivos/modelos_latex.zip). El ZIP original `modelos_latex.zip` se conserva en este equipo como referencia, pero queda excluido de Git; tras clonar, puede obtenerse del enlace oficial. La fuente de portada, sin modificaciones, sí se conserva en [portada_unizar_original.tex](portada_unizar_original.tex).

El logotipo [logo_uz.png](../imagenes/logo_uz.png) procede de `distribucion/1-plantilla-portada/img/logo_uz.png` del ZIP. No es una recreación. El ZIP conserva los archivos y notas de distribución originales; no se atribuye una licencia adicional al material institucional.

La portada activa conserva emblema, Carlito, recuadro azul y orden general. Se ajustan espacios y ancho del recuadro para incorporar departamento, centro, curso y fecha. Comparar el resultado con `portada.pdf` del ZIP al completar títulos y nombres largos.

El cuerpo utiliza decisiones editoriales configurables: A4, 11 pt, Latin Modern, márgenes de 2,5 cm e interlineado 1,1. No se presentan como medidas obligatorias de EINA. IEEE se adopta por petición del usuario; no se encontró imposición de otro estilo concreto en las instrucciones revisadas.
