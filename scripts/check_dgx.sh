#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux ]]; then
  printf 'ERROR: este diagnóstico está preparado para Linux/DGX.\n' >&2
  exit 1
fi

status=0
printf 'Host: '
if ! hostname; then
  printf 'ERROR: no se pudo obtener el hostname.\n' >&2
  status=1
fi

printf '\nGPU, driver y memoria (nvidia-smi):\n'
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi --query-gpu=index,name,driver_version,memory.total,memory.free --format=csv; then
    printf 'ERROR: nvidia-smi no pudo consultar las GPU.\n' >&2
    status=1
  fi
else
  printf 'ERROR: nvidia-smi no está disponible.\n' >&2
  status=1
fi

printf '\nEspacio de disco en el directorio actual:\n'
if ! df -h .; then
  printf 'ERROR: df -h . falló.\n' >&2
  status=1
fi

printf '\nPython:\n'
if command -v python3 >/dev/null 2>&1; then
  python3 --version || status=1
elif command -v python >/dev/null 2>&1; then
  python --version || status=1
else
  printf 'ERROR: no hay intérprete Python en PATH.\n' >&2
  status=1
fi

printf '\nConda:\n'
if command -v conda >/dev/null 2>&1; then
  conda --version || status=1
else
  printf 'ERROR: conda no está disponible en PATH.\n' >&2
  status=1
fi

printf '\nGit:\n'
if command -v git >/dev/null 2>&1; then
  git --version || status=1
else
  printf 'ERROR: git no está disponible en PATH.\n' >&2
  status=1
fi

if (( status != 0 )); then
  printf '\nERROR: faltan comprobaciones necesarias; revisar los mensajes anteriores.\n' >&2
  exit 1
fi
printf '\nDiagnóstico completado. No se instaló software.\n'
