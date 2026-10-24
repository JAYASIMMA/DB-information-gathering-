#!/usr/bin/env bash
# Collect every non-template database from UAT and Dev into the central warehouse.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
    exec "${SCRIPT_DIR}/.venv/bin/python" collect_dev_uat_db_info.py "$@"
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run python collect_dev_uat_db_info.py "$@"
fi

echo "ERROR: install uv or create .venv before running the collector." >&2
exit 1
