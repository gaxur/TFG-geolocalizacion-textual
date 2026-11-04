# Revisión de autorización para la comparación A/B

**Fecha de revisión técnica:** 29 de octubre de 2026.

## Fuentes oficiales accesibles

1. Licencia de imágenes Mapillary:
   <https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data>
2. Acceso mediante Mapillary API:
   <https://help.mapillary.com/hc/en-us/articles/360010234680-Accessing-imagery-and-data-through-the-Mapillary-API>
3. Documentación de desarrolladores enlazada oficialmente:
   <https://www.mapillary.com/developer/api-documentation/>
4. Términos enlazados por Mapillary:
   <https://www.mapillary.com/terms>

La URL de términos devolvió HTTP 400 a esta pasarela. Debe revisarse en la sesión
autenticada de la aplicación antes de aprobar.

## Expresamente verificado

- Mapillary declara todas las imágenes CC BY-SA 4.0.
- Permite observar, distribuir y modificar con atribución y condiciones de la
  licencia.
- El ejemplo oficial de atribución incluye título/enlace de imagen, usuario/enlace
  de perfil y licencia.
- Existe una API oficial y la ayuda remite a la documentación completa.

## Interpretación condicionada

- CC BY-SA permite reproducción/adaptación, pero la página accesible no menciona
  explícitamente análisis automatizado o inferencia con IA.
- La inferencia local con Qwen3-VL de pesos fijos no es entrenamiento, pero debe
  confirmarse frente a los términos de acceso de la aplicación.
- El almacenamiento temporal privado puede ser compatible con el uso descrito,
  pero su alcance/retención debe confirmarse en los términos aplicables.
- Publicar métricas y veredictos sin redistribuir imágenes reduce obligaciones de
  distribución de bytes, pero no elimina atribución, privacidad u otros derechos.

## Autorización individual frente a fundamento público

Las fuentes públicas revisadas no establecen una obligación general de obtener
una carta o correo individual de Mapillary para reutilizar imágenes. La licencia
CC BY-SA 4.0 es una licencia pública: su sección 2(a)(1) concede reproducción y
adaptación, y su sección 3 fija atribución y ShareAlike cuando se comparte. La
sección 2(b)(1) advierte que privacidad y derechos de imagen no quedan
licenciados.

Por tanto, la referencia documental del gate puede ser el conjunto de licencia,
términos y documentación oficial, en lugar de una aprobación particular del
proveedor. `approved_by` identifica al responsable interno que acepta esas
condiciones para esta ejecución; no afirma que Mapillary haya emitido una
aprobación individual. Si el panel de la aplicación muestra términos adicionales,
estos prevalecen para el acceso y deben registrarse.

## Revisión pública de 29 de octubre de 2026

- La documentación API se recuperó correctamente siguiendo la redirección y
  documenta `thumb_1024_url`, las entidades de imagen y estos límites publicados:
  60.000 peticiones/minuto/aplicación para entidades, 10.000 para búsquedas y
  50.000 teselas/día.
- La ayuda de privacidad indica difuminado automático de caras y matrículas; el
  editor de difuminado permite reportar omisiones. El experimento no debe intentar
  desdifuminar, identificar personas ni explotar matrículas.
- No se encontró en las fuentes accesibles una retención máxima impuesta por la
  licencia. La eliminación propuesta `2027-01-31T23:59:59Z` es una salvaguarda
  interna compatible con CC BY-SA, pero debe ser aceptada por el responsable y no
  contradecir términos adicionales de la aplicación.
- La inferencia local con pesos fijos no aparece expresamente regulada en las
  páginas públicas accesibles. CC BY-SA permite reproducción/adaptación, pero esa
  conclusión no sustituye revisar los términos de acceso aplicables a la cuenta.
- La página de términos se recuperó con HTTP 200 mediante redirección, pero su
  contenido contractual no fue extraíble de forma fiable por esta pasarela. No se
  marca por ello `terms_reviewed=true`.

## Pendiente de confirmación

- Revisión por el titular de los términos efectivos de la aplicación y cuenta.
- Ausencia o registro de condiciones específicas, facturación y límites más
  restrictivos que las cuotas públicas documentadas.
- Descarga de los 474 IDs exactos y 1.024 px.
- Retención y eliminación.
- Inferencia fija 2B/8B.
- Tratamiento de personas, matrículas, difuminado y privacidad.
- Restricciones adicionales o comerciales.

## Alcance solicitado

- manifests A/B congelados;
- unión 511 imágenes, 37 disponibles y 474 pendientes;
- estimación 57.670.476 B;
- máximo duro 3.792.000.000 B;
- caché privada `data/cache/mapillary/`;
- Qwen3-VL-2B/8B sin entrenamiento ni fine-tuning;
- sin dataset público;
- atribución y procedencia por asset.

El archivo que debe completarse es:

`config/h16_h23_selector_comparison_authorization.request.json`.

La aprobación interna requiere `approved=true`, `terms_reviewed=true`,
identidad/fecha del responsable, fecha límite de retención y todas las
confirmaciones del operador en `true`. El fundamento puede ser público o una
autorización individual si existiera; solo esta segunda modalidad exige una
referencia individual. Cualquier cuota o condición adicional debe registrarse en
`notes`.
