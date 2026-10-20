# F5.5b: revisión visual Panoramax y vía de evaluación

## Resultado

F5.5b registra la revisión visual comunicada por el responsable del TFG sin
convertir aptitud visual en aprobación geográfica. El contrato v2 añade
`visual_review` y conserva intacto `review.status`.

Resultado de la primera cola:

| Aptitud visual | Items | Estado GT |
|---|---:|---|
| `suitable` | 1 | `pending` |
| `limited` | 2 | `pending` |
| `unsuitable` | 2 | `pending` |
| Aprobados como GT | 0 | No disponible |

El artefacto está fuera de Git:

```text
results/generated/f5/f55b/
  f55b-visual-review-09ef7aeb8b66982384ed74495faece396e7fd1f8de670162ad36599da398b60d/
```

Contiene `primary-visual-review.json`, `primary-review.html`, una referencia
hashada al snapshot F5.5 y la segunda cola.

## Revisión primaria registrada

### Apta visualmente

`fdf10c50-11ee-4f43-af3f-5704f8fed2a1` muestra espacio peatonal,
árboles sin hojas, árbol navideño, personas, edificios, comercios y torre con
reloj. Conserva esta descripción propuesta:

> Estoy junto a una zona peatonal pavimentada, con árboles sin hojas y comercios
> a un lado. Delante se abre una plaza concurrida donde hay un gran árbol
> navideño. Al fondo se observa un edificio con una torre y un reloj.

La descripción sigue `pending` de revisión final. La posición tiene 5 m de
precisión declarada, pero las asignaciones 25 m y 50 m son
`accuracy_insufficient`; no hay Recall exacto.

### Contexto limitado

- `d766c3b3-875a-4442-8f0b-56b0f26d49bf`: fachada, balcones,
  revestimiento decorativo, accesos y edificios contiguos; sin precisión.
- `a36f42ac-816c-4de1-8f70-3f88bf1fb80b`: fachada comercial,
  puertas, ventanas, balcones y calle; sin precisión.

Pueden servir como casos secundarios visuales, no como benchmark principal ni GT
actual.

### Inadecuadas para el benchmark principal

- `091933c1-c0a1-4132-b0f6-54082712fdff`: primer plano de
  monumento/pedestal y contexto urbano escaso.
- `08b1f259-52a8-4c86-814e-46f99bc85dc7`: primer plano de placa y
  fotografías; contexto exterior escaso.

La segunda tiene celda 50 m `assigned`. F5.5b registra expresamente que esa buena
asignación no compensa una evidencia visual inadecuada.

## Segunda cola

Los cinco items restantes se materializaron sin cambiar inventario ni primera
cola. Abrir:

```text
results/generated/f5/f55b/f55b-visual-review-09ef7aeb8b66982384ed74495faece396e7fd1f8de670162ad36599da398b60d/complementary-review.html
```

| Item | Precisión | 25 m | 50 m |
|---|---:|---|---|
| `37c78a1f-049e-4a05-9f5a-16f671f226d0` | 12 m | insufficient | insufficient |
| `3e5731ae-a054-4866-bef2-6d2b59dcaf4f` | 5 m | insufficient | outside coverage |
| `608dca83-929b-49d6-be52-537ee91a2aaa` | 5 m | insufficient | insufficient |
| `9602c41b-fab5-4db0-bd47-d0de6d339c15` | ausente | unavailable | unavailable |
| `9846a3e6-e42d-4478-82fc-1b1404dfd2da` | ausente | unavailable | unavailable |

Los cinco thumbnails están congelados y siguen `pending`. Esta cola puede mejorar
contexto visual, pero no aporta por sí misma Recall exacto.

El campo `recorded_at_utc` identifica cuándo se incorporó al repositorio la
revisión comunicada; no pretende reconstruir la hora original de inspección. Un
artefacto preliminar `f55b-visual-review-66c6...` usaba el nombre ambiguo
`reviewed_at_utc`; se conserva sin sobrescribir, pero queda sustituido por el ID
válido anterior.

## Alternativas sin desplazamiento

| Alternativa | Cobertura D004 | Posición | Precisión | Contexto | Licencia/coste | Métricas posibles | Riesgo |
|---|---|---|---|---|---|---|---|
| Wikimedia Commons | 4.226 files; 4.121 `type=camera` | Cámara si `Location`; excluir object/landmark | Generalmente no garantizada; requiere validación individual | Variable, desde fachadas hasta plazas/secuencias | Licencia por file; API pública; coste medio de filtrado/revisión | Haversine/GeoRecall si se valida coordenada; Recall solo con precisión suficiente | Sesgo turístico, duplicados, geocodificación manual y licencias heterogéneas |
| Panoramax restante | 5 items en segunda cola | Cámara | 3 declaradas, todas insuficientes o fuera; 2 ausentes | Pendiente de revisión | CC BY-SA 4.0; ya adquirido | Haversine exploratorio tras validar; no Recall 25 m | Dos colecciones y cobertura espacial limitada |
| Mapillary | Cobertura probable pero no inventariada | Cámara original/computada | No garantizada por campo API | Calle sistemática potencialmente rica | Token y términos pendientes; coste medio | Haversine/Recall según precisión que pueda justificarse | Dependencia de credenciales, secuencias densas y metadata procesada |
| KartaView | Sin cobertura observada | Cámara | Variable | Nula en D004 ahora | API pública, términos antiguos | Ninguna ahora | Servicio/API inestable y cobertura cero |
| Recogida propia | Por realizar | Observador medido | Controlable con múltiples lecturas | Diseñada para descripción rica | Desplazamiento y revisión; derechos controlables | Recall 25/50 m, GeoRecall, Haversine | Coste humano y riesgo de bordes de celda |
| Ampliar catálogo | No implementado | Dependería de nueva F1-F4 | No resuelve precisión fuente | Más diversidad potencial | Coste alto: OSM, imágenes y embeddings nuevos | Mismas métricas tras rehacer galerías | Cambio de alcance y comparabilidad; propuesta futura בלבד |
| Benchmark sintético OSM | Cobertura completa por construcción | Centro/regla OSM, no observador real | Exacta respecto a dato sintético | Sin apariencia fotográfica real | Coste bajo; ODbL | Recall técnico respecto a celda sintética | Contaminación: texto y respuesta derivan de OSM; no mide usuarios reales |

El benchmark sintético solo sería un banco técnico separado, nunca GT visual real
ni evidencia de transferencia a descripciones humanas.

## Vía mínima de evaluación

### Nivel 1: GT geométrico validado

Mínimo científicamente útil: cinco ubicaciones propias `human_in_situ`, separadas
espacialmente, con descripción española, fotografías, múltiples lecturas GNSS y
precisión suficiente. Para Recall exacto por galería, cada punto debe ser
`assigned` en esa galería. Con cinco casos, cualquier conclusión sería
exploratoria.

### Nivel 2: coordenadas fotográficas con incertidumbre

Panoramax/Commons pueden formar un subconjunto documental si la posición de
cámara, licencia, precisión y descripción se revisan. Se puede calcular error
Haversine y GeoRecall con incertidumbre documentada. Recall exacto se omite para
`accuracy_insufficient`, `accuracy_unavailable`, bordes o huecos.

Actualmente la primera cola aporta una sola imagen visualmente apta, pero no tiene
asignación exacta. Por tanto no desbloquea Recall.

### Nivel 3: sintético OSM

Puede probar contratos y sensibilidad lingüística con coordenadas conocidas,
pero debe etiquetarse `synthetic`, mantenerse fuera del test humano y no usarse
para seleccionar la mejor variante definitiva.

### Nivel 4: sin GT

Acuerdo Top-1, Jaccard y desplazamiento entre variantes continúan siendo solo
estabilidad. No sustituyen precisión.

## Acciones del responsable

1. Abrir `complementary-review.html` y clasificar los cinco items restantes.
2. Confirmar o corregir la descripción propuesta de la imagen apta.
3. Revisar licencia y metadata por item antes de una eventual aprobación.
4. Mantener todas las fotografías Panoramax `pending` salvo validación explícita.
5. Recoger cinco observaciones propias con el formulario F5.5.
6. Evitar puntos cercanos a bordes usando solo planificación espacial previa; la
   coordenada registrada debe seguir siendo la medición real, nunca el centro de
   la celda.
7. Importar únicamente registros `approved` y validar F4.3/F5.4.

## Fase posterior

El siguiente BUILD recomendado es **F5.5c: recogida/revisión de cinco
observaciones `human_in_situ`**. Cuando existan GT aprobados, continuar con F5.2
para variantes y después con el runner F5.4. No ejecutar Qwen ni CrossText2Loc
antes de congelar esas observaciones.
