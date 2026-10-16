#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PORT=${ATLAS_API_PORT:-18000}
NAME=${ATLAS_API_CONTAINER_NAME:-atlas-mvp1-smoke}
OUTPUT=${ATLAS_SMOKE_OUTPUT:-results/generated/mvp1/http-stack-smoke.json}
LOG_FILE=$(mktemp /tmp/atlas-mvp1-stack.XXXXXX.log)

cleanup() {
  docker stop --timeout 30 "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

ATLAS_API_PORT="$PORT" ATLAS_API_CONTAINER_NAME="$NAME" "$ROOT/scripts/run_mvp1_api_docker.sh" >"$LOG_FILE" 2>&1 &
wrapper_pid=$!

for attempt in $(seq 1 60); do
  status=$(curl -s -o /tmp/atlas-mvp1-ready.json -w '%{http_code}' "http://127.0.0.1:$PORT/api/v1/health/ready" || true)
  if [[ "$status" == "200" ]]; then break; fi
  if ! kill -0 "$wrapper_pid" 2>/dev/null; then
    wait "$wrapper_pid"
  fi
  sleep 1
done
[[ "${status:-}" == "200" ]]

top_output=$(docker top "$NAME" -eo pid,ppid,args)
worker_count=$(TOP_OUTPUT="$top_output" python -c 'import os; print(sum("uvicorn backend.atlas_api.main:create_app" in line for line in os.environ["TOP_OUTPUT"].splitlines()))')
[[ "$worker_count" == "1" ]]

"$ROOT/.venv-geo/bin/python" "$ROOT/scripts/smoke_mvp1_http.py" \
  --base-url "http://127.0.0.1:$PORT" \
  --expected-25m "$ROOT/results/generated/f4/f44/25m/madrid-f42-final-en-001.json" \
  --expected-50m "$ROOT/results/generated/f4/f44/50m/madrid-f42-final-en-001.json" \
  --output "$ROOT/$OUTPUT"

cleanup
wait "$wrapper_pid" || true
trap - EXIT INT TERM
test -z "$(docker ps -q --filter name="$NAME")"
grep -q 'Application shutdown complete' "$LOG_FILE"
rm -f "$LOG_FILE"
echo "MVP.1 stack smoke: PASS"
