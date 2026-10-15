#!/usr/bin/env bash
set -euo pipefail

python /workspace/project/scripts/run_f4_crosstext2loc.py "$@"
chown -R "$F4_HOST_UID:$F4_HOST_GID" /artifacts /run-results
find /artifacts /run-results -type d -exec chmod 755 {} +
find /artifacts /run-results -type f -exec chmod 644 {} +
