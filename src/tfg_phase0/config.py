"""Carga de configuración de Fase 0 sin dependencias externas.

Los ficheros `.yaml` de esta fase utilizan el subconjunto JSON de YAML 1.2.
Esto mantiene el archivo legible como YAML sin fijar todavía una dependencia
de parsing para el proyecto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validation import SchemaValidationError, validate_document


def load_region_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaValidationError(f"No se pudo leer la configuración: {config_path}") from exc

    validate_document(document, "region_config")
    bbox = document["region"]["bbox"]
    if bbox["south"] >= bbox["north"]:
        raise SchemaValidationError("La bbox debe cumplir south < north")
    if bbox["west"] >= bbox["east"]:
        raise SchemaValidationError("La bbox debe cumplir west < east")
    return document
