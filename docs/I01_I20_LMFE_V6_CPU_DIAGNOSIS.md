# Diagnóstico CPU del fallo LMFE en la anotación v6

## Evidencia preservada

`raw.json` conserva 49 caracteres, su SHA-256, 20 tokens generados, el último
token EOS y métricas de tiempo/CUDA. No conserva la lista de IDs de los 20 tokens.
Por tanto, no puede reproducirse exactamente la secuencia original. Las pruebas
con IDs obtenidos al volver a tokenizar el raw se identifican expresamente como
sintéticas, aunque su decodificación round-trip coincide con el raw.

## Causa demostrada

El parser de caracteres no permite un salto de línea literal dentro de una
cadena JSON abierta y no permite terminar el documento en ese estado. El fallo
aparece antes:

1. La integración construye `JsonSchemaParser` con su alfabeto inicial.
2. `TokenEnforcer.__init__` sustituye después `parser.config.alphabet` por el
   alfabeto del tokenizer, pero `JsonSchemaParser.context.alphabet_without_quotes`
   ya había quedado calculado con el alfabeto anterior.
3. El atajo de free text permite tokens según la representación precalculada del
   tokenizer. En la re-tokenización sintética del raw, el token `ía` se permite.
4. Al aplicarlo, `í` no figura en `alphabet_without_quotes` desactualizado.
5. `JsonSchemaParser.add_character` recorre hacia abajo la pila buscando un
   receptor. Si ninguno acepta el carácter, no lanza una excepción: construye
   una pila vacía y descarta silenciosamente el carácter.
6. Una pila vacía hace que `can_end()` sea verdadero. Desde ese momento LMFE
   permite EOS aunque el texto finalmente decodificado siga dentro de
   `description_es`.
7. El token de ocho saltos de línea también queda permitido por el estado interno
   ya terminado. La aplicación recibe un JSON distinto e incompleto.

La reproducción con tokenizer Qwen local, sin pesos, mostró que el parser
original permite EOS tras `ía`. Si se construye desde el principio con
`CharacterLevelParserConfig(alphabet=tokenizer_data.tokenizer_alphabet)`, `ía`
mantiene el documento abierto, EOS sigue prohibido y el token de ocho saltos de
línea queda rechazado.

LMFE tiene además dos rutas fail-open secundarias: convierte excepciones al
aplicar caracteres en `ForceStopParser`, cuyo `can_end()` es verdadero, y ante
errores internos al calcular tokens permite únicamente EOS.

## Solución local

No se modifica `site-packages`. El adaptador local:

- construye los datos del tokenizer antes del parser;
- crea el parser con el alfabeto definitivo desde el inicio;
- usa una instancia fresca por generación;
- revalida siempre el prefijo con la decodificación final de Transformers;
- revalida contextualmente tokens con controles o representación divergente;
- permite cualquier EOS configurado solo si el prefijo final puede terminar;
- lanza un error si no queda ningún token válido;
- conserva en futuros diagnósticos los IDs exactos generados.

No repara el raw ni añade reintentos. `json.loads`, Draft 2020-12 y las reglas
semánticas posteriores siguen siendo obligatorios.

## Alternativas

| Estrategia | Evaluación |
|---|---|
| Corregir integración LMFE | Seleccionada. Resuelve la causa demostrada sin cambiar prompt/schema ni dependencias instaladas. |
| XGrammar local | Está instalado, pero no se ha comprobado su integración con Qwen3-VL/Transformers en este flujo. Cambiar de motor añade riesgo sin necesidad demostrada. |
| Generación en fases | Aumentaría llamadas, coste y riesgo de contradicción; complica spans y cambia prompts/contratos. No se justifica antes de probar la corrección mínima. |

## Límites

Las pruebas CPU demuestran exclusión de controles literales, EOS cerrado,
booleanos, arrays, objetos, campos obligatorios y compatibilidad con el tokenizer
local. No demuestran calidad visual ni que una inferencia futura vaya a completar
el documento. La revisión v7 permanece desautorizada.
