#!/usr/bin/env python3
"""
Audit & Ingest Old Production RDS Cluster (Live Past DB) into e34data78
Source: bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com:5432
Target: e34data78 on 34.100.237.205:5432
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from store_all_dbs_to_e34data78 import execute_discovery_and_store

if __name__ == "__main__":
    execute_discovery_and_store(target_name="old_prod")
