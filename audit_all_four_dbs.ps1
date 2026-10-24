# ==============================================================================
# Audit & Ingest All Four Database Clusters into e34data78:
#   1. UAT Database (GCP Cloud: 34.100.237.205)
#   2. Dev Database (EC2 Instance: 34.93.217.164)
#   3. Production RDS (AWS Marketplace: bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
#   4. Old Production RDS (AWS Live Past: bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
# Target Storage Database:
#   e34data78 on 34.100.237.205:5432
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$PythonBin = "python"
if (Test-Path "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\..\instance-detail-information-script-\.venv\Scripts\python.exe"
} elseif (Test-Path "$ScriptDir\.venv\Scripts\python.exe") {
    $PythonBin = "$ScriptDir\.venv\Scripts\python.exe"
}

& $PythonBin "$ScriptDir\audit_all_four_dbs.py" $args
