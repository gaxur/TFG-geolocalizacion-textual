#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
external_dir="$project_root/external"
target="$external_dir/CVG-Text"
source_url="https://github.com/yejy53/CVG-Text.git"
commit="6910d2747a94fbe985309bde60cd4732bcbbf50f"

if ! command -v git >/dev/null 2>&1; then
  printf 'ERROR: git no está disponible.\n' >&2
  exit 1
fi

if [[ -e "$target" || -L "$target" ]]; then
  if [[ ! -d "$target" ]] || [[ "$(git -C "$target" rev-parse --show-toplevel 2>/dev/null || true)" != "$target" ]]; then
    printf 'ERROR: %s ya existe y no es la raíz de un clon Git. No se modificó.\n' "$target" >&2
    exit 1
  fi
  if [[ "$(git -C "$target" remote get-url origin 2>/dev/null || true)" != "$source_url" ]]; then
    printf 'ERROR: el remoto origin de %s no coincide con %s.\n' "$target" "$source_url" >&2
    exit 1
  fi
  if [[ -n "$(git -C "$target" status --porcelain)" ]]; then
    printf 'ERROR: %s contiene cambios locales. No se modificó.\n' "$target" >&2
    exit 1
  fi
  if [[ "$(git -C "$target" rev-parse HEAD)" != "$commit" ]]; then
    printf 'ERROR: %s está en otro commit. Revisar manualmente antes de cambiarlo.\n' "$target" >&2
    exit 1
  fi
  printf 'CVG-Text ya está en el commit requerido: %s\n' "$commit"
else
  mkdir -p "$external_dir"
  git clone --no-checkout "$source_url" "$target"
  git -C "$target" checkout --detach "$commit"
  if [[ "$(git -C "$target" rev-parse HEAD)" != "$commit" ]]; then
    printf 'ERROR: no se obtuvo el commit solicitado en %s.\n' "$target" >&2
    exit 1
  fi
  printf 'Clon local de CVG-Text fijado en %s\n' "$commit"
fi

printf 'Código original: %s (autores de CVG-Text).\n' "$source_url"
printf 'Este clon en external/ no se incorpora al repositorio del TFG.\n'
