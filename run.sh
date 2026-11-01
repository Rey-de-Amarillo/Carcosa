#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ ! -f app/data/report.json ]; then
  python3 scripts/build_report.py
fi
exec python3 server.py "$@"
