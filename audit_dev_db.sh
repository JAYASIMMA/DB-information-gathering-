#!/usr/bin/env bash
# ==============================================================================
# Audit & Ingest Dev Database Cluster into e34data78
# Source: 34.93.217.164:5432 (EC2 Instance)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PYTHON_BIN="python3"
if [ -f "${SCRIPT_DIR}/../instance-detail-information-script-/.venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/../instance-detail-information-script-/.venv/bin/python"
elif [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
    PYTHON_BIN="uv run python"
fi

${PYTHON_BIN} audit_dev_db.py "$@"
