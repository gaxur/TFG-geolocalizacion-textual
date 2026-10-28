#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.mapillary_cache import cache_from_env


if __name__ == "__main__":
    print(json.dumps(cache_from_env(ROOT).cleanup(), sort_keys=True))
