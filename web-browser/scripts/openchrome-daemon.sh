#!/bin/sh
# Manage the skill-local openchrome HTTP daemon without modifying the project.

set -eu

PID_FILE="${TMPDIR:-/tmp}/web-browser-openchrome.pid"
LOG_FILE="${TMPDIR:-/tmp}/web-browser-openchrome.log"
OWNS_CHROME_FILE="${TMPDIR:-/tmp}/web-browser-openchrome-owns-chrome"
HEALTH_URL="http://127.0.0.1:9090/health"

load_openchrome() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "ERROR: nvm not found at $NVM_DIR" >&2
    echo "Run ./scripts/setup.sh from the web-browser skill directory." >&2
    exit 1
  fi
  . "$NVM_DIR/nvm.sh"
  if ! nvm use --lts >/dev/null 2>&1; then
    echo "ERROR: the current Node.js LTS release is not installed." >&2
    echo "Run ./scripts/setup.sh from the web-browser skill directory." >&2
    exit 1
  fi
  if ! command -v openchrome >/dev/null 2>&1; then
    echo "ERROR: openchrome is not installed under the active Node.js LTS release." >&2
    echo "Run ./scripts/setup.sh from the web-browser skill directory." >&2
    exit 1
  fi
}

healthy() {
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1
}

start() {
  mode="${1:-headed}"
  case "$mode" in
    headed) mode_args="--auto-launch" ;;
    headless) mode_args="--auto-launch --server-mode" ;;
    *) echo "Usage: $0 start [headed|headless]" >&2; exit 2 ;;
  esac

  if healthy; then
    echo "openchrome daemon already healthy at $HEALTH_URL"
    return
  fi

  load_openchrome

  if lsof -ti tcp:3199 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port 3199 is occupied but the openchrome health check failed." >&2
    exit 1
  fi

  rm -f "$PID_FILE" "$LOG_FILE" "$OWNS_CHROME_FILE"
  if ! lsof -ti tcp:9222 -sTCP:LISTEN >/dev/null 2>&1; then
    : > "$OWNS_CHROME_FILE"
  fi

  # shellcheck disable=SC2086
  OPENCHROME_ALLOW_UNAUTHENTICATED_HTTP=1 openchrome serve $mode_args --http 3199 --transport http --no-auto-elect >"$LOG_FILE" 2>&1 &
  daemon_pid=$!
  echo "$daemon_pid" > "$PID_FILE"

  attempts=0
  while [ "$attempts" -lt 40 ]; do
    if healthy; then
      echo "openchrome $mode daemon ready (pid $daemon_pid)"
      echo "log: $LOG_FILE"
      return
    fi
    if ! kill -0 "$daemon_pid" 2>/dev/null; then
      echo "ERROR: openchrome exited during startup." >&2
      tail -30 "$LOG_FILE" >&2
      exit 1
    fi
    attempts=$((attempts + 1))
    sleep 0.25
  done

  echo "ERROR: openchrome health check did not become ready." >&2
  tail -30 "$LOG_FILE" >&2
  exit 1
}

status() {
  if healthy; then
    curl -fsS "$HEALTH_URL"
    echo
  else
    echo "openchrome daemon is not healthy"
    exit 1
  fi
}

stop() {
  if [ -f "$PID_FILE" ]; then
    daemon_pid="$(cat "$PID_FILE")"
    if kill -0 "$daemon_pid" 2>/dev/null; then
      kill "$daemon_pid" 2>/dev/null || true
    fi
  fi

  if [ -f "$OWNS_CHROME_FILE" ]; then
    chrome_pids="$(lsof -ti tcp:9222 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$chrome_pids" ]; then
      kill $chrome_pids 2>/dev/null || true
    fi
  fi

  rm -f "$PID_FILE" "$LOG_FILE" "$OWNS_CHROME_FILE"
  echo "openchrome session stopped; skill-owned temporary files removed"
}

case "${1:-}" in
  start) start "${2:-headed}" ;;
  status) status ;;
  stop) stop ;;
  *) echo "Usage: $0 {start [headed|headless]|status|stop}" >&2; exit 2 ;;
esac
