#!/usr/bin/env bash
# AI Cost History Hub — cost dashboard only (loopback)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONUTF8=1
export AGENT_COST_DASHBOARD_DIR="${AGENT_COST_DASHBOARD_DIR:-$ROOT/agent}"

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi
  return 1
}

if ! PY="$(pick_python)"; then
  cat <<'EOF' >&2

[ERROR] Python 3.12+ was not found on PATH.

Next steps:
  macOS:  brew install python@3.12
  Ubuntu: sudo apt update && sudo apt install python3
  Then:   python3 --version && ./start-cost-dashboard.sh

EOF
  exit 1
fi

if ! "$PY" "$ROOT/scripts/coordinator.py" open-cost; then
  code=$?
  cat <<EOF >&2

[ERROR] Could not open cost dashboard (exit ${code}).
Stop existing instance:  $PY scripts/coordinator.py stop
EOF
  exit "$code"
fi
