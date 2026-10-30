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
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT"
URL="http://localhost:8502"

health() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL/_stcore/health" || true)
  if [ "$code" = "200" ]; then echo "HTTP health: OK ($URL)"; else echo "HTTP health: not responding (code: ${code:-none})"; fi
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
    docker compose ps 2>/dev/null || true
    health
    ;;
  up)
    docker compose up -d --build
    wait_healthy
    ;;
  test)
    docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider -q tests
    ;;
  rebuild)
    docker compose build --no-cache app
    docker compose up -d
    wait_healthy
    ;;
  restart)
    docker compose restart app
    wait_healthy
    ;;
  down)
    docker compose down
    ;;
  logs)
    docker compose logs --tail "${2:-100}" -f app
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 1
    ;;
esac
