#!/usr/bin/env bash
# Same as start.sh
exec "$(cd "$(dirname "$0")" && pwd)/start.sh" "$@"
