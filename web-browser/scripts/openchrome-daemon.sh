#!/bin/sh
# Manage the skill-owned openchrome HTTP daemon.
#
# Invoke this script by absolute path. Do not cd into the shared skills repo.
# The daemon always runs with cwd=$RUNTIME_HOME so openchrome's cwd-relative
# .openchrome/ writes never land in a project or in this skills repo.

set -eu

RUNTIME_HOME="${HOME}/.openchrome/web-browser-skill"
PROFILE_DIR="${HOME}/.openchrome/profile"
HEADLESS_PROFILE_DIR="${RUNTIME_HOME}/headless-profile"
PID_FILE="${RUNTIME_HOME}/daemon.pid"
LOG_FILE="${RUNTIME_HOME}/daemon.log"
OWNS_CHROME_FILE="${RUNTIME_HOME}/owns-chrome"
STATE_FILE="${RUNTIME_HOME}/daemon.state"
HEALTH_URL="http://127.0.0.1:9090/health"

load_openchrome() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    echo "ERROR: nvm not found at $NVM_DIR" >&2
    echo "Run $HOME/.agents/skills/web-browser/scripts/setup.sh" >&2
    exit 1
  fi
  . "$NVM_DIR/nvm.sh"
  if ! nvm use --lts >/dev/null 2>&1; then
    echo "ERROR: the current Node.js LTS release is not installed." >&2
    echo "Run $HOME/.agents/skills/web-browser/scripts/setup.sh" >&2
    exit 1
  fi
  if ! command -v openchrome >/dev/null 2>&1; then
    echo "ERROR: openchrome is not installed under the active Node.js LTS release." >&2
    echo "Run $HOME/.agents/skills/web-browser/scripts/setup.sh" >&2
    exit 1
  fi
}

healthy() {
  if ! curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    return 1
  fi
  # Stronger readiness: prefer dedicated /ready (newer openchrome) or chrome.connected in health
  if curl -fsS http://127.0.0.1:9090/ready >/dev/null 2>&1; then
    return 0
  fi
  if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"connected":true'; then
    return 0
  fi
  echo "WARNING: daemon HTTP ok but Chrome not connected (reconnect loop possible)" >&2
  return 1
}

chrome_on_9222() {
  lsof -ti tcp:9222 -sTCP:LISTEN 2>/dev/null || true
}

chrome_uses_dir() {
  expected="$1"
  pids="$(chrome_on_9222)"
  [ -n "$pids" ] || return 1
  for pid in $pids; do
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    case "$args" in
      *"--user-data-dir=$expected"*|*"--user-data-dir $expected"*) return 0 ;;
    esac
  done
  return 1
}

current_mode() {
  if [ -f "$STATE_FILE" ]; then
    cat "$STATE_FILE"
  fi
}

start() {
  mode="${1:-headed}"
  case "$mode" in
    headed|headless) ;;
    *) echo "Usage: $0 start [headed|headless]" >&2; exit 2 ;;
  esac
  if [ "$mode" = headed ]; then
    mkdir -p "$PROFILE_DIR"
  else
    mkdir -p "$HEADLESS_PROFILE_DIR"
  fi

  mkdir -p "$RUNTIME_HOME"
  if [ "$mode" = headed ]; then
    expected_profile="$PROFILE_DIR"
  else
    expected_profile="$HEADLESS_PROFILE_DIR"
  fi

  if healthy; then
    running_mode="$(current_mode)"
    if [ "$running_mode" = "$mode" ]; then
      echo "openchrome $mode daemon already healthy at $HEALTH_URL"
      echo "profile: $expected_profile"
      echo "runtime: $RUNTIME_HOME"
      echo "Use /ready endpoint or proton-mail.py for full readiness."
      return
    fi
    echo "ERROR: openchrome is already running in ${running_mode:-unknown} mode." >&2
    echo "Stop it first: $0 stop" >&2
    echo "Do not reuse a headless daemon for authenticated work." >&2
    exit 1
  fi

  load_openchrome

  if lsof -ti tcp:3199 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port 3199 is occupied but the openchrome health check failed." >&2
    echo "This is usually caused by a previous daemon that did not shut down cleanly." >&2
    echo "Run: $0 stop   (the improved stop now kills stray node processes)" >&2
    echo "Then try starting again." >&2
    exit 1
  fi

  if [ -n "$(chrome_on_9222)" ] && ! chrome_uses_dir "$expected_profile"; then
    echo "ERROR: port 9222 is already occupied by a Chrome that is not using $expected_profile." >&2
    echo "Stop that Chrome, or stop the previous daemon, then start again." >&2
    echo "Do not attach to daily Chrome. Headed work uses $PROFILE_DIR only." >&2
    exit 1
  fi

  rm -f "$PID_FILE" "$LOG_FILE" "$OWNS_CHROME_FILE" "$STATE_FILE"
  if [ -z "$(chrome_on_9222)" ]; then
    : > "$OWNS_CHROME_FILE"
  fi

  # cwd is RUNTIME_HOME so openchrome never writes .openchrome/ into a project.
  (
    cd "$RUNTIME_HOME"
    if [ "$mode" = headed ]; then
      OPENCHROME_ALLOW_UNAUTHENTICATED_HTTP=1 \
        openchrome serve --auto-launch \
          --user-data-dir "$PROFILE_DIR" --profile-directory Default \
          --http 3199 --transport http --no-auto-elect \
          >"$LOG_FILE" 2>&1
    else
      OPENCHROME_ALLOW_UNAUTHENTICATED_HTTP=1 \
        openchrome serve --auto-launch --server-mode \
          --user-data-dir "$HEADLESS_PROFILE_DIR" --profile-directory Default \
          --http 3199 --transport http --no-auto-elect \
          >"$LOG_FILE" 2>&1
    fi
  ) &
  daemon_pid=$!
  echo "$daemon_pid" > "$PID_FILE"
  echo "$mode" > "$STATE_FILE"

  attempts=0
  while [ "$attempts" -lt 40 ]; do
    if healthy; then
      echo "openchrome $mode daemon ready (pid $daemon_pid)"
      echo "profile: $([ "$mode" = headed ] && echo "$PROFILE_DIR" || echo "$HEADLESS_PROFILE_DIR")"
      echo "runtime: $RUNTIME_HOME"
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
    echo "=== full health ==="
    curl -fsS "$HEALTH_URL"
    echo
    echo "=== readiness ==="
    curl -fsS http://127.0.0.1:9090/ready 2>/dev/null || echo "no /ready endpoint (older openchrome)"
    echo
    running_mode="$(current_mode)"
    echo "mode: ${running_mode:-unknown}"
    echo "runtime: $RUNTIME_HOME"
    if [ "$running_mode" = "headed" ]; then
      echo "profile: $PROFILE_DIR"
    elif [ "$running_mode" = "headless" ]; then
      echo "profile: $HEADLESS_PROFILE_DIR"
    fi
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

  # Always kill any openchrome-mcp or node processes on our ports, even if PID file is stale.
  # This makes "stop" robust against the exact failure mode seen in the latest engineering report.
  pkill -f 'openchrome.*serve' 2>/dev/null || true
  pkill -f 'node.*3199' 2>/dev/null || true
  pkill -f 'node.*9222' 2>/dev/null || true
  sleep 2

  if [ -f "$OWNS_CHROME_FILE" ]; then
    chrome_pids="$(lsof -ti tcp:9222 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$chrome_pids" ]; then
      kill $chrome_pids 2>/dev/null || true
      sleep 1
    fi
  fi

  rm -f "$PID_FILE" "$LOG_FILE" "$OWNS_CHROME_FILE" "$STATE_FILE"
  echo "openchrome daemon stopped"
  echo "headed profile kept at $PROFILE_DIR"
}

case "${1:-}" in
  start) start "${2:-headed}" ;;
  status) status ;;
  stop) stop ;;
  *) echo "Usage: $0 {start [headed|headless]|status|stop}" >&2; exit 2 ;;
esac
