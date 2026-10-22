#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PORT=${MVP_HTTP_PORT:-18080}
PROJECT=${MVP_COMPOSE_PROJECT:-atlas-mvp-smoke}
OUTPUT=${MVP_SMOKE_OUTPUT:-results/generated/mvp3/stack-smoke.json}
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/compose.mvp.yaml")

cleanup() {
  "${COMPOSE[@]}" --profile test down --timeout 30 --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

export MVP_HTTP_PORT=$PORT
export MVP_COMPOSE_PROJECT=$PROJECT
export MVP_BIND_HOST=${MVP_BIND_HOST:-127.0.0.1}
export MVP_CLIP_CACHE_DIR=${MVP_CLIP_CACHE_DIR:-$HOME/.cache/clip}
export MVP_QWEN_MODEL_DIR=${MVP_QWEN_MODEL_DIR:-$HOME/models/hf/Qwen3-8B-b968826d9c46}
export MVP_API_CONTAINER_NAME=${MVP_API_CONTAINER_NAME:-$PROJECT-api}
export MVP_FRONTEND_CONTAINER_NAME=${MVP_FRONTEND_CONTAINER_NAME:-$PROJECT-frontend}

"$ROOT/scripts/run_mvp3_stack.sh" -d

for attempt in $(seq 1 240); do
  status=$(curl -s -o /tmp/atlas-mvp3-health.json -w '%{http_code}' "http://127.0.0.1:$PORT/healthz" || true)
  api_id=$("${COMPOSE[@]}" ps -q api)
  frontend_id=$("${COMPOSE[@]}" ps -q frontend)
  api_health=$(if [[ -n "$api_id" ]]; then docker inspect "$api_id" --format '{{.State.Health.Status}}'; else printf 'missing'; fi)
  frontend_health=$(if [[ -n "$frontend_id" ]]; then docker inspect "$frontend_id" --format '{{.State.Health.Status}}'; else printf 'missing'; fi)
  [[ "$status" == "200" && "$api_health" == "healthy" && "$frontend_health" == "healthy" ]] && break
  sleep 1
done
[[ "${status:-}" == "200" ]]

[[ -n "$api_id" && -n "$frontend_id" ]]
[[ "$(docker inspect "$api_id" --format '{{.State.Health.Status}}')" == "healthy" ]]
[[ "$(docker inspect "$frontend_id" --format '{{.State.Health.Status}}')" == "healthy" ]]
worker_count=$(docker top "$api_id" -eo pid,args | grep 'uvicorn' | grep 'backend.atlas_api.main:create_app' | grep -c -- '--workers 1' || true)
[[ "$worker_count" == "1" ]]

python "$ROOT/scripts/smoke_mvp3_http.py" --base-url "http://127.0.0.1:$PORT" --output "$ROOT/$OUTPUT"
"${COMPOSE[@]}" --profile test build browser-check
"${COMPOSE[@]}" --profile test run --rm browser-check npm run test:browser
"${COMPOSE[@]}" --profile test run --rm browser-check npm run test:browser:real

cleanup
trap - EXIT INT TERM
test -z "$(docker ps -q --filter label=com.docker.compose.project="$PROJECT")"
echo "MVP.3 integrated stack smoke: PASS"
