"""Contratos y validadores independientes de los modelos del TFG."""

from .config import load_region_config
from .validation import SchemaValidationError, validate_document

__all__ = ["SchemaValidationError", "load_region_config", "validate_document"]
