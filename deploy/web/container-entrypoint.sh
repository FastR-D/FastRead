#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -gt 0 ]; then exec fastread "$@"; fi
fastread serve --listen 0.0.0.0:80 &
api_pid=$!
fastread worker --concurrency "${FASTREAD_WORKER_CONCURRENCY:-2}" &
worker_pid=$!
trap 'kill "$api_pid" "$worker_pid" 2>/dev/null || true; wait || true' EXIT TERM INT
wait -n "$api_pid" "$worker_pid"
