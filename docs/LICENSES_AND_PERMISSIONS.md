# Licencias y permisos de software y datos

## Matriz de auditoría (actualizada: 2 de octubre de 2026)

Esta matriz distingue usar, modificar, almacenar, generar derivados, publicar
y redistribuir. Una URL pública o un checkpoint descargable no implica que
todas esas acciones estén autorizadas.

| Recurso | Fuente oficial | Uso | Licencia | Datos/pesos | Redistribución | Estado | Acción pendiente |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Datos OSM | [OpenStreetMap](https://www.openstreetmap.org/copyright) | Catálogo, filtros y derivados geográficos | ODbL 1.0, con atribución | Almacenables; registrar snapshot y procedencia | Condicionada por ODbL y tipo de obra/base derivada | PERMITIDO CON CONDICIONES | Revisar obligaciones del artefacto concreto publicado. |
| Overpass API | [Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) | Adquisición/adaptación de OSM | Datos devueltos bajo ODbL; servicio sujeto a política de uso | Cache local razonable y reproducible | Datos según ODbL; no se redistribuye el servicio | PERMITIDO CON CONDICIONES | Respetar límites del endpoint y atribuir OSM. |
| Wikidata | [Wikidata](https://www.wikidata.org/wiki/Wikidata:Copyright) | Enriquecimiento opcional | CC0 para datos estructurados | Almacenables; revisar fuentes enlazadas | Posible para CC0 | PERMITIDO CON CONDICIONES | Mantener procedencia y revisar contenido externo. |
| Código GOTPR | [GitHub](https://github.com/donghwijung/GOTPR) | Extensión de retrieval por grafos | MIT | No cubre automáticamente pesos/datasets | Sí para código, conservando aviso MIT | PERMITIDO CON CONDICIONES | Auditar cada artefacto no incluido en MIT. |
| Checkpoints/datos GOTPR | Recursos enlazados por GOTPR | Extensión GOTPR | No determinada por MIT | Uso, almacenamiento y derivados no confirmados | No redistribuir por defecto | NO CONFIRMADO | Obtener licencia/autorización específica. |
| Código CVG-Text | [GitHub](https://github.com/yejy53/CVG-Text) | Recuperador del MVP mediante wrappers | No localizada | No aplica a datos/pesos | No copiar/modificar/publicar sin permiso | PENDIENTE DE AUTORES | Resolver D016. |
| Checkpoints/dataset CVG-Text | [Hugging Face](https://huggingface.co/CVG-Text/CrossText2Loc) y recursos oficiales | Inferencia CrossText2Loc | No confirmada | Uso y embeddings pendientes | No redistribuir por defecto | PENDIENTE DE AUTORES | Resolver D013 y D016. |
| Código GeoBridge | [GitHub](https://github.com/MiliLab/GeoBridge) | Extensión opcional | No localizada | No cubre pesos/datos | No copiar o publicar adaptación | PENDIENTE DE AUTORES | Resolver D038. |
| Checkpoint GeoBridge | [Hugging Face](https://huggingface.co/Son12s/GeoBridge) | Inferencia opcional | No declarada | `best_net.pth`, 6,87 GB; uso/derivados no confirmados | No redistribuir | PENDIENTE DE AUTORES | Confirmar uso académico y embeddings. |
| GeoLoc | [Hugging Face](https://huggingface.co/datasets/Son12s/GeoLoc) | Datos de referencia de GeoBridge | Paper anuncia CC BY-NC-SA 4.0; release sin card/licencia | Dos RAR *drone*; no vistas de Google | No asumir hasta delimitar cobertura y atribución | PENDIENTE DE AUTORES | Confirmar alcance de licencia por archivo. |
| OpenAerialMap | [OAM](https://openaerialmap.org/legal/) | Posible fuente *drone*/aérea | CC BY 4.0 | Descarga/procesamiento con atribución | Sí, cumpliendo CC BY 4.0 | PERMITIDO CON CONDICIONES | Conservar titular, fuente y metadata por imagen. |
| Google Street View | [Política oficial](https://developers.google.com/maps/documentation/streetview/policies) | Verificación VLM o galería GeoBridge | Términos contractuales | No asumir almacenamiento, evaluación de IA ni embeddings | No redistribuir imágenes/derivados | PENDIENTE DE PROVEEDOR | Confirmar el flujo concreto o usar otra fuente. |
| Google Maps/Earth satélite | [Términos oficiales](https://cloud.google.com/maps-platform/terms) | Satélite opcional/GeoBridge | Términos contractuales | No asumir descarga, cache, transformación o embeddings | No redistribuir | PENDIENTE DE PROVEEDOR | Elegir fuente alternativa o autorización. |
| Futuro proveedor satelital | Por seleccionar | Extensión satelital | Por revisar | Por revisar | Por revisar | NO CONFIRMADO | Resolver D015 antes de adquirir datos. |
| LLM/VLM externo | Proveedor por seleccionar | Parsing o verificación | Según cuenta/modelo | Retención y salidas dependen del contrato | No publicar entradas/salidas/pesos sin revisar | NO CONFIRMADO | Auditar al seleccionar proveedor. |
| DialogueVPR/DQ-pilot | Publicación/repositorio oficial | Extensión de diálogo | No auditada aquí | Pesos/datos por revisar | No redistribuir por defecto | NO CONFIRMADO | Auditoría específica antes de integrar. |
| TOL/TOLoc | [GitHub](https://github.com/WHU-USI3DV/TOL) | Refinamiento opcional | No localizada en revisión previa | Pesos/datos por revisar | No copiar o redistribuir por defecto | PENDIENTE DE AUTORES | Solicitar autorización si se integra. |
| MLLM Retriever | Publicación/recurso oficial pendiente de normalizar | Alternativa opcional | No auditada | Por revisar | Por revisar | NO CONFIRMADO | Identificar artefactos y licencia antes de uso. |

Fuentes oficiales consultadas: [OSM Copyright](https://www.openstreetmap.org/copyright),
[Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API),
[Wikidata Copyright](https://www.wikidata.org/wiki/Wikidata:Copyright),
[términos de Google Maps Platform](https://cloud.google.com/maps-platform/terms),
[términos EEE](https://cloud.google.com/terms/maps-platform/eea),
[CVG-Text](https://github.com/yejy53/CVG-Text) y
[GOTPR](https://github.com/donghwijung/GOTPR),
[GeoBridge](https://github.com/MiliLab/GeoBridge),
[GeoLoc](https://huggingface.co/datasets/Son12s/GeoLoc) y
[OpenAerialMap](https://openaerialmap.org/legal/). La tabla no constituye asesoramiento
jurídico; las condiciones aplicables a una cuenta o recurso concreto deben
confirmarse antes de publicar.

La infraestructura de Fase 2 materializa D043-D048 sin haber realizado una
adquisición real. Antes de usar el endpoint se comprobará su política vigente;
el raw continuará fuera de Git y la publicación de provenance o derivados se
revisará según ODbL.

**Proyecto:** localización geográfica a partir de descripciones textuales en Madrid  
**Fecha de revisión:** 2 de octubre de 2026  
**Estado:** guía de cumplimiento para el desarrollo y la memoria del TFG

Este documento registra las condiciones observadas en los repositorios y fuentes que se prevé utilizar. No sustituye una revisión jurídica ni una autorización escrita de los titulares de derechos. La fecha es relevante porque los autores pueden añadir o modificar una licencia posteriormente.

## Conclusión operativa

El código de [GOTPR](https://github.com/donghwijung/GOTPR) se puede reutilizar bajo la licencia MIT que incluye su repositorio, conservando el aviso de copyright y el texto de la licencia.

GeoBridge permanece como extensión opcional y no puede considerarse todavía una
dependencia reutilizable. En el commit auditado no existe archivo de licencia y
los metadatos públicos del modelo y de GeoLoc no declaran una licencia. La
declaración CC BY-NC-SA 4.0 del artículo para GeoLoc debe aclararse respecto a
los dos archivos *drone* publicados y no cubre automáticamente el código, los
pesos ni contenido de Google.

En [CVG-Text](https://github.com/yejy53/CVG-Text),
[GeoBridge](https://github.com/MiliLab/GeoBridge) y
[TOL](https://github.com/WHU-USI3DV/TOL) no se observa una licencia de software
abierta en los commits/repositorios revisados. Que el código esté publicado en
GitHub permite consultarlo y hacer un fork dentro de GitHub conforme a las
funciones de la plataforma, pero no concede por sí solo permiso general para
copiarlo, modificarlo, redistribuirlo o incorporarlo a otro proyecto.

Por ello, GOTPR puede ser una dependencia reutilizable del proyecto. CVG-Text y TOL pueden estudiarse como referencias; antes de reutilizarlos se debe aclarar la licencia o autorización para el uso concreto. El carácter académico o local de una ejecución no acredita por sí solo permiso. No consta en este documento ninguna autorización individual recibida.

## Estado de cada repositorio

| Recurso | Estado observado | Uso permitido con la información actual | Acción necesaria |
|---|---|---|---|
| [GOTPR](https://github.com/donghwijung/GOTPR) | Declara MIT en `license.txt`. | Usar, estudiar, modificar e integrar el código, incluida una posible redistribución, manteniendo los avisos de MIT. | Conservar `license.txt`, añadir atribución y revisar por separado checkpoints, datasets y dependencias. |
| [CVG-Text](https://github.com/yejy53/CVG-Text) | No se observa licencia de software en el repositorio. | Consultar el código y citar el trabajo. La copia, modificación o redistribución no queda autorizada por el repositorio público. | Pedir autorización escrita a los autores si se va a copiar o redistribuir código. Revisar también las condiciones de los checkpoints y de las imágenes. |
| [GeoBridge](https://github.com/MiliLab/GeoBridge) | No incluye licencia en el commit `636c413c...`; pesos y dataset tampoco declaran licencia en sus metadatos de Hugging Face. | Consultar y citar. No asumir permiso para integrar código, ejecutar los pesos o generar/publicar derivados. | Consultar a los autores; resolver por separado los términos de la fuente de imágenes. |
| [TOL](https://github.com/WHU-USI3DV/TOL) | No se observa licencia de software en el repositorio. | Estudiar la propuesta y citarla. No asumir permiso para integrarlo, modificarlo o redistribuirlo. | Pedir autorización escrita antes de incorporarlo como módulo o publicar una versión adaptada. |

La ausencia de una licencia no significa que el software sea de dominio público. En general, se aplica el copyright por defecto y los derechos permanecen en los autores. Véase la explicación de [GitHub sobre repositorios sin licencia](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).


## Qué permite la licencia MIT de GOTPR

La licencia MIT permite utilizar el código de GOTPR, modificarlo, combinarlo con código propio y redistribuirlo, siempre que se incluya el aviso de copyright y la licencia MIT. También permite un uso académico y comercial.

Esto se aplica al código cubierto por esa licencia. No implica automáticamente que tengan la misma licencia:

- los checkpoints descargados desde servicios externos;
- los datos de KITTI360Pose u otros datasets;
- las imágenes incluidas o descargadas por el proyecto;
- las dependencias de Python;
- los modelos de terceros, como CLIP o modelos de lenguaje.

El proyecto debe conservar una copia de la licencia de GOTPR y registrar las versiones o commits utilizados. No se debe presentar el código adaptado como si fuera completamente original.

## CVG-Text y CrossText2Loc

El repositorio de CVG-Text contiene el código de CrossText2Loc, scripts de evaluación y referencias a checkpoints. La página del repositorio describe cómo obtener el dataset y los checkpoints, pero no muestra una licencia abierta para el código.

Para el TFG se recomienda el siguiente tratamiento:

1. Confirmar las condiciones que permiten ejecutar y evaluar el modelo; no asumir que el uso local resuelve la ausencia de licencia.
2. Citar el artículo, el repositorio y el checkpoint utilizado.
3. Mantener el código original en su repositorio de origen y guardar en el proyecto únicamente los adaptadores propios, configuraciones y scripts escritos desde cero cuando sea posible.
4. No subir al repositorio del TFG una copia completa de CVG-Text, sus checkpoints ni imágenes de terceros.
5. Solicitar permiso si se necesita copiar funciones, modificar archivos del repositorio y publicar esa adaptación como parte del TFG.

El repositorio indica además que las imágenes originales de Street View y de Google Maps no se redistribuyen con el dataset y que deben recuperarse mediante las APIs correspondientes. Por tanto, no se deben incluir esas imágenes en el repositorio público ni en una distribución del dataset sin revisar sus condiciones de uso.

## Uso de Google Street View o Google Maps con un VLM

Google Street View sigue siendo la fuente prevista de fotografías reales para verificar los candidatos del sistema definido en [PROJECT.md](PROJECT.md). Su incorporación está pendiente de confirmar las condiciones del flujo concreto; no se considera libre de restricciones ni universalmente prohibida por tratarse de inferencia.

Hay que distinguir inferencia con un modelo fijo, evaluación de modelos y entrenamiento o ajuste. Verificar si un edificio coincide con una descripción no equivale automáticamente a validar un modelo. Si esas imágenes se emplean para medir o mejorar el sistema, se debe describir también ese uso experimental en la consulta al proveedor.

Las condiciones EEE, sección 3.3.2(c), restringen usar contenido para mejorar modelos, incluyendo entrenamiento, pruebas, validación y ajuste. Esa cláusula no basta para resolver cualquier uso de inferencia. También deben revisarse extracción, almacenamiento, contenido derivado y envío a terceros. El contrato aplicable depende de la cuenta y de las condiciones particulares. Fuentes: [términos EEE](https://cloud.google.com/terms/maps-platform/eea), [términos generales](https://cloud.google.com/maps-platform/terms) y [condiciones específicas](https://cloud.google.com/maps-platform/terms/maps-service-terms).

Borrar una imagen después de procesarla no autoriza el procesamiento ni la descarga. Tampoco pagar la API o seguir las instrucciones de CVG-Text concede permisos adicionales. La política del proyecto es aclarar el uso antes de activar esta integración y obtener autorización contractual si resulta necesaria.

La consulta debe describir la API, cuenta, finalidad académica, inferencia sin entrenamiento, evaluación prevista, proveedor del VLM, transferencia y retención de imágenes, resultados derivados y publicación. No consta todavía una respuesta que confirme este flujo.

Si no puede utilizarse Google, se estudiarán fotografías propias u otra fuente con permisos adecuados. Renderizar mapas OSM permite preparar entradas cartográficas de CrossText2Loc, pero no sustituye la evidencia fotográfica de fachadas, materiales o relojes. El cambio de fuente deberá documentarse.

## TOL y el refinamiento futuro

TOL es una referencia técnicamente pertinente para una posible ampliación, cuya compatibilidad debe comprobarse: su pipeline trabaja con consultas textuales, teselas OSM y poses, y contiene una fase de recuperación y otra de localización fina. El repositorio documenta una estructura de datos con carpetas de imágenes, textos, poses OSM y poses textuales.

La compatibilidad técnica no equivale a permiso legal. Mientras el repositorio no incluya una licencia abierta que cubra el código, el plan recomendado es:

- citar TOL como trabajo relacionado;
- estudiar su arquitectura y sus formatos;
- confirmar las condiciones aplicables antes de ejecutar una prueba local;
- no copiar código ni redistribuir checkpoints sin permiso;
- pedir autorización antes de integrarlo en el código del TFG o publicar una adaptación.

Si se obtiene autorización, debe conservarse el mensaje o documento de autorización junto con el proyecto y describir en la memoria qué partes se reutilizaron y bajo qué condiciones.

## OpenStreetMap y datos derivados

OpenStreetMap distribuye sus datos bajo la [Open Data Commons Open Database License (ODbL)](https://www.openstreetmap.org/copyright). Se debe documentar la procedencia de datos y derivados. La atribución y las obligaciones sobre bases de datos derivadas deben revisarse según el artefacto y su publicación; no todos los mapas, grafos y programas reciben automáticamente la misma licencia. Una base derivada hecha pública puede requerir ofrecerla bajo ODbL.

En la memoria y en cualquier aplicación o material publicado debe aparecer, como mínimo, una atribución equivalente a:

> © OpenStreetMap contributors. Datos disponibles bajo la Open Database License (ODbL). https://www.openstreetmap.org/copyright

También deben conservarse la fecha de descarga, la consulta o área utilizada, la versión o fuente de los datos y cualquier transformación aplicada. Las teselas raster, estilos cartográficos, imágenes satelitales y servicios de terceros pueden tener condiciones adicionales a las de los datos OSM.

## Checkpoints, datasets e imágenes

Antes de redistribuir cualquier artefacto, hay que comprobar su licencia individual. La licencia del repositorio no cubre automáticamente los recursos descargados desde Hugging Face, Google Drive, Baidu, Google Maps, Google Street View u otros servicios.

La política recomendada para este TFG es:

- descargar los checkpoints para uso local cuando sus condiciones lo permitan;
- no incluir los pesos en el repositorio Git del TFG salvo que su licencia lo permita expresamente;
- guardar un enlace al origen, la fecha de descarga, el identificador de versión y la licencia;
- no redistribuir imágenes de Google Street View o Google Maps;
- publicar únicamente los metadatos y scripts propios necesarios para reproducir el proceso, salvo que las licencias permitan compartir los datos.

## Cómo solicitar permiso

La persona u organización a la que hay que solicitar permiso depende del recurso que se quiera utilizar:

| Recurso | Destinatario recomendado | Canal de contacto |
|---|---|---|
| Código de GOTPR | Autores o mantenedores del repositorio, aunque su código ya declara MIT | [Issues de GOTPR](https://github.com/donghwijung/GOTPR/issues) o el perfil institucional de los autores |
| Código y checkpoints de CVG-Text/CrossText2Loc | Autores o mantenedores de CVG-Text | [Issues de CVG-Text](https://github.com/yejy53/CVG-Text/issues) y los perfiles de los autores enlazados desde el repositorio |
| Código, checkpoint y GeoLoc de GeoBridge | Autores o mantenedores de GeoBridge | Correos del paper y [Issues de GeoBridge](https://github.com/MiliLab/GeoBridge/issues); borrador de consulta local en `docs/MAILS.md` (no versionado) |
| Código y checkpoints de TOL/TOLoc | Autores o mantenedores de TOL | [Issues de TOL](https://github.com/WHU-USI3DV/TOL/issues) y los perfiles institucionales enlazados desde el repositorio |
| Datos de OpenStreetMap | No se solicita permiso individual a cada autor; se cumplen ODbL y las condiciones de uso de OSM | [Página oficial de copyright y licencia de OSM](https://www.openstreetmap.org/copyright) |
| Google Street View o Google Maps | Google Maps Platform, mediante el proyecto y la cuenta de Google Cloud que utilizarían la API | [Asistencia de Google Maps Platform](https://developers.google.com/maps/support) dentro de Google Cloud Console |

Para Google Street View o Google Maps no basta con escribir a los autores de CVG-Text. Ellos pueden autorizar el uso de su código o explicar su configuración, pero no pueden conceder derechos sobre imágenes propiedad de Google. La consulta debe dirigirse a Google Maps Platform Support desde la consola de Google Cloud asociada al proyecto de API. Google indica que las solicitudes de soporte se crean desde la página de asistencia de Google Maps Platform en Cloud Console; normalmente se necesita ser propietario, editor o tener permisos de soporte del proyecto. La respuesta debe solicitar expresamente confirmación para descargar, procesar con un VLM, validar resultados, refinar coordenadas, almacenar temporalmente y eliminar después las imágenes.

Si la cuenta de la API pertenece a la universidad, debe intervenir también el administrador del proyecto de Google Cloud o el responsable institucional de la cuenta. El administrador institucional puede tramitar la consulta, pero no conceder derechos de Google. Soporte es una vía de aclaración y derivación al equipo competente, no una garantía de excepción contractual; una excepción debe proceder de una parte facultada y quedar formalizada. La documentación de [soporte](https://developers.google.com/maps/support) indica que sus responsables de escalado no pueden conceder excepciones a términos. No se debe publicar información privada, claves API ni archivos con datos personales en una issue.

La solicitud debe especificar:

- nombre y finalidad académica del TFG;
- repositorio y archivos que se quieren reutilizar;
- si se copiará, modificará o solo ejecutará el código;
- si el código adaptado se publicará y dónde;
- si se redistribuirán checkpoints, imágenes o datasets;
- cómo se citará a los autores;
- qué licencia se pretende aplicar al código propio.

## Registro que debe conservar el proyecto

Se recomienda crear y mantener una tabla de terceros con estas columnas:

| Recurso | URL | Commit o versión | Licencia | Uso realizado | Atribución | Evidencia del permiso |
|---|---|---|---|---|---|---|
| GOTPR | URL del repositorio | Pendiente | MIT | Código y adaptadores | Sí | `license.txt` |
| CVG-Text | URL del repositorio | Pendiente | No localizada | Referencia; ejecución pendiente de aclaración | Prevista | No consta autorización recibida |
| GeoBridge | URL del repositorio/modelo | `636c413c...` / `959a40ce...` | No localizada para código/pesos | Extensión opcional; solo auditoría | Prevista | No consta autorización recibida |
| GeoLoc | URL del dataset | `cb3de0ca...` | CC BY-NC-SA 4.0 anunciada en paper; no declarada en release | No descargado | Prevista | Alcance pendiente de autores |
| TOL | URL del repositorio | Pendiente | No localizada | Referencia o futura ampliación | Prevista | No consta autorización recibida |
| OpenStreetMap | URL de copyright | Fecha de descarga | ODbL | Datos, imágenes o grafos derivados | Sí | Metadatos de descarga |
| Google Street View / Google Maps | [Google Maps Platform](https://cloud.google.com/maps-platform/terms) | Fecha de consulta | Términos de Google Maps Platform | Verificación fotográfica con VLM prevista; uso concreto pendiente de aclaración | Según contrato y API | Confirmación pendiente; autorización adicional si procede |

Mientras se aclaran los permisos, puede avanzarse en código propio y componentes con licencia compatible. Publicar adaptadores propios o enlaces no concede derechos sobre los componentes externos ni resuelve sus condiciones de ejecución. Se conservarán las licencias y autorizaciones efectivamente verificadas, diferenciándolas de solicitudes pendientes.

## Estado respecto al roadmap actual

La Fase 0 se ha implementado únicamente con código propio de contratos,
schemas, validadores y provenance. No se han descargado checkpoints, imágenes,
datasets ni datos OSM durante esta fase.

La independencia del proveedor LLM está aceptada. El proyecto seleccionará
posteriormente un proveedor compatible con el JSON Schema, calidad,
reproducibilidad, latencia y coste requeridos. Esa elección deberá revisar las
condiciones de entrada, salida, retención y publicación del proveedor.

Las licencias no bloquean el desarrollo de adaptadores propios, geometría,
loaders, validadores o métricas con fixtures. Sí condicionan estas etapas:

- CrossText2Loc no se integrará definitivamente hasta resolver D007, D013 y
  D016;
- GOTPR permanece condicionado por D011 y por las licencias de sus artefactos;
- satélite permanece fuera del MVP por D014 y depende de D015;
- Street View/VLM, diálogo y TOLoc son extensiones posteriores sujetas a sus
  propias condiciones.
- GeoBridge es una extensión opcional por D036; su uso depende de D038 y D039,
  y no habilita por sí mismo imágenes de Google ni embeddings derivados.

Las fases 5 y 6 pueden avanzar mientras se espera la respuesta de los autores de
CVG-Text. Ninguna fase debe copiar, modificar o redistribuir código, pesos o
datos de `external/` sin comprobar las condiciones correspondientes.
