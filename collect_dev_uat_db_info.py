#!/usr/bin/env python3
"""Scheduled collector for every non-template database in Dev and UAT."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterator


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_FILE = SCRIPT_DIR / "logs" / "db-collector.log"
DEFAULT_LOCK_FILE = SCRIPT_DIR / ".db-collector.lock"


# Keep connection details and passwords out of logs if a driver includes them in
# an exception message.
def redact_error(message: str) -> str:
    message = re.sub(
        r"(?i)(postgres(?:ql)?(?:\+[^:/]+)?://)[^\s@]+@",
        r"\1<redacted>@",
        message,
    )
    message = re.sub(
        r"(?i)(password|passwd|pwd)\s*=\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    return message[:1000]


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else SCRIPT_DIR / path


@contextlib.contextmanager
def collector_lock(path: Path) -> Iterator[bool]:
    """Acquire a non-blocking process lock, supported on Linux and Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                acquired = False
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                acquired = False

        yield acquired
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def safe_result(result: dict[str, Any]) -> dict[str, Any]:
    """Persist only non-secret fields from the collector's result."""
    fields = (
        "status",
        "audit_id",
        "environment",
        "cluster_name",
        "engine_version",
        "total_databases_recorded",
        "total_tables_stored",
        "total_users_stored",
        "total_settings_stored",
        "total_cluster_storage",
    )
    return {field: result.get(field) for field in fields if field in result}


def validate_configuration(collector: Any) -> None:
    """Validate all three connection profiles without opening a database socket."""
    collector.parse_db_credentials(target="uat")
    collector.parse_db_credentials(target="dev")
    collector.parse_storage_credentials()


def collect(collector: Any) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    for target in ("uat", "dev"):
        started = dt.datetime.now(dt.timezone.utc)
        print(f"[{started.isoformat()}] Starting {target.upper()} database collection")
        try:
            result = collector.execute_discovery_and_store(target_name=target)
        except Exception as exc:  # continue so the other cluster is still audited
            message = redact_error(f"{type(exc).__name__}: {exc}")
            print(f"[{target.upper()}] FAILED: {message}")
            results.append(
                {
                    "target": target,
                    "status": "FAILED",
                    "error": message,
                    "started_at": started.isoformat(),
                    "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            )
            continue

        safe = safe_result(result)
        safe.update(
            {
                "target": target,
                "started_at": started.isoformat(),
                "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        results.append(safe)
        print(
            f"[{target.upper()}] SUCCESS: audit #{safe.get('audit_id')} | "
            f"databases={safe.get('total_databases_recorded', 0)} | "
            f"tables={safe.get('total_tables_stored', 0)}"
        )

    return results, 0 if all(item.get("status") == "SUCCESS" for item in results) else 1


def write_summary(path: Path, results: list[dict[str, Any]], exit_code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "SUCCESS" if exit_code == 0 else "FAILED",
        "exit_code": exit_code,
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect all non-template databases from Dev and UAT into the central warehouse."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate required environment variables without connecting to PostgreSQL",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to load, relative to this script directory (default: .env)",
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_FILE),
        help="Collector log path (default: logs/db-collector.log)",
    )
    parser.add_argument(
        "--lock-file",
        default=str(DEFAULT_LOCK_FILE),
        help="Overlap lock path (default: .db-collector.lock)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Import after loading the requested env file so the collector sees the
    # same configuration when it resolves the three connection profiles.
    from dotenv import load_dotenv

    env_file = resolve_path(args.env_file)
    load_dotenv(env_file, override=False)

    import store_all_dbs_to_e34data78 as collector

    if args.dry_run:
        try:
            validate_configuration(collector)
        except Exception as exc:
            print(f"Configuration validation failed: {redact_error(str(exc))}", file=sys.stderr)
            return 2
        print("Configuration is valid for UAT, Dev, and the central storage database.")
        return 0

    log_path = resolve_path(args.log_file)
    lock_path = resolve_path(args.lock_file)
    summary_path = log_path.with_name("db-collector-summary.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with collector_lock(lock_path) as acquired:
        if not acquired:
            print("Another database collector run is already active; exiting without a duplicate run.")
            return 0

        with log_path.open("a", encoding="utf-8") as log_handle:
            with contextlib.redirect_stdout(log_handle), contextlib.redirect_stderr(log_handle):
                print("\n" + "=" * 80)
                print(f"Database collector run started at {dt.datetime.now(dt.timezone.utc).isoformat()}")
                try:
                    results, exit_code = collect(collector)
                except Exception as exc:
                    message = redact_error(f"{type(exc).__name__}: {exc}")
                    print(f"Collector setup failed: {message}")
                    results = [{"target": "all", "status": "FAILED", "error": message}]
                    exit_code = 1
                write_summary(summary_path, results, exit_code)
                print(f"Run finished with exit code {exit_code}; summary: {summary_path}")

    print(f"Database collector finished with exit code {exit_code}. Log: {log_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
