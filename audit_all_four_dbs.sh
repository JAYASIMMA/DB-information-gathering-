#!/usr/bin/env bash
# ==============================================================================
# Audit & Ingest All Four Database Clusters into e34data78:
#   1. UAT Database (GCP Cloud: 34.100.237.205)
#   2. Dev Database (EC2 Instance: 34.93.217.164)
#   3. Production RDS (AWS Marketplace: bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
#   4. Old Production RDS (AWS Live Past: bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
# Target Storage Database:
#   e34data78 on 34.100.237.205:5432
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN="python3"
if [ -f "$SCRIPT_DIR/../instance-detail-information-script-/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../instance-detail-information-script-/.venv/Scripts/python.exe"
elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/audit_all_four_dbs.py" "$@"
