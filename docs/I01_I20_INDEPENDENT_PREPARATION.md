# Preparación del conjunto independiente I01–I20

## Estado

La preparación técnica está completa y la recogida permanece bloqueada. No se
han creado observaciones, consultado APIs, adquirido imágenes, ejecutado modelos
ni abierto el test H38–H61.

El conjunto propuesto es una validación one-shot de transferencia. No será un
nuevo conjunto de ajuste. Cualquier política diseñada después de ver I01–I20
necesitará otro conjunto independiente.

## Viabilidad

Es viable preparar veinte observaciones con garantías razonables si se cumplen
cuatro condiciones críticas:

1. campaña manual propia dentro del ámbito fijo;
2. custodio independiente para el ledger ciego;
3. dos revisores humanos ciegos y adjudicación;
4. al menos 12 observaciones válidas después de exclusiones.

Actualmente estas condiciones están pendientes de autorización y asignación de
personas. No se reduce ningún requisito para alcanzar artificialmente veinte
filas.

## Fuente recomendada

### Primaria: fotografías y GNSS propios

Es la fuente recomendada porque permite controlar:

- posición del observador mediante múltiples lecturas GNSS;
- precisión reportada por el dispositivo;
- heading de cámara u observador, o declarar que es desconocido;
- sesión, momento y procedencia;
- separación entre referencia y eventual verificación;
- consentimiento, privacidad y política de publicación;
- descripción española redactada antes del retrieval.

La selección se congela por bloques antes del campo y no utiliza rankings,
fuerza OSM, candidatos, resultados visuales ni dificultad esperada. No se deben
elegir puntos por estar cerca del centro de una celda.

La nueva campaña no reinterpreta la decisión remota específica de H26–H61; usa
IDs `I01–I20`, protocolo y autorización propios.

### Fallback: Mapillary nuevo

Es técnicamente viable, pero su coordenada de cámara suele tener precisión
desconocida y el heading no equivale a orientación corporal. Debe formar un
conjunto remoto separado y reportarse como referencia aproximada. La autorización
de adquisiciones anteriores no se reutiliza.

No se recomienda mezclar ambas fuentes en la métrica principal: fuente,
precisión, encuadre y descripción quedarían confundidos con el rendimiento.

### Alternativas descartadas por ahora

- Commons: coordenadas de objeto, no de cámara, y piloto negativo.
- Panoramax: cobertura y precisión local insuficientes.
- KartaView: sin snapshot local reproducible y términos pendientes.
- Street View: píxeles no conservados y uso condicionado.
- Fuente mixta: heterogeneidad difícil de interpretar con veinte casos.

## Selección I01–I20

- IDs exactos `I01` a `I20`.
- Cuadrícula de bloques de 150 m en EPSG:25830.
- Al menos diez bloques.
- Máximo dos observaciones por bloque.
- Separación objetivo de 75 m.
- Máximo una sustitución pre-freeze por slot, bajo las mismas reglas ciegas.
- Ninguna sustitución después de ver rankings o resultados.

Los 75 m no demuestran independencia. Se comprueban además:

- image ID y bytes;
- SHA-256 y hashes perceptuales;
- sesión/secuencia;
- escena y campo de visión;
- objetos distintivos compartidos;
- cercanía temporal y perspectiva;
- solapamiento con referencias y vistas de verificación históricas;
- revisión humana de casos ambiguos.

Un candidato `REVIEW` del ledger queda bloqueado, nunca se interpreta como
aceptado.

## Frontera ciega

### Propósito

Un custodio autorizado compara un lote congelado contra el material reservado.
El workspace de desarrollo no monta, indexa ni transforma H38–H61.

La salida por candidato contiene exclusivamente:

- `CLEAR`;
- `EXCLUDE`;
- `REVIEW`.

No devuelve IDs, imágenes, coordenadas, distancias, scores, umbrales, número de
coincidencias, detector o razón.

### Flujo

1. Desarrollo congela un release completo y asigna UUID opacos.
2. Calcula compromisos SHA-256 de los candidatos y del manifest.
3. Firma y entrega una única solicitud cifrada por lote.
4. El custodio valida autorización, compromiso y presupuesto.
5. Ejecuta dentro de su dominio controles exactos, perceptuales, de secuencia y
   escena.
6. Los casos ambiguos se revisan dentro del dominio del custodio.
7. Devuelve la respuesta tri-state completa, canónica y firmada.
8. Desarrollo verifica firma, compromiso y cardinalidad.
9. `EXCLUDE` se retira irreversiblemente y `REVIEW` queda bloqueado.
10. El custodio firma una atestación administrativa y elimina copias de trabajo
    según su política.

### Riesgos de filtración

| Riesgo | Mitigación |
|---|---|
| Consultas adaptativas | Un lote por release; sin API interactiva; repetición con doble aprobación |
| Membership inference | Releases precomprometidas, cuotas pequeñas y procedencia obligatoria |
| Diccionario de hashes | Holdout protegido con HMAC; nunca publicar hashes desnudos |
| Reconstrucción por distancias | Salida tri-state sin scores, vecinos ni umbrales |
| Fuga por razones | Sin códigos por detector ni texto libre |
| Diferencias temporales | Procesamiento asíncrono por ventanas, sin tiempos por candidato |
| Lotes diferenciales | Bloqueo de entradas exactas o perceptualmente próximas ya consultadas |

El tri-state contiene inevitablemente información de pertenencia limitada. La
seguridad depende también de gobernanza, baja capacidad de consulta y separación
de responsabilidades, no solo de criptografía.

### Responsable independiente

Debe ejecutar:

- acceso e indexación del holdout;
- claves HMAC/Ed25519 y almacenamiento separado;
- controles contra el holdout;
- revisión humana de escenas ambiguas;
- respuesta y atestación firmadas;
- ledger append-only y gestión de excepciones;
- borrado de copias temporales.

El workspace solo puede validar schemas, compromisos, firmas con claves públicas,
cardinalidad, estados y ausencia de campos prohibidos. Las firmas reales y la
eficacia de detectores no se validan aquí hasta que exista custodio.

## Paquete de anotación

La preparación genera una plantilla vacía, no datos de ejemplo. El paquete real
contendrá:

```text
i01-i20-annotation/
  PACKAGE_MANIFEST.json
  ANNOTATION_INSTRUCTIONS.md
  observations.json
  references/
  checksums.sha256
```

El descriptor ve una única referencia autorizada. No ve coordenadas, mapa,
candidatos, OSM, rankings, scores ni predicciones.

Cada observación registra:

- ID opaco y hash de referencia;
- descriptor y fecha;
- descripción original española;
- claims atómicos enlazados por spans literales;
- certeza y observabilidad;
- OCR requerido;
- frame de orientación;
- incertidumbres y limitaciones.

Orientación de cámara y cuerpo se mantienen distintas. Una orientación
desconocida conserva bearing e incertidumbre nulos. Solo una orientación
verificada y con incertidumbre permite conversión cardinal.

## Revisión humana

Dos personas revisan independientemente:

- fidelidad de la descripción;
- observabilidad;
- spans y atomicidad;
- incertidumbre;
- orientación;
- uso de conocimiento externo o inferencia de lugar.

No ven GT, revisión de la otra persona ni predicciones. Un desacuerdo global, de
claim, orientación o leakage exige adjudicación ciega. El adjudicador puede
eliminar o degradar claims, elegir una interpretación o excluir la fila; no puede
introducir hechos nuevos. Una corrección sustancial implica exclusión.

## Ground truth separado

El custodio GT trabaja con el registro de posición, no con la descripción:

- múltiples lecturas GNSS originales;
- método y precisión reportada;
- posición de cámara/observador, nunca del objeto mencionado;
- incertidumbre y validación;
- hash del registro fuente;
- revisor distinto y ciego a predicciones.

Las asignaciones a 25/50 m se derivan después mediante código geométrico. La
precisión no se infiere del número de decimales. Los casos ambiguos pueden seguir
sirviendo para GeoRecall si la incertidumbre se informa, pero no se fuerzan a una
celda exacta.

## Freeze de políticas

Freeze:

`i20-policy-freeze-sha256-d3d255310369a00d30669216a7d26bad46ca44ca3632946a10d3e26f009dc55b`

### CT2L

Es el único brazo primario ejecutable directamente sobre textos nuevos. Mantiene
checkpoint, galería Madrid 50 m, embeddings, contexto textual y Top-100.

### Atlas v3

La política está congelada, pero el bundle histórico contiene únicamente las 12
peticiones H26–H37. Para texto nuevo devuelve fallback CT2L exacto. Ese fallback
no puede contabilizarse como resultado Atlas.

Atlas solo será un brazo primario si se aprueba y genera evidencia I-específica:
Top-50 nuevo, vistas candidatas autorizadas, claims congelados, inferencia
Qwen3-VL-8B con la revisión histórica y la misma fórmula `beta=0,1`. De lo
contrario se declara no disponible.

### V4 y v5

Son diagnósticos, no políticas seleccionables. V4 necesita un runner genérico
sobre Top-100 y F3; debe declarar el mismatch de snapshots. V5 requiere además
evidencia visual y fallback Atlas completo. No se permite sustituir Atlas por
CT2L silenciosamente ni reutilizar rankings H26–H37.

Ninguna política admite recalibración con I01–I20.

## Evaluación one-shot

Una ejecución por política congelada, salvo fallo operativo documentado antes de
abrir GT. Mismas observaciones, galería y presupuesto Top-100.

Métricas:

- GeoRecall@1/5/10 a 50 y 100 m;
- sensibilidad 25/50/75/100 m;
- media y mediana Top-1;
- mejoras/degradaciones pareadas;
- máxima degradación;
- cobertura Top-100;
- cobertura de política y abstención.

Se publican conteos, proporciones, tabla por consulta e intervalos descriptivos.
No se afirma significación ni generalización con veinte consultas. No se usa
score compuesto.

El orden es obligatorio: freeze anotación y GT, freeze políticas, rankings sin
GT, freeze rankings, apertura única del GT, evaluación. I01–I20 no selecciona una
nueva política.

## Presupuesto

### Campaña manual recomendada

| Actividad | Estimación |
|---|---:|
| Diseño/preflight | 2–3 h |
| Recogida de 20 observaciones | 5–8 h |
| Ingesta, hashes y GNSS | 2–4 h |
| Primera revisión | 3–5 h |
| Segunda revisión | 3–5 h |
| Freeze y solapamiento | 1–2 h |
| Total humano | 16–27 h, más trabajo del custodio |
| Coste de oportunidad | 240–675 EUR |
| Transporte/material | 5–30 EUR |
| Almacenamiento | menos de 1 GB esperado |

La preparación autorizada actual consume 0 segundos GPU y 0 llamadas de red.
CT2L/Atlas se presupuestarán por separado tras congelar el dataset. Atlas implica
una nueva campaña VLM y no está incluido en la siguiente autorización mínima.

### Fallback Mapillary

13–24 horas humanas, aproximadamente 195–600 EUR de coste de oportunidad y
adquisición específica sujeta a licencia/términos. Sus resultados se separarían
por fuente y precisión.

## Riesgos y parada

Gates críticos pendientes:

- autorización de campo, privacidad y consentimiento;
- custodio ciego independiente;
- dos revisores;
- GT interpretable;
- capacidad de ejecutar Atlas real, si se desea ese brazo.

Se detiene si:

- quedan menos de 12 observaciones válidas;
- no existe frontera de custodia;
- la incertidumbre GT no está documentada;
- hay solapamiento referencia/verificación;
- se rompe el cegamiento;
- se modifica descripción o política tras freeze;
- Atlas solo puede hacer fallback.

## Ablación cartográfica

El plan G/GS/GSN/FULL permanece secundario y bloqueado. Resolvería atribución de
representación, no generalización. Presupuesto conservado: 1.012 PNG, unos
209 MB, 24 minutos CPU, 66 segundos GPU estimados y hasta 12 GB tmpfs. No se ha
ejecutado ninguna parte.

## Autorización siguiente solicitada

La solicitud mínima es exclusivamente:

1. campaña manual de hasta veinte observaciones en bloques precongelados;
2. una comprobación ciega por lotes operada por custodio independiente;
3. dos revisiones humanas y adjudicación.

No se solicita todavía GPU, Atlas/Qwen3-VL, evaluación, adquisición Mapillary ni
ablación cartográfica.
