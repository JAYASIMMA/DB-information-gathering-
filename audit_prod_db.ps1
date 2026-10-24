# ==============================================================================
# Audit & Ingest Production RDS Cluster (Marketplace) into e34data78
# Source: bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com:5432
# Target: e34data78 on 34.100.237.205:5432
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$PythonBin = "python"
if (Test-Path "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe"
} elseif (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\.venv\Scripts\python.exe"
}

& $PythonBin "$ScriptDir\audit_prod_db.py" $args
