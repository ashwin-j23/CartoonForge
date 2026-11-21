#!/usr/bin/env bash
# Run a HawkScan command against a throwaway local copy of the backend.
#   scripts/stackhawk-scan.sh                  # full scan
#   scripts/stackhawk-scan.sh validate auth    # any other hawk subcommand (config path added automatically)
# The backend runs with a clean environment: .env off, an empty temp database, no Supabase / YouTube / AI keys,
# the scheduler off — attack traffic never reaches the live channel. The owner password is random per run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8765}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cf-hawk-XXXXXX")"
SCAN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
export SCAN_PASSWORD APP_HOST="http://localhost:$PORT"
export COMMIT_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo none)"
export BRANCH_NAME="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo none)"

env -i PATH="$PATH" HOME="$WORK" TMPDIR="$WORK" \
    CARTOONFORGE_NO_DOTENV=1 DATA_DIR="$WORK/data" INTERNAL_SCHEDULER=0 WORKER_MODE=inline \
    ADMIN_PASSWORD="$SCAN_PASSWORD" SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    "$ROOT/.venv/bin/python" -m uvicorn --app-dir "$ROOT/backend" app.main:app --host 127.0.0.1 --port "$PORT" \
    --log-level warning > "$WORK/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; wait $SERVER 2>/dev/null || true; rm -rf "$WORK"' EXIT

for _ in $(seq 60); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  kill -0 $SERVER 2>/dev/null || { echo "backend failed to start:"; cat "$WORK/server.log"; exit 1; }
  sleep 1
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "backend not healthy"; cat "$WORK/server.log"; exit 1; }

cd "$ROOT"
if [ $# -eq 0 ]; then
  hawk scan stackhawk.yml
else
  hawk "$@" stackhawk.yml
fi
