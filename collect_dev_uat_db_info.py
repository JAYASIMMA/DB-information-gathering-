#!/usr/bin/env python3
"""
Scheduled Collector for Database Clusters into e34data78.
Includes UAT, Dev, Production (RDS Marketplace), and Old Production (RDS Live Past).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collect_all_dbs_info import main

if __name__ == "__main__":
    raise SystemExit(main())
