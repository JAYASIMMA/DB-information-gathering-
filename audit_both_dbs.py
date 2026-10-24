#!/usr/bin/env python3
"""Compatibility entry point for the scheduled Dev + UAT collector."""

from collect_dev_uat_db_info import main


if __name__ == "__main__":
    raise SystemExit(main())
