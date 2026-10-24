# ==============================================================================
# Audit & Ingest Both Database Clusters (UAT + Dev) into e34data78
# Sources:
#   1. UAT: 34.100.237.205:5432 (GCP Cloud Database)
#   2. Dev: 34.93.217.164:5432 (EC2 Instance)
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

& $PythonBin "$ScriptDir\audit_both_dbs.py" $args
