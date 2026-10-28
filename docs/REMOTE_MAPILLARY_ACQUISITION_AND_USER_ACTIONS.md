# Adquisición Mapillary remota y acciones pendientes

## Estado

El inventario metadata-only D004 con buffer fotográfico ya existía localmente y
se reutilizó sin llamadas de red. La selección v2 y el plan de 79 IDs se generaron
offline. No se descargaron fotografías nuevas.

La revisión oficial documentada confirma CC BY-SA 4.0 para las imágenes y acceso
mediante API, pero la licencia de contenido no sustituye los términos de la
aplicación, privacidad, atribución ni derechos de imagen. La autorización de 24
miniaturas del piloto del 23 de octubre no cubre automáticamente H26-H61.

## Alcance que debe autorizarse

La persona titular de la aplicación debe confirmar por escrito:

1. Los 79 `image_id` exactos del plan v2 y sus roles: 36 referencia, 43 verificación.
2. Miniaturas de hasta 1.024 px y límite de 8 MB por imagen.
3. Conservación local durante un plazo que debe indicarse.
4. Revisión y anotación humana privada.
5. Transferencia privada a Windows y, para test, a un segundo revisor.
6. Inferencia local con Qwen3-VL-2B y 8B de pesos fijos.
7. Ausencia de entrenamiento, fine-tuning y publicación de dataset de imágenes.
8. Atribución por imagen, revisión de privacidad y cualquier cuota o restricción
   adicional de la aplicación.

Texto de autorización sugerido:

> He revisado las condiciones aplicables a la aplicación Mapillary y autorizo el
> plan `remote-mapillary-acquisition-sha256-d5ba6a6e985ca31859aba2d434e15811fb05de415655e9be78ded9a508196c6e`
> para los 79 IDs exactos, con los roles, resolución, almacenamiento privado,
> anotación e inferencia fija 2B/8B descritos en este documento. Indico además el
> plazo de retención y cualquier condición adicional aplicable.

## Recursos

| Concepto | Valor |
|---|---:|
| Referencias | 36 |
| Verificaciones | 43 |
| Total único | 79 |
| Media observada en piloto | 110.762,42 B/imagen |
| Estimación | 8.750.231 B |
| Máximo duro | 632.000.000 B |

La estimación usa 24 miniaturas y puede variar. El máximo es un límite de
seguridad, no una predicción.

## Credencial

La futura adquisición requiere `MAPILLARY_ACCESS_TOKEN`. Debe permanecer en un
`.env` ignorado o en el entorno del proceso, nunca en comandos compartidos,
manifests, logs o Git. Antes de ejecutar se comprobará:

```bash
git check-ignore -v .env
```

No se proporciona aún un comando de descarga: falta una autorización expresa y
el descargador remoto específico debe validar el plan autorizado antes de abrir
red. El comando ya disponible solo regenera el plan offline:

```bash
python scripts/plan_remote_mapillary_acquisition.py \
  --selection results/generated/mapillary/remote-h26-h61-v2/selection-plan.json \
  --pilot-manifest results/generated/mapillary/visual-pilot-v1/photo-manifest.json \
  --output results/generated/mapillary/remote-h26-h61-v2/acquisition-plan.json
```

## Acciones exactas del responsable

1. Revisar y aceptar o rechazar el alcance de 79 IDs mediante el texto anterior.
2. Indicar el plazo de retención de las fotografías y si se permite transferencia
   privada a un segundo revisor.
3. Confirmar que `MAPILLARY_ACCESS_TOKEN` corresponde a la aplicación revisada,
   sin comunicar su valor.
4. Tras una adquisición autorizada, abrir
   `results/generated/mapillary/remote-h26-h61-v2/annotation-human/annotate.html`
   para H26-H37.
5. En Windows, servir el paquete Codex con
   `py -m http.server 8765 --bind 127.0.0.1` y seguir `CODEX_PROMPT.md`.
6. Revisar manualmente toda propuesta Codex; no aceptar etiquetas automáticas.
7. Conseguir, si es viable, un segundo revisor para H38-H61 y usar el paquete
   `annotation-blind-test`, sin propuestas IA ni predicciones 2B/8B.
8. Autorizar por separado la apertura única del test cuando development haya
   congelado K, modelos, prompts, umbrales y política.

No debe ejecutarse todavía Qwen3-VL sobre H38-H61, activar promoción en el MVP,
implementar diálogo ni ampliar D004.
