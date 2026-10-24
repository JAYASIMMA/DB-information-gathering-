# ==============================================================================
# Audit & Ingest UAT Database Cluster into e34data78
# Source: 34.100.237.205:5432 (GCP Cloud Database)
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

& $PythonBin "$ScriptDir\audit_uat_db.py" $args
