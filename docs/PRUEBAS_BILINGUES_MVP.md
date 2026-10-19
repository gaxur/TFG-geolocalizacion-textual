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

## Casos detallados para revisión visual en español

### 1. Puerta del Sol

**Referencia aproximada:** `40.41694, -3.70361`

> Estoy en una plaza urbana grande y peatonal, rodeada de edificios. Desde la
> zona abierta salen varias calles estrechas en direcciones diferentes. El
> espacio tiene una forma irregular y alargada de este a oeste. En el lado este
> conecta con una calle principal más ancha, mientras que hacia el oeste y el
> sur continúa una red densa de calles estrechas y manzanas pequeñas. En uno de
> los edificios que rodean la plaza veo una torre elevada con un reloj grande y
> visible en su parte superior. No hay un parque grande ni una lámina de agua
> junto a la plaza.

**Pistas cartográficas principales:** espacio peatonal grande, muchos accesos,
forma irregular, vía más ancha al este y tejido denso alrededor.

**Pista visual secundaria:** torre con un reloj grande sobre uno de los
edificios. CrossText2Loc procesa esta frase, pero la imagen OSM no permite
verificar visualmente el reloj.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41694&mlon=-3.70361#map=18/40.41694/-3.70361)

### 2. Plaza Mayor

**Referencia aproximada:** `40.41536, -3.70740`

> Estoy en una gran plaza rectangular y cerrada, rodeada completamente por
> edificios continuos en sus cuatro lados. El interior es un espacio abierto
> amplio y regular, sin una avenida que lo atraviese. Las entradas son pasos y
> calles relativamente estrechas situadas cerca de las esquinas y de los lados.
> Al salir de la plaza aparecen manzanas compactas, calles irregulares y otro
> pequeño espacio abierto hacia el oeste.

**Pistas cartográficas principales:** rectángulo cerrado, perímetro edificado,
accesos estrechos y ausencia de una vía principal atravesando el interior.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41536&mlon=-3.70740#map=18/40.41536/-3.70740)

### 3. Plaza de Santa Ana

**Referencia aproximada:** `40.41467, -3.70103`

> Estoy en una plaza rectangular y alargada dentro de una zona urbana densa. Hay
> edificios en todos sus lados, pero el espacio no está completamente cerrado.
> Su eje más largo se extiende aproximadamente de este a oeste. Varias calles
> estrechas conectan con las esquinas y con los extremos. Al norte y al sur hay
> manzanas compactas; no veo una avenida de varios carriles ni una zona verde
> grande pegada a la plaza.

**Pistas cartográficas principales:** plaza alargada, eje este-oeste, accesos en
extremos y tejido compacto sin parque adyacente.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41467&mlon=-3.70103#map=18/40.41467/-3.70103)

### 4. Plaza de Jacinto Benavente

**Referencia aproximada:** `40.41439, -3.70368`

> Estoy en un espacio urbano abierto de forma irregular donde confluyen varias
> calles desde distintos ángulos. No es una plaza rectangular cerrada: uno de sus
> lados se abre hacia una calle más ancha y el resto conecta con calles estrechas.
> Las manzanas próximas son pequeñas, densas e irregulares. Hay otros espacios
> abiertos importantes a poca distancia hacia el norte y el oeste, pero no están
> unidos directamente a este espacio.

**Pistas cartográficas principales:** nodo irregular, calles convergentes con
ángulos distintos, una conexión más ancha y varias plazas cercanas separadas.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41439&mlon=-3.70368#map=18/40.41439/-3.70368)

### 5. Plaza del Carmen

**Referencia aproximada:** `40.41882, -3.70330`

> Estoy en una plaza alargada entre edificios, cerca de una calle comercial
> importante. El espacio abierto tiene un eje aproximadamente norte-sur y está
> rodeado por manzanas densas. Varias calles cortas y estrechas lo conectan con
> una vía mucho más ancha situada al norte. Hacia el sur continúa una red de
> calles peatonales y pequeños cruces; no hay un parque grande junto a la plaza.

**Pistas cartográficas principales:** plaza alargada norte-sur, gran vía próxima
al norte y conexión por calles cortas dentro de una trama densa.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41882&mlon=-3.70330#map=18/40.41882/-3.70330)

### 6. Mercado de San Miguel

**Referencia aproximada:** `40.41548, -3.70897`

> Estoy junto a una pequeña plaza y un edificio rectangular aislado dentro de
> una zona de calles estrechas y manzanas irregulares. El edificio ocupa gran
> parte del pequeño espacio abierto y puede rodearse por varios lados. A muy poca
> distancia hacia el este hay una plaza rectangular mucho más grande y cerrada.
> Hacia el oeste aparece otra plaza menor, mientras que al norte y al sur
> continúan calles estrechas del centro histórico.

**Pistas cartográficas principales:** edificio exento y rodeable, dos plazas
próximas de tamaños distintos y red de calles históricas estrechas.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41548&mlon=-3.70897#map=18/40.41548/-3.70897)

### 7. Plaza, estación de Cercanías y torre con reloj

**Referencia exploratoria aproximada:** entorno de Puerta del Sol,
`40.41694, -3.70361`.

**Descripción original en inglés:**

> I am in a plaza and to my right I have a commuter train station, and just
> behind me there is a tower with a clock.

**Traducción al español:**

> Estoy en una plaza y a mi derecha hay una estación de tren de Cercanías. Justo
> detrás de mí hay una torre con un reloj.

**Versión con algo más de contexto cartográfico:**

> Estoy en una plaza urbana grande, abierta y mayoritariamente peatonal, rodeada
> de edificios y conectada con numerosas calles estrechas. A mi derecha hay una
> estación de tren de Cercanías integrada en la plaza. Justo detrás de mí veo una
> torre elevada con un reloj grande en su parte superior. Cerca de uno de los
> lados de la plaza pasa una calle principal más ancha, mientras que en las otras
> direcciones continúa una trama densa de calles comerciales.

**Pistas potencialmente cartográficas:** plaza grande, numerosos accesos, zona
peatonal, estación ferroviaria y vía principal próxima.

**Pistas visuales o egocéntricas:** «a mi derecha», «detrás de mí» y torre con
reloj. El modelo procesa estas expresiones, pero no conoce la orientación del
usuario y la imagen OSM no permite verificar visualmente el reloj.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41694&mlon=-3.70361#map=18/40.41694/-3.70361)

### 8. Plaza, Pans & Company y cartel de Schweppes

**Referencia exploratoria:** entorno de Callao y edificio Capitol. La coordenada
del cartel, `40.4202891, -3.7063716`, está fuera del límite norte de la bbox.

**Descripción original en inglés:**

> I'm in a square and to my right there's a Pans & Company and to my left a big
> building with a Schweppes brand sign.

**Traducción al español:**

> Estoy en una plaza y a mi derecha hay un Pans & Company. A mi izquierda hay un
> edificio grande con un cartel de la marca Schweppes.

**Versión con algo más de contexto cartográfico:**

> Estoy en una plaza urbana abierta, rodeada de edificios altos y manzanas muy
> densas. La plaza está junto a una avenida principal ancha y ligeramente curva,
> y hacia el sur salen varias calles comerciales y peatonales más estrechas. A mi
> derecha hay un establecimiento Pans & Company. A mi izquierda veo un edificio
> grande y alto, situado en una esquina destacada, con una torre vertical y un
> cartel luminoso de la marca Schweppes en la parte superior. No hay parques
> grandes ni agua cerca de la plaza.

**Pistas potencialmente cartográficas:** plaza junto a una avenida ancha, calles
estrechas hacia el sur, manzanas densas y edificio en una esquina destacada.

**Pistas visuales o egocéntricas:** Pans & Company, cartel de Schweppes,
«derecha» e «izquierda». Las marcas y el cartel no son visibles en la galería
OSM, y derecha/izquierda no pueden convertirse a direcciones cardinales sin
conocer la orientación del usuario.

Este caso no puede tener una celda centrada en la ubicación exacta del cartel con
las galerías actuales. Se conserva como prueba exploratoria de sensibilidad al
texto y de cobertura del borde norte, no como caso evaluable de precisión.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.4202891&mlon=-3.7063716#map=18/40.4202891/-3.7063716)

### Resultado exploratorio del caso Schweppes

La descripción optimizada se ejecutó con Top-10. El candidato del borde norte
más cercano a la referencia no apareció en el Top-10 de 25 m ni en el de 50 m.
Esto debe tratarse como una prueba negativa de cobertura y transferencia, no como
un problema de la interfaz. Para convertir este caso en una prueba recuperable
sería necesario ampliar y regenerar el catálogo al norte, lo que implica una
nueva galería y queda fuera del MVP actual.

## Variantes detalladas para revisión visual en inglés

El checkpoint utilizado procede de la configuración NewYork-mixed. Comparar una
consulta equivalente en español e inglés permite explorar la estabilidad
lingüística, pero no mide por sí solo la precisión geográfica.

### Puerta del Sol

> I am standing in a large pedestrian square surrounded by buildings. Many
> narrow streets leave the open area in different directions. The square has an
> irregular shape elongated from east to west. Its eastern side connects to a
> wider main street, while dense small blocks and narrow streets continue to the
> west and south. On one of the buildings surrounding the square, I can see a
> raised tower with a large visible clock near its top. There is no large park or
> body of water beside the square.

### Plaza Mayor

> I am inside a large rectangular enclosed square completely surrounded by
> continuous buildings on all four sides. No main avenue crosses the open
> interior. Relatively narrow passages and streets provide access near the
> corners and sides. Dense irregular blocks surround the square, with another
> smaller open space to the west.

### Plaza de Santa Ana

> I am in a long rectangular square within a dense urban area. Buildings surround
> the open space, but it is not fully enclosed. Its long axis runs approximately
> east to west. Narrow streets connect to the corners and both ends. Compact
> blocks lie to the north and south, with no multilane avenue or large park
> directly beside the square.

### Plaza de Jacinto Benavente

> I am in an irregular open urban space where several streets converge. It is
> not a closed rectangular square. Streets approach it from different angles;
> one side opens onto a wider street while the other connections are narrow.
> Small dense irregular blocks surround it, and other major open spaces lie a
> short distance to the north and west without directly joining this space.

### Plaza del Carmen

> I am in an elongated open square between dense city blocks. Its main axis runs
> approximately north to south. Several short narrow streets connect it to a
> much wider major road to the north. A network of pedestrian streets and small
> intersections continues southward, and there is no large park beside it.

### Mercado de San Miguel

> I am beside a small square containing a detached rectangular building that can
> be passed on several sides. A much larger enclosed rectangular square lies a
> very short distance to the east, while another smaller square lies to the
> west. Narrow historic streets continue to the north and south.

### Square, commuter station and clock tower

> I am in a large, open, mostly pedestrian urban square surrounded by buildings
> and connected to many narrow streets. To my right there is a commuter train
> station integrated into the square. Just behind me I can see a raised tower
> with a large clock near its top. A wider main street runs close to one side of
> the square, while a dense network of narrow commercial streets continues in
> the other directions.

**Potentially map-visible clues:** a large square, many access streets, a
pedestrian area, a railway station and a nearby main street.

**Visual or observer-relative clues:** “to my right”, “behind me” and a clock
tower. The model processes these expressions, but it does not know the user's
orientation and the OSM image cannot visually verify the clock.

### Square, Pans & Company and Schweppes sign

> I am in an open urban square surrounded by tall buildings and very dense city
> blocks. The square is beside a wide, slightly curved main avenue, and several
> narrower commercial and pedestrian streets extend south. To my right there is
> a Pans & Company restaurant. To my left I can see a large, tall building on a
> prominent corner, with a vertical tower and an illuminated Schweppes sign near
> the top. There is no large park or body of water near the square.

**Potentially map-visible clues:** a square beside a wide avenue, narrow streets
to the south, dense blocks and a building on a prominent corner.

**Visual or observer-relative clues:** Pans & Company, the Schweppes sign, “to
my right” and “to my left”. The brands and sign are not visible in the OSM
gallery, and left/right cannot be converted to cardinal directions without the
user's orientation.

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
