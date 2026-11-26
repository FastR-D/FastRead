#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -f "${FASTREAD_ENV_FILE:-$ROOT/.env}" ]]; then
  set -a
  source "${FASTREAD_ENV_FILE:-$ROOT/.env}"
  set +a
fi
RUNTIME="${FASTREAD_RUNTIME_DIR:-$ROOT/.runtime/go-web}"
export FASTREAD_WEB_ROOT="${FASTREAD_WEB_ROOT:-$ROOT/.runtime/web-data}"
export FASTREAD_COOKIE_SECURE="${FASTREAD_COOKIE_SECURE:-false}"
PORT="${FASTREAD_PORT:-3015}"
HOST="${FASTREAD_HOST:-127.0.0.1}"
ACTION=start
OPEN=1
BUILD=1
ADMIN_EMAIL="${FASTREAD_ADMIN_EMAIL:-admin@fastread.local}"
for arg in "$@"; do
  case "$arg" in
    start|stop|restart|status|check|init-admin) ACTION="$arg" ;;
    --stop|--restart|--status|--check|--init-admin) ACTION="${arg#--}" ;;
    --no-open) OPEN=0 ;;
    --no-build|--quick) BUILD=0 ;;
    --help|-h) echo 'Usage: ./run.sh [start|stop|restart|status|check|init-admin] [--no-open] [--no-build]'; echo 'Config: .env (FASTREAD_PORT, FASTREAD_HOST, FASTREAD_WEB_ROOT, FASTREAD_DATABASE_URL, FASTREAD_ADMIN_EMAIL)'; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT > 0 && PORT < 65536 )) || { echo 'Invalid FASTREAD_PORT' >&2; exit 2; }
export FASTREAD_PUBLIC_ORIGIN="${FASTREAD_PUBLIC_ORIGIN:-http://127.0.0.1:$PORT}"
URL="$FASTREAD_PUBLIC_ORIGIN"
mkdir -p "$RUNTIME"
chmod 700 "$RUNTIME"
RUNTIME="$(cd "$RUNTIME" && pwd)"
exec 9>"$RUNTIME/launcher.lock"
flock -n 9 || { echo 'Another FastRead launcher is running.' >&2; exit 1; }
BIN="$RUNTIME/fastread"
start_time() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null || true; }
alive() {
  local pid saved
  [[ -f "$RUNTIME/$1.pid" ]] || return 1
  read -r pid saved < "$RUNTIME/$1.pid"
  [[ "$pid" =~ ^[0-9]+$ && -n "$saved" && "$(start_time "$pid")" == "$saved" ]] || return 1
  [[ "$(readlink "/proc/$pid/exe" 2>/dev/null)" == "$BIN" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}
stop_all() {
  local name pid saved
  for name in worker server; do
    if alive "$name"; then
      read -r pid saved < "$RUNTIME/$name.pid"
      kill -TERM "$pid"
      for ((i=0;i<100;i++)); do alive "$name" || break; sleep .1; done
      if alive "$name"; then echo "$name is still shutting down; retry stop shortly." >&2; return 1; fi
      echo "$name stopped"
    fi
    rm -f "$RUNTIME/$name.pid"
  done
}
check() {
  for tool in go node curl pdftotext pdfinfo flock setsid; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; return 1; }; done
  go version; node --version
  if command -v pnpm >/dev/null; then PNPM=(pnpm); elif command -v corepack >/dev/null; then PNPM=(corepack pnpm); else echo 'Install pnpm or corepack.' >&2; return 1; fi
}
case "$ACTION" in
 stop) stop_all; exit ;;
 status)
   running=1
   for name in server worker; do if alive "$name"; then echo "$name: running"; else echo "$name: stopped"; running=0; fi; done
   ((running)) || exit 1
   curl -fsS --max-time 3 "$URL/api/health" || exit 1
   echo; echo "$URL/"; exit ;;
 check) check; echo 'Dependencies ready'; exit ;;
 restart) stop_all ;;
esac
if alive server || alive worker; then echo 'FastRead is already running. Use ./run.sh restart or status.'; exit 0; fi
check
if [[ "$BUILD" == 1 || ! -x "$BIN" ]]; then
  (cd backend-go && go build -trimpath -o "$BIN.next" ./cmd/fastread)
  mv "$BIN.next" "$BIN"
fi
if [[ "$ACTION" == init-admin ]]; then
  if [[ -z "${FASTREAD_INITIAL_PASSWORD:-}" ]]; then read -r -s -p 'Administrator password (at least 12 characters): ' FASTREAD_INITIAL_PASSWORD; echo; export FASTREAD_INITIAL_PASSWORD; fi
  "$BIN" user-create --email "$ADMIN_EMAIL" --name '管理员' --admin
  exit
fi
if [[ "$BUILD" == 1 || ! -f fastread-frontend/dist/index.html ]]; then
  (cd fastread-frontend; [[ -d node_modules ]] || "${PNPM[@]}" install --frozen-lockfile; "${PNPM[@]}" build)
fi
if curl -s --connect-timeout 1 --max-time 2 "http://$HOST:$PORT/" >/dev/null; then echo "Port $PORT is occupied; no process was stopped." >&2; exit 1; fi
trap 'code=$?; if (( code != 0 )); then stop_all || true; echo "Startup failed. See $RUNTIME/*.log" >&2; fi' EXIT
for name in server worker; do
  if [[ "$name" == server ]]; then args=(serve --listen "$HOST:$PORT" --frontend "$ROOT/fastread-frontend/dist"); else args=(worker --concurrency "${FASTREAD_WORKER_CONCURRENCY:-2}"); fi
  nohup setsid "$BIN" "${args[@]}" </dev/null >>"$RUNTIME/$name.log" 2>&1 9>&- &
  pid=$!
  printf '%s %s\n' "$pid" "$(start_time "$pid")" > "$RUNTIME/$name.pid"
done
ready=0
for ((i=0;i<60;i++)); do
  if alive server && alive worker && curl -fsS --max-time 1 "$URL/api/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep .5
done
((ready)) || exit 1
trap - EXIT
echo "FastRead: $URL/"
echo "Data: $FASTREAD_WEB_ROOT | Logs: $RUNTIME"
if [[ "$OPEN" == 1 ]] && command -v xdg-open >/dev/null; then xdg-open "$URL/" >/dev/null 2>&1 9>&- & fi
