# Transferencia y revisión de anotaciones visuales con Codex local

## Paquete preparado

Directorio:

```text
results/generated/mapillary/visual-reranking-expanded-v1/codex-portable/
```

Archivo recomendado para transferencia privada:

```text
results/generated/mapillary/visual-reranking-expanded-v1/codex-portable.tar.gz
```

SHA-256:

```text
f94748acffa3ecaafd57c8cb8150bf9afa4a1d297b9c48d6fbfaeffdf260a333
```

El paquete ocupa aproximadamente 1,3 MB comprimido y contiene 12 imágenes, 24
claims, 72 pares, manifest sanitizado, atribuciones, schemas, prompt y scripts de
validación/revisión. No contiene referencias geográficas de evaluación, scores o
rangos CrossText2Loc ni outputs Qwen3-VL.

## Licencia y canal recomendado

Las fotografías Mapillary se declaran CC BY-SA 4.0 y conservan autor, enlace,
licencia y modificaciones en `ATTRIBUTION.md`. Sin embargo, la autorización
operativa registrada en el proyecto cubre uso académico local y no aprueba de
forma inequívoca publicar un dataset de imágenes en GitHub.

Por ello se recomienda una transferencia privada: `scp`, SFTP, almacenamiento
institucional o carpeta privada. No se recomienda GitHub público hasta confirmar
expresamente publicación, privacidad y atribución por imagen.

Git LFS no está instalado/configurado y no es necesario por tamaño. Además,
`results/generated/` y los archivos comprimidos están ignorados por Git.

## Transferencia privada

Desde el ordenador local:

```bash
scp dataai@dataai-pgx:/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/results/generated/mapillary/visual-reranking-expanded-v1/codex-portable.tar.gz .
scp dataai@dataai-pgx:/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/results/generated/mapillary/visual-reranking-expanded-v1/codex-portable.tar.gz.sha256 .
sha256sum -c codex-portable.tar.gz.sha256
tar -xzf codex-portable.tar.gz
cd codex-portable
```

Si Windows no dispone de `sha256sum`, usar:

```powershell
Get-FileHash .\codex-portable.tar.gz -Algorithm SHA256
```

## Ejecución de Codex local

Abrir la carpeta `codex-portable` como workspace y proporcionar a Codex el
contenido de `CODEX_PROMPT.md`. Codex debe producir:

```text
ai-proposals.json
```

Validación:

```bash
python scripts/validate_codex_ai_proposals.py \
  --package-root . \
  --proposals ai-proposals.json
```

Las propuestas permanecen `AI-proposed` y `human_validated=false`.

## Revisión humana

Generar el formulario:

```bash
python scripts/render_codex_proposal_review.py \
  --package-root . \
  --proposals ai-proposals.json \
  --output human-review.html
```

Servir localmente:

```bash
python -m http.server 8765
```

Abrir:

```text
http://127.0.0.1:8765/human-review.html
```

Cada propuesta debe confirmarse o corregirse y marcarse como revisada. La salida
será `human-reviewed-annotations.json`, ya bajo el contrato humano del proyecto.

## Opción GitHub condicionada

Solo si se autoriza expresamente publicar las imágenes:

1. crear un directorio versionable fuera de `results/generated/`;
2. conservar `ATTRIBUTION.md` y CC BY-SA;
3. no incluir otros datos/resultados;
4. verificar `git status` y el tamaño staged;
5. usar Git normal; LFS no aporta valor para 1,3 MB.

Comandos orientativos desde el repositorio local, después de aprobar el canal:

```bash
mkdir -p annotation-transfer/codex-expanded-v1
cp -R /ruta/codex-portable/. annotation-transfer/codex-expanded-v1/
git status --short
git add annotation-transfer/codex-expanded-v1
git diff --cached --stat
git diff --cached --check
git commit -m "data: add private visual annotation package"
git push
```

No debe ejecutarse esta opción sin revisar la política de publicación.

## Retorno de anotaciones

La opción preferida es transferir únicamente:

```text
ai-proposals.json
human-reviewed-annotations.json
```

mediante canal privado. Si se usa GitHub para esos JSON sin imágenes:

```bash
git status --short
mkdir -p annotation-results/visual-reranking-expanded-v1
cp ai-proposals.json human-reviewed-annotations.json annotation-results/visual-reranking-expanded-v1/
git add annotation-results/visual-reranking-expanded-v1
git diff --cached --check
git commit -m "data: add reviewed visual annotations"
git push
```

En PGX, antes de traer cambios:

```bash
git status --short
git fetch origin
git diff --stat HEAD..origin/<rama>
```

El árbol PGX puede estar sucio; no hacer `pull` si los cambios remotos se solapan
con trabajo local. En ese caso, transferir solo los dos JSON o coordinar una rama
separada. Nunca usar `git reset --hard` ni sobrescribir cambios locales.

## Validaciones al regresar

1. schema y procedencia `AI-proposed`;
2. exactamente 72 IDs y cobertura de fixture;
3. unicidad de pares;
4. revisión humana completa;
5. hashes del paquete y fotografías;
6. ausencia de cambios en anotaciones históricas;
7. ejecución 2B/8B solo después de aceptar la referencia humana.

## Evaluación geográfica posterior

La fase posterior será offline y reversible. Comparará Recall@1/5/10 cuando la
relevancia exacta sea válida, GeoRecall@1/5/10 a 50 m, distancia Top-1, reranking
sin sustitución y, en una fase distinta, descarte reversible y candidatos de una
reserva ampliada. Informará candidatos correctos eliminados, relevantes
incorporados y consultas mejoradas/empeoradas/iguales. GT solo se abrirá en el
evaluador posterior. Nada de esto se activa en el MVP en esta fase.
