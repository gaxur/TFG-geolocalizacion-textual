# Selección del motor de generación estructurada I01-I20

## Diagnóstico del timeout v7

El wrapper LMFE v7 realizaba trabajo multiplicativo:

- por generación reconstruía datos y trie para unos 151.000 tokens;
- por token generado materializaba la secuencia completa y decodificaba el
  prefijo completo;
- reconstruía y reproducía el parser sobre todos los caracteres del prefijo;
- recorría allowlists de hasta unos 148.000 IDs en strings libres;
- para candidatos sospechosos volvía a decodificar y reproducir el prefijo.

El benchmark CPU con 147 tokens contractuales midió una mediana de 562,97 ms por
paso para v7 y 583,10 ms en free text. La extrapolación lineal de la mediana es
288 s para 512 tokens y 1.153 s para 2.048 tokens. No es tiempo de inferencia GPU
medido, pero concuerda con el timeout de 900 s y demuestra que el overhead de
restricción no es operativo.

LMFE original fue más rápido, 2,77 ms de mediana, pero rechazó un token válido al
cerrar `description_es` y mantiene los defectos de corrección ya observados. No
es una alternativa segura.

## Benchmark reproducible

Entorno: ARM64, Python 3.12.3, Transformers 5.9.0, LMFE 0.11.3, XGrammar 0.2.1,
tokenizer Qwen local, vocabulario de cabeza 151.936 y ambos EOS. Documento:
147 tokens y 628 caracteres con descripción española, claims, arrays, objetos,
booleanos, null y orientación.

| Métrica | LMFE original | LMFE v7 | XGrammar matcher | XGrammar + máscara CPU |
|---|---:|---:|---:|---:|
| Setup principal | 1,95 s | 2,01 s | 1,27 s compilación | igual |
| Mediana por paso | 2,774 ms | 562,965 ms | 0,0148 ms | 0,5355 ms |
| P95 free text | no completó documento | 655,009 ms | 0,518 ms `fill` | 0,572 ms máscara global |
| Extrapolación 512 tokens | 1,42 s | 288,24 s | 7,58 ms | 274,19 ms |
| Extrapolación 2.048 tokens | 5,68 s | 1.152,95 s | 30,31 ms | 1.096,78 ms |

Las extrapolaciones multiplican la mediana por el número de tokens. No incluyen
inferencia, carga del modelo, transferencia del bitmask a GPU ni variación del
estado gramatical.

El presupuesto adoptado es:

- matcher mediano inferior a 1 ms/token;
- matcher más aplicación de máscara CPU inferior a 2 ms/token;
- ningún estado sostenido en segundos/token.

XGrammar cumple con amplio margen. LMFE v7 no cumple.

## Corrección y seguridad

XGrammar 0.2.1 se probó con el tokenizer Qwen real y el schema v7/v8:

- acepta Unicode español;
- bloquea el token 5959 de ocho saltos dentro de una cadena;
- bloquea ambos EOS mientras el documento está incompleto;
- exige campos obligatorios;
- acepta booleanos, null, arrays, objetos y `$defs`;
- permite ambos EOS después de completar el objeto;
- su `LogitsProcessor` HF aplica un bitmask comprimido incremental;
- el resultado final sigue pasando por `json.loads`, Draft 2020-12 y validación
  semántica propia.

No se repara el raw ni se reintenta. Una transición rechazada, límite de tokens,
JSON inválido o contrato inválido sigue siendo un fallo terminal del ledger.

## Comparación

| Criterio | LMFE v7 | LMFE optimizado | XGrammar 0.2.1 |
|---|---|---|---|
| JSON por construcción | Guard local, no completó sonda | Posible, no implementado | Sí, gramática compilada |
| Unicode español | Corregido, muy lento | Requeriría más ingeniería | Probado |
| EOS seguro | Guard local | Posible | Probado con ambos EOS |
| Arrays/objetos | Sí | Sí | Probado |
| Schema actual | Sí, con limitaciones LMFE | Igual | Compila y replay completo |
| Coste por paso | ~563 ms mediana | No medido | ~0,535 ms con máscara CPU |
| Memoria CPU | Pico global ~2,0 GB | Desconocida | Gramática ~182 MB; pico global ~2,0 GB |
| Complejidad operativa | Alta | Alta | Adaptador HF local pequeño |
| Riesgo principal | Timeout/corrección | Nueva implementación | Semántica Draft final requiere jsonschema |

## Decisión

Se selecciona XGrammar para la revisión v8. Optimizar LMFE exigiría caches,
parser incremental y tratamiento de ramas/tokenización, manteniendo riesgos ya
materializados. XGrammar ofrece bitmask nativo, estado incremental y una mejora
medida de tres órdenes de magnitud en matcher.

No se adopta generación por fases: aumentaría llamadas, coste y contradicciones,
y dificultaría spans. No existe evidencia de necesidad tras seleccionar un motor
estructurado eficiente.

## Trazabilidad v8

Se congelan versión y hashes locales del binario XGrammar y de su adaptador HF.
La autorización v8 permanece desactivada y limitada a una futura sonda I01 de
una anotación, cero escenas y una llamada total.
