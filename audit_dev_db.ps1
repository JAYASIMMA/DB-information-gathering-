# ==============================================================================
# Audit & Ingest Dev Database Cluster into e34data78
# Source: 34.93.217.164:5432 (EC2 Instance)
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$PythonBin = "python"
if (Test-Path "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe"
} elseif (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\.venv\Scripts\python.exe"
}

& $PythonBin "$ScriptDir\audit_dev_db.py" $args
