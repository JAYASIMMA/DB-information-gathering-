#!/usr/bin/env python3
"""
Audit & Ingest All Four Database Clusters into e34data78:
  1. UAT Database (GCP Cloud: 34.100.237.205)
  2. Dev Database (EC2 Instance: 34.93.217.164)
  3. Production RDS (AWS Marketplace: bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
  4. Old Production RDS (AWS Live Past: bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com)
Target Storage Database:
  e34data78 on 34.100.237.205:5432
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from store_all_dbs_to_e34data78 import audit_all_four_instances

if __name__ == "__main__":
    audit_all_four_instances()
