#!/usr/bin/env bash
# AI Cost History Hub — macOS / Linux launcher (portal + cost dashboard)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONUTF8=1
export AGENT_COST_DASHBOARD_DIR="${AGENT_COST_DASHBOARD_DIR:-$ROOT/agent}"

echo
echo " ============================================"
echo "  AI Cost History Hub"
echo "  Local history and cost analytics"
echo " ============================================"
echo

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

Next steps (macOS / Linux):
  1. Install Python 3.12+, e.g.:
       macOS:  brew install python@3.12
       Ubuntu: sudo apt update && sudo apt install python3
  2. Verify:  python3 --version
  3. Re-run:  ./start.sh

EOF
  exit 1
fi

if "$PY" "$ROOT/scripts/coordinator.py" start --portal; then
  exit 0
else
  code=$?
  cat <<EOF >&2

[ERROR] Launcher failed with exit code ${code}.
If ports are busy:  $PY scripts/coordinator.py stop
Or check listeners:  lsof -iTCP:8753 -sTCP:LISTEN
                     lsof -iTCP:8740 -sTCP:LISTEN
See README Troubleshooting.

EOF
  exit "$code"
fi
