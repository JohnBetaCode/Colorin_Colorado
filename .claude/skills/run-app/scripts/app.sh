#!/usr/bin/env bash
# Manage the Colorín Colorado Streamlit app (Docker Compose).
#
#   app.sh status    - container state + HTTP health of http://localhost:8502
#   app.sh up        - start (build if needed) in the background
#   app.sh test      - run the pytest suite inside the container
#   app.sh rebuild   - rebuild the image (after requirements.txt / Dockerfile changes) and restart
#   app.sh restart   - restart the container (config/.env changes, or code edited with no tab open)
#   app.sh down      - stop and remove the container
#   app.sh logs [N]  - last N log lines (default 100), then follow
#   app.sh gpu       - start (build if needed) the local GPU engine's server (Compose profile "gpu")
#   app.sh gpu-logs [N] - follow the GPU server's logs (download progress, loads, pages)
#
# For a full start with GPU detection, use ./launch.sh at the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT"
URL="http://localhost:8502"
GPU_URL="http://127.0.0.1:8602"

health() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL/_stcore/health" || true)
  if [ "$code" = "200" ]; then echo "HTTP health: OK ($URL)"; else echo "HTTP health: not responding (code: ${code:-none})"; fi
  local gpu
  gpu=$(curl -s --max-time 3 "$GPU_URL/health" || true)
  if [ -n "$gpu" ]; then echo "Local GPU server: $gpu"; else echo "Local GPU server: not running (optional; app.sh gpu)"; fi
}

# Google Cloud credentials are mounted by docker-compose.override.yml (git-ignored). Create it
# from the example when the host has the credentials file and the override does not exist yet.
adc_override() {
  if [ ! -f docker-compose.override.yml ] && [ -f "$HOME/.config/gcloud/application_default_credentials.json" ]; then
    cp docker-compose.override.example.yml docker-compose.override.yml
    echo "Created docker-compose.override.yml to mount your gcloud credentials."
  fi
}

wait_healthy() {
  for _ in $(seq 1 30); do
    if curl -s -o /dev/null --max-time 2 "$URL/_stcore/health"; then break; fi
    sleep 1
  done
  health
}

case "${1:-status}" in
  status)
    docker compose --profile gpu ps 2>/dev/null || true
    health
    ;;
  up)
    adc_override
    docker compose up -d --build
    wait_healthy
    ;;
  test)
    adc_override
    docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider -q tests
    ;;
  rebuild)
    adc_override
    docker compose build --no-cache app
    docker compose up -d
    wait_healthy
    ;;
  restart)
    docker compose restart app
    wait_healthy
    ;;
  down)
    docker compose --profile gpu down
    ;;
  gpu)
    docker compose --profile gpu up -d --build local-image
    health
    ;;
  gpu-logs)
    docker compose --profile gpu logs --tail "${2:-100}" -f local-image
    ;;
  logs)
    docker compose logs --tail "${2:-100}" -f app
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 1
    ;;
esac
