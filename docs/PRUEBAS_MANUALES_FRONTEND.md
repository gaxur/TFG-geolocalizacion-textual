# Pruebas manuales del frontend con ubicaciones conocidas

## Objetivo y alcance

Este documento reúne consultas exploratorias para comprobar manualmente el
recorrido frontend → API → CrossText2Loc → Top-K. Cada caso incluye una ubicación
de referencia que permite revisar visualmente si los candidatos recuperados
aparecen cerca del lugar descrito.

Estas pruebas no forman un dataset de evaluación ni aportan métricas del TFG. Las
coordenadas son referencias manuales aproximadas, no *ground truth* validado. Las
descripciones tampoco proceden de observaciones humanas recogidas mediante el
protocolo previsto para la evaluación formal.

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

## Casos en español

### 1. Puerta del Sol

**Referencia aproximada:** `40.41694, -3.70361`

> Estoy en una plaza urbana grande y peatonal, rodeada de edificios. Desde la
> plaza salen numerosas calles en distintas direcciones y hay una vía principal
> junto a uno de sus lados.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41694&mlon=-3.70361#map=18/40.41694/-3.70361)

### 2. Plaza Mayor

**Referencia aproximada:** `40.41536, -3.70740`

> Estoy en una gran plaza rectangular y cerrada, rodeada completamente por
> edificios. Se accede a ella mediante pasos relativamente estrechos y las calles
> de alrededor forman manzanas densas e irregulares.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41536&mlon=-3.70740#map=18/40.41536/-3.70740)

### 3. Plaza de Santa Ana

**Referencia aproximada:** `40.41467, -3.70103`

> Estoy en una plaza rectangular y alargada dentro de una zona urbana densa. Hay
> edificios en todos sus lados y varias calles estrechas conectadas con sus
> esquinas.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41467&mlon=-3.70103#map=18/40.41467/-3.70103)

### 4. Plaza de Jacinto Benavente

**Referencia aproximada:** `40.41439, -3.70368`

> Estoy en un espacio urbano abierto de forma irregular donde confluyen varias
> calles. Alrededor hay manzanas compactas y calles estrechas del centro
> histórico.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41439&mlon=-3.70368#map=18/40.41439/-3.70368)

### 5. Plaza del Carmen

**Referencia aproximada:** `40.41882, -3.70330`

> Estoy en una plaza alargada entre edificios, cerca de una calle comercial
> importante. Varias calles estrechas conectan este espacio con una avenida más
> amplia situada al norte.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41882&mlon=-3.70330#map=18/40.41882/-3.70330)

### 6. Mercado de San Miguel

**Referencia aproximada:** `40.41548, -3.70897`

> Estoy junto a una pequeña plaza y un edificio rectangular aislado dentro de
> una zona de calles estrechas. Cerca hay una plaza urbana mucho más grande y
> varias manzanas irregulares.

[Abrir referencia en OpenStreetMap](https://www.openstreetmap.org/?mlat=40.41548&mlon=-3.70897#map=18/40.41548/-3.70897)

## Variantes en inglés

El checkpoint utilizado procede de la configuración NewYork-mixed. Comparar una
consulta equivalente en español e inglés permite explorar la estabilidad
lingüística, pero no mide por sí solo la precisión geográfica.

### Puerta del Sol

> I am standing in a large pedestrian square surrounded by buildings. Many
> streets leave the square in different directions, and a major road runs along
> one side.

### Plaza Mayor

> I am inside a large rectangular enclosed square completely surrounded by
> buildings. Narrow passages connect the square with dense and irregular streets.

### Plaza de Santa Ana

> I am in a long rectangular square within a dense urban area. Buildings surround
> the open space and narrow streets connect to its corners.

### Plaza de Jacinto Benavente

> I am in an irregular open urban space where several streets converge. It is
> surrounded by compact city blocks and narrow streets.

## Procedimiento recomendado

1. Desplegar el MVP con `scripts/run_mvp3_stack.sh -d` y abrir
   `http://127.0.0.1:8080/` en la PGX o `http://IP_LOCAL:8080/` desde la LAN.
2. Seleccionar la galería de 25 m.
3. Seleccionar `Top-10` para la primera inspección.
4. Copiar únicamente la descripción del caso, sin incluir su nombre ni sus
   coordenadas.
5. Ejecutar la búsqueda y localizar la referencia manual en el mapa.
6. Anotar si algún candidato aparece cerca de la referencia y cuál es su rango.
7. Repetir la consulta con la galería de 50 m.
8. Repetir en inglés cuando exista una variante equivalente.
9. No interpretar la similitud coseno como probabilidad de acierto.

Al terminar:

```bash
docker compose -f compose.mvp.yaml down
```

Los candidatos representan centros de celdas. Por ello, no se espera una
coincidencia decimal exacta entre el candidato y la referencia. Para cualquier
comparación cuantitativa debe calcularse la distancia geodésica y fijarse de
antemano un criterio de acierto coherente con la resolución; una inspección
visual aproximada no sustituye ese protocolo.

## Registro sugerido

| Caso | Idioma | Galería | Top-K | Rango del candidato más cercano | Distancia | Observaciones |
|---|---|---|---:|---:|---:|---|
| Puerta del Sol | es | 25 m | 10 |  |  |  |
| Puerta del Sol | en | 25 m | 10 |  |  |  |
| Puerta del Sol | es | 50 m | 10 |  |  |  |

No deben incorporarse estos registros a resultados experimentales sin validar
antes las referencias, el origen de las descripciones, el criterio de asignación
al catálogo y la separación entre desarrollo y prueba final.
