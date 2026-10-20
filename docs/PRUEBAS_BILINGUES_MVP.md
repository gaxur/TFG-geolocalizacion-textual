# Pruebas bilingües y revisión manual del MVP

## Objetivo y alcance

Este documento reúne dos comprobaciones distintas:

1. un check automatizado inglés-español sobre la aplicación desplegada;
2. una revisión visual manual con ubicaciones de referencia aproximadas.

Ambas recorren frontend/proxy → API → CrossText2Loc → Top-K, pero ninguna mide
por sí sola precisión geográfica.

Estas pruebas no forman un dataset de evaluación ni aportan métricas del TFG. Las
coordenadas son referencias manuales aproximadas, no *ground truth* validado. Las
descripciones tampoco proceden de observaciones humanas recogidas mediante el
protocolo previsto para la evaluación formal.

## Check bilingüe automatizado

El script `scripts/check_mvp_bilingual.py` reutiliza los tres pares controlados
inglés-español de `config/madrid_f45_linguistic_robustness.json`. Ejecuta seis
comparaciones: tres pares sobre la galería de 50 m y los mismos tres sobre 25 m.

Primero desplegar el MVP:

```bash
scripts/run_mvp3_stack.sh -d
```

Después ejecutar desde la raíz:

```bash
python scripts/check_mvp_bilingual.py \
  --base-url http://127.0.0.1:8080 \
  --output results/generated/mvp3/bilingual-check.json
```

Desde otro equipo de la LAN puede utilizarse `http://IP_PGX:8080`, siempre que
el archivo de configuración de consultas también esté disponible localmente.

El informe contiene, para cada par y galería:

- IDs Top-1 en inglés y español;
- coincidencia o cambio de Top-1;
- candidatos compartidos en Top-K;
- Jaccard del Top-K;
- distancia entre las coordenadas de ambos Top-1.

Estas magnitudes describen **estabilidad lingüística**. Un Top-1 idéntico puede
ser incorrecto y una distancia entre salidas no es error respecto a la ubicación
real. El script no usa las coordenadas de referencia de este documento, no
calcula accuracy y no modifica rankings.

F4.5 dispone además de una prueba científica más amplia con 27 variantes:
`scripts/run_f4_linguistic_rankings.sh` y
[PHASE4_LINGUISTIC_ROBUSTNESS.md](PHASE4_LINGUISTIC_ROBUSTNESS.md). Esa prueba
ejecuta el runtime directamente; el nuevo check verifica específicamente el
transporte HTTP de la aplicación desplegada.

### Ejecución observada en la PGX

El check se ejecutó el 19 de octubre de 2026 contra
`http://127.0.0.1:8080`, con Top-10 y ambas galerías. Las 12 peticiones HTTP
terminaron correctamente y produjeron seis comparaciones inglés-español:

| Grupo | Galería | Top-1 igual | Compartidos Top-10 | Jaccard@10 | Distancia entre Top-1 |
|---|---|---:|---:|---:|---:|
| Plaza | 50 m | No | 0 | 0,000 | 111,9 m |
| Plaza | 25 m | No | 0 | 0,000 | 160,0 m |
| Parque | 50 m | No | 1 | 0,053 | 461,0 m |
| Parque | 25 m | No | 0 | 0,000 | 727,7 m |
| Intersección | 50 m | No | 2 | 0,111 | 50,1 m |
| Intersección | 25 m | No | 0 | 0,000 | 56,0 m |

El informe local está en `results/generated/mvp3/bilingual-check.json`, fuera de
Git. Los resultados son coherentes con la inestabilidad lingüística técnica ya
observada en F4.5. No demuestran que el inglés sea correcto ni que el español
sea menos preciso: no existe ground truth para estas sondas.

## Ámbito del piloto

La galería actual cubre la bbox D004 definida en `config/madrid.yaml`:

| Límite | Coordenada WGS84 |
|---|---:|
| Norte | 40.4200 |
| Sur | 40.4120 |
| Este | -3.6990 |
| Oeste | -3.7090 |

Solo deben utilizarse referencias situadas dentro de este ámbito. Un lugar fuera
de la bbox no puede aparecer como candidato correcto en las galerías actuales.

## Cómo redactar una descripción útil

CrossText2Loc compara el texto con imágenes OSM cenitales orientadas al norte.
Por ello, más detalle no implica necesariamente una consulta mejor. Conviene
priorizar elementos que puedan estar representados en el mapa:

- forma y tamaño relativo de plazas, parques y manzanas;
- calles que desembocan en un espacio y anchura relativa de las vías;
- zonas peatonales, cruces, avenidas y trazado regular o irregular;
- densidad de edificios y relación entre espacios abiertos próximos;
- posición cardinal solo cuando se conoce de manera fiable.

Los colores, materiales, escaparates, logotipos, carteles, relojes y apariencia
de fachadas pueden influir en el embedding textual, pero normalmente no tienen
una evidencia equivalente en la imagen OSM. Añadirlos puede no cambiar el
ranking o incluso introducir ruido. Para comprobarlo, se recomienda ejecutar
primero la versión cartográfica de cada caso y después una variante visual con
el mismo contexto base.

## Casos detallados

### Plaza, estación de Cercanías y torre con reloj

**Referencia exploratoria aproximada:** entorno de Puerta del Sol,
`40.41694, -3.70361`.

**Descripción original en inglés:**

> I am in a plaza and to my right I have a commuter train station, and just
> behind me there is a tower with a clock.

**Traducción al español:**

> Estoy en una plaza y a mi derecha hay una estación de tren de Cercanías. Justo
> detrás de mí hay una torre con un reloj.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41694&mlon=-3.70361#map=18/40.41694/-3.70361)

### Plaza, Pans & Company y cartel de Schweppes

**Referencia exploratoria:** entorno de Callao y edificio Capitol. La coordenada
del cartel, `40.4202891, -3.7063716`, está fuera del límite norte de la bbox.

**Descripción original en inglés:**

> I'm in a square and to my right there's a Pans & Company and to my left a big
> building with a Schweppes brand sign.

**Traducción al español:**

> Estoy en una plaza y a mi derecha hay un Pans & Company. A mi izquierda hay un
> edificio grande con un cartel de la marca Schweppes.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.4202891&mlon=-3.7063716#map=18/40.4202891/-3.7063716)


**Nota:** Se puede observar un gran contraste entre el uso de descripciones en inglés o en español. Esto es debido a que el modeo fue entrenado con descripciones en español, por lo que traducirlas al inglés puede ser una gran mejoría.

## Mejoras posibles sin nuevos modelos

Sin incorporar todavía LLM, TOLoc, VLM, Street View o diálogo, las mejoras más
defendibles son:

1. **Descripciones cartográficas controladas.** Priorizar estructura urbana y
   eliminar de una segunda variante los detalles sin representación OSM.
2. **Orientación explícita opcional.** Añadir rumbo cardinal solo cuando el
   usuario realmente lo conoce; nunca inferirlo de «derecha» o «izquierda».
3. **Variantes de consulta predeterminadas.** Ejecutar texto original, versión
   cartográfica y traducción inglesa como rankings separados. No sumar scores de
   escalas no calibradas.
4. **Consenso espacial y de ranking.** Identificar candidatos o zonas que se
   repiten entre variantes y entre galerías 25 m/50 m mediante IDs, distancias,
   intersección Top-K o reciprocal-rank fusion documentada.
5. **Margen y dispersión.** Mostrar diferencia Top-1/Top-2 y concentración
   geográfica del Top-K para describir ambigüedad, no confianza.
6. **Revisión determinista de OSM.** Contrastar etiquetas y geometrías ya
   disponibles alrededor del Top-K, sin usar ground truth. La ausencia de una
   etiqueta no prueba que un objeto no exista.
7. **Galería de 25 m para salida final.** Usar 50 m como evidencia de zona y 25 m
   para seleccionar una celda más fina cuando ambos rankings muestran acuerdo
   espacial.

Estas técnicas pueden mejorar estabilidad o selección, pero la salida seguirá
siendo el centro de una celda. Con la galería actual no debe afirmarse precisión
subcelda ni una coordenada exacta nueva. Un promedio ponderado de coordenadas o
una fusión de scores sería una metodología experimental propia y necesitaría
ground truth para demostrar que reduce el error en vez de desplazarlo.
