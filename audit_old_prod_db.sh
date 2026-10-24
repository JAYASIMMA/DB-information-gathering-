#!/usr/bin/env bash
# ==============================================================================
# Audit & Ingest Old Production RDS Cluster (Live Past DB) into e34data78
# Source: bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com:5432
# Target: e34data78 on 34.100.237.205:5432
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="python3"
if [ -f "$SCRIPT_DIR/../instance-detail-information-script-/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../instance-detail-information-script-/.venv/Scripts/python.exe"
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/audit_old_prod_db.py" "$@"
