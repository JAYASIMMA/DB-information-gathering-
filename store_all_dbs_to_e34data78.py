#!/usr/bin/env python3
"""
Multi-Database Discovery & Insertion Engine for e34data78
=========================================================
Audits all databases, instance metrics, user tables, connections, and configuration
across PostgreSQL database instances (UAT on 34.100.237.205 and Dev on 34.93.217.164)
and stores all gathered information into the central storage database named 'e34data78'.

Features:
- Seamlessly handles standard 'postgresql://' as well as 'postgresql+asyncpg://' URLs.
- Supports UAT database (34.100.237.205) and Dev database (34.93.217.164) out of the box.
- Independent separation of the source cluster being audited and the target storage database (e34data78).
- Automatically initializes the relational storage schema in 'e34data78' (tables, indexes, views).
- Connects to every discovered database on the instance (e.g. sarla-uat, bettrlabs, consumer_dev, etc.).
- Inserts comprehensive instance-level and per-database table details into 'e34data78'.
- Automatically syncs with the backend telemetry cache.
"""

import os
import sys
import json
import argparse
import datetime
import urllib.request
from urllib.parse import urlparse, unquote
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

try:
    import pg8000.native
except ImportError:
    print("[!] ERROR: pg8000 is required. Install via `pip install pg8000` or `uv add pg8000`")
    sys.exit(1)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ANSI terminal colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
GRAY = "\033[90m"


def print_table(rows, headers):
    if HAS_TABULATE:
        return tabulate(rows, headers=headers, tablefmt="rounded_grid")
    lines = [" | ".join(str(h) for h in headers), "-" * 75]
    for r in rows:
        lines.append(" | ".join(str(v) for v in r))
    return "\n".join(lines)


# ==============================================================================
# KNOWN DATABASE CLUSTER REGISTRY
# ==============================================================================
CLUSTERS_REGISTRY = {
    "uat": {
        "key": "uat",
        "name": "UAT Database Cluster (GCP Cloud)",
        "environment": "uat",
        "url_envs": ["UAT_DATABASE_URL", "DATABASE_URL_UAT"],
        "host_envs": ["UAT_DB_HOST", "DB_HOST_UAT"],
        "port_envs": ["UAT_DB_PORT", "DB_PORT_UAT"],
        "user_envs": ["UAT_DB_USER", "DB_USER_UAT"],
        "password_envs": ["UAT_DB_PASSWORD", "UAT_DB_PWD", "DB_PWD_UAT"],
        "admin_db_envs": ["UAT_DB_ADMIN_DATABASE", "UAT_DB_NAME"],
        "default_host": "34.100.237.205",
        "default_port": 5432,
        "default_user": "postgres",
        "default_password": "gvufvjfvavVASVJVAHSVDhbbvjhdUAThbBEttr",
        "default_admin_db": "postgres",
    },
    "dev": {
        "key": "dev",
        "name": "Dev Database Cluster (EC2 Instance)",
        "environment": "development",
        "url_envs": ["DEV_DATABASE_URL", "DATABASE_URL_DEV"],
        "host_envs": ["DEV_DB_HOST", "DB_HOST_DEV"],
        "port_envs": ["DEV_DB_PORT", "DB_PORT_DEV"],
        "user_envs": ["DEV_DB_USER", "DB_USER_DEV"],
        "password_envs": ["DEV_DB_PASSWORD", "DEV_DB_PWD", "DB_PWD_DEV"],
        "admin_db_envs": ["DEV_DB_ADMIN_DATABASE", "DEV_DB_NAME"],
        "default_host": "34.93.217.164",
        "default_port": 5432,
        "default_user": "postgres",
        "default_password": "BettrvFYCDwehfgsdfsdfvvVDGHadvaHVDuv",
        "default_admin_db": "postgres",
    },
    "prod": {
        "key": "prod",
        "name": "Production RDS Cluster (Marketplace)",
        "environment": "production",
        "url_envs": ["PROD_DATABASE_URL", "PRODUCTION_DATABASE_URL", "DATABASE_URL_PROD"],
        "host_envs": ["PROD_DB_HOST", "PRODUCTION_DB_HOST"],
        "port_envs": ["PROD_DB_PORT", "PRODUCTION_DB_PORT"],
        "user_envs": ["PROD_DB_USER", "PRODUCTION_DB_USER"],
        "password_envs": ["PROD_DB_PASSWORD", "PROD_DB_PWD", "PRODUCTION_DB_PASSWORD", "PRODUCTION_DB_PWD"],
        "admin_db_envs": ["PROD_DB_ADMIN_DATABASE", "PROD_DB_NAME"],
        "default_host": "bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com",
        "default_port": 5432,
        "default_user": "postgres",
        "default_password": "9nj-Ahng5FCbdfjdsbcdggbj*7VGgbj",
        "default_admin_db": "postgres",
    },
    "old_prod": {
        "key": "old_prod",
        "name": "Old Production RDS Cluster (Live Past DB)",
        "environment": "old_production",
        "url_envs": ["OLD_PROD_DATABASE_URL", "LIVE_PAST_DATABASE_URL", "PAST_PROD_DATABASE_URL"],
        "host_envs": ["OLD_PROD_DB_HOST", "LIVE_PAST_DB_HOST"],
        "port_envs": ["OLD_PROD_DB_PORT", "LIVE_PAST_DB_PORT"],
        "user_envs": ["OLD_PROD_DB_USER", "LIVE_PAST_DB_USER"],
        "password_envs": ["OLD_PROD_DB_PASSWORD", "OLD_PROD_DB_PWD", "LIVE_PAST_DB_PWD"],
        "admin_db_envs": ["OLD_PROD_DB_NAME", "OLD_PROD_DB_ADMIN_DATABASE", "LIVE_PAST_DB_NAME"],
        "default_host": "bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com",
        "default_port": 5432,
        "default_user": "bl_pg_admin",
        "default_password": "7oRfnIND467GrxOIArQw",
        "default_admin_db": "ag4good_db",
    },
}

CLUSTER_ALIASES = {
    "uat": "uat",
    "dev": "dev",
    "development": "dev",
    "prod": "prod",
    "production": "prod",
    "marketplace": "prod",
    "marketplace_prod": "prod",
    "old_prod": "old_prod",
    "old_production": "old_prod",
    "oldprod": "old_prod",
    "live_past": "old_prod",
    "live_past_old": "old_prod",
    "past_prod": "old_prod",
    "ag4good": "old_prod",
    "ag4good_db": "old_prod",
}


def clean_database_url(url: str) -> str:
    """Normalize asyncpg, psql, or custom prefixes into standard postgresql format."""
    clean = url.strip().strip("'").strip('"')
    if clean.startswith("postgresql+asyncpg://"):
        clean = "postgresql://" + clean[len("postgresql+asyncpg://"):]
    elif clean.startswith("postgres+asyncpg://"):
        clean = "postgresql://" + clean[len("postgres+asyncpg://"):]
    elif clean.startswith("postgres://"):
        clean = "postgresql://" + clean[len("postgres://"):]
    return clean


def _get_first_env(keys: List[str], default: str = "") -> str:
    for k in keys:
        val = os.getenv(k, "").strip()
        if val:
            return val
    return default


def _parse_database_url(url: str, *, default_db: str = "postgres") -> Dict[str, Any]:
    cleaned = clean_database_url(url)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
        raise ValueError("Database URL must use postgresql:// and include a host")
    if not parsed.username or parsed.password is None:
        raise ValueError("Database URL must include a username and password")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
        "admin_db": parsed.path.lstrip("/").strip() or default_db,
    }


def parse_db_credentials(custom_url: Optional[str] = None, target: Optional[str] = None) -> Dict[str, Any]:
    """Resolve one cluster from an explicit URL or its environment-specific variables, with safe fallbacks."""
    raw_key = (target or "").strip().lower()
    canonical_key = CLUSTER_ALIASES.get(raw_key, raw_key)
    if canonical_key not in CLUSTERS_REGISTRY:
        if custom_url:
            connection = _parse_database_url(custom_url)
            return {
                "key": "custom",
                "name": f"Custom Cluster ({connection['host']})",
                "environment": "custom",
                **connection,
            }
        valid_keys = ", ".join(CLUSTERS_REGISTRY.keys())
        raise ValueError(f"Target '{target}' is invalid. Supported targets: {valid_keys}, both, four, all")

    reg = CLUSTERS_REGISTRY[canonical_key]
    url = custom_url or _get_first_env(reg["url_envs"])
    if url:
        connection = _parse_database_url(url, default_db=reg["default_admin_db"])
    else:
        host = _get_first_env(reg["host_envs"], reg["default_host"])
        port_str = _get_first_env(reg["port_envs"], str(reg["default_port"]))
        port = int(port_str) if port_str.isdigit() else reg["default_port"]
        user = _get_first_env(reg["user_envs"], reg["default_user"])
        password = _get_first_env(reg["password_envs"], reg["default_password"])
        admin_db = _get_first_env(reg["admin_db_envs"], reg["default_admin_db"])

        connection = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "admin_db": admin_db,
        }

    return {
        "key": reg["key"],
        "name": reg["name"],
        "environment": reg["environment"],
        **connection,
    }


def parse_storage_credentials(custom_storage_url: Optional[str] = None) -> Dict[str, Any]:
    """Resolve the central warehouse connection (e34data78) with safe fallbacks."""
    storage_url = custom_storage_url or os.getenv("STORAGE_DATABASE_URL", "").strip()
    if storage_url:
        connection = _parse_database_url(storage_url, default_db=os.getenv("TARGET_STORAGE_DB", "e34data78"))
        storage_db = connection.pop("admin_db")
    else:
        host = os.getenv("STORAGE_DB_HOST", "34.100.237.205").strip()
        port_str = os.getenv("STORAGE_DB_PORT", "5432").strip()
        port = int(port_str) if port_str.isdigit() else 5432
        user = os.getenv("STORAGE_DB_USER", "postgres").strip()
        password = (
            os.getenv("STORAGE_DB_PASSWORD", "").strip()
            or os.getenv("STORAGE_DB_PWD", "").strip()
            or "gvufvjfvavVASVJVAHSVDhbbvjhdUAThbBEttr"
        )
        storage_db = os.getenv("TARGET_STORAGE_DB", "e34data78").strip() or "e34data78"
        connection = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
        }

    return {**connection, "storage_db": storage_db}


def get_pg_connection(user: str, password: str, host: str, port: int, database: str, timeout: int = 10):
    """
    Connects to PostgreSQL using pg8000, attempting non-SSL first (or SSL fallback)
    for seamless cloud/EC2/RDS compatibility.
    """
    try:
        return pg8000.native.Connection(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl_context=False,
            timeout=timeout,
        )
    except Exception as e_plain:
        try:
            return pg8000.native.Connection(
                user=user,
                password=password,
                host=host,
                port=port,
                database=database,
                ssl_context=True,
                timeout=timeout,
            )
        except Exception:
            raise e_plain


# ==============================================================================
# SCHEMA INITIALIZATION FOR e34data78
# ==============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS db_instance_audits (
    id SERIAL PRIMARY KEY,
    audit_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    engine_version VARCHAR(64),
    full_version TEXT,
    postmaster_started_at TIMESTAMPTZ,
    uptime VARCHAR(64),
    total_databases_count INT DEFAULT 0,
    total_cluster_storage_pretty VARCHAR(64),
    total_cluster_storage_bytes BIGINT DEFAULT 0,
    cache_hit_ratio_pct NUMERIC(5, 2),
    current_connections INT DEFAULT 0,
    active_connections INT DEFAULT 0,
    idle_connections INT DEFAULT 0,
    idle_in_transaction INT DEFAULT 0,
    max_connections INT DEFAULT 0,
    connection_usage_pct NUMERIC(5, 2),
    cpu_computing_queries INT DEFAULT 0,
    io_waiting_queries INT DEFAULT 0,
    lock_waiting_queries INT DEFAULT 0,
    raw_json_summary JSONB,
    environment_profile VARCHAR(64),
    instance_name VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_instance_audits_ts ON db_instance_audits (audit_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_instance_audits_host ON db_instance_audits (host, port);

CREATE TABLE IF NOT EXISTS db_cluster_users (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    username VARCHAR(128) NOT NULL,
    is_superuser BOOLEAN DEFAULT FALSE,
    can_login BOOLEAN DEFAULT TRUE,
    conn_limit INT DEFAULT -1,
    granted_roles TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_users_audit_id ON db_cluster_users (audit_id);
CREATE INDEX IF NOT EXISTS idx_cluster_users_username ON db_cluster_users (username);

CREATE TABLE IF NOT EXISTS db_cluster_settings (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL,
    setting_name VARCHAR(128) NOT NULL,
    setting_value TEXT,
    unit VARCHAR(32),
    source VARCHAR(64),
    short_desc TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_settings_audit_id ON db_cluster_settings (audit_id);
CREATE INDEX IF NOT EXISTS idx_cluster_settings_name ON db_cluster_settings (setting_name);

CREATE TABLE IF NOT EXISTS db_database_catalog (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128) NOT NULL,
    is_template BOOLEAN DEFAULT FALSE,
    disk_size_pretty VARCHAR(64),
    disk_size_bytes BIGINT DEFAULT 0,
    encoding VARCHAR(32),
    db_collation VARCHAR(64),
    total_connections INT DEFAULT 0,
    active_connections INT DEFAULT 0,
    idle_connections INT DEFAULT 0,
    idle_in_transaction INT DEFAULT 0,
    user_tables_count INT DEFAULT 0,
    user_views_count INT DEFAULT 0,
    user_indexes_count INT DEFAULT 0,
    inspection_status VARCHAR(64) NOT NULL DEFAULT 'PENDING',
    inspection_error TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_db_catalog_audit_id ON db_database_catalog (audit_id);
CREATE INDEX IF NOT EXISTS idx_db_catalog_name ON db_database_catalog (database_name);

CREATE TABLE IF NOT EXISTS db_database_tables (
    id SERIAL PRIMARY KEY,
    database_catalog_id INT NOT NULL REFERENCES db_database_catalog(id) ON DELETE CASCADE,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128) NOT NULL,
    schema_name VARCHAR(128) NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    full_table_name VARCHAR(256) NOT NULL,
    total_size_pretty VARCHAR(64),
    total_size_bytes BIGINT DEFAULT 0,
    table_size_pretty VARCHAR(64),
    table_size_bytes BIGINT DEFAULT 0,
    index_size_pretty VARCHAR(64),
    index_size_bytes BIGINT DEFAULT 0,
    estimated_rows BIGINT DEFAULT 0,
    seq_scan BIGINT DEFAULT 0,
    idx_scan BIGINT DEFAULT 0,
    n_dead_tup BIGINT DEFAULT 0,
    last_vacuum TIMESTAMPTZ,
    last_autovacuum TIMESTAMPTZ,
    last_analyze TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_db_tables_catalog_id ON db_database_tables (database_catalog_id);
CREATE INDEX IF NOT EXISTS idx_db_tables_audit_id ON db_database_tables (audit_id);
CREATE INDEX IF NOT EXISTS idx_db_tables_dbname ON db_database_tables (database_name);
CREATE INDEX IF NOT EXISTS idx_db_tables_size_bytes ON db_database_tables (total_size_bytes DESC);

CREATE TABLE IF NOT EXISTS db_database_active_queries (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128),
    pid INT,
    username VARCHAR(128),
    client_addr VARCHAR(64),
    state VARCHAR(64),
    duration_seconds NUMERIC(10, 2),
    duration_formatted VARCHAR(64),
    wait_event_type VARCHAR(64),
    wait_event VARCHAR(64),
    query_preview TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_active_queries_audit_id ON db_database_active_queries (audit_id);
CREATE INDEX IF NOT EXISTS idx_active_queries_dbname ON db_database_active_queries (database_name);

ALTER TABLE db_instance_audits ADD COLUMN IF NOT EXISTS environment_profile VARCHAR(64);
ALTER TABLE db_instance_audits ADD COLUMN IF NOT EXISTS instance_name VARCHAR(128);

DROP VIEW IF EXISTS v_all_databases_summary CASCADE;
CREATE OR REPLACE VIEW v_all_databases_summary AS
SELECT 
    a.id AS audit_id,
    a.audit_timestamp,
    a.host AS cluster_host,
    c.database_name,
    c.disk_size_pretty,
    c.disk_size_bytes,
    c.encoding,
    c.db_collation,
    c.user_tables_count,
    c.user_views_count,
    c.user_indexes_count,
    c.total_connections,
    c.inspection_status
FROM db_database_catalog c
JOIN db_instance_audits a ON c.audit_id = a.id
ORDER BY a.audit_timestamp DESC, c.disk_size_bytes DESC;

DROP VIEW IF EXISTS v_largest_tables_cross_db CASCADE;
CREATE OR REPLACE VIEW v_largest_tables_cross_db AS
SELECT 
    t.audit_id,
    t.database_name,
    t.full_table_name,
    t.total_size_pretty,
    t.total_size_bytes,
    t.table_size_pretty,
    t.index_size_pretty,
    t.estimated_rows,
    t.n_dead_tup,
    t.recorded_at
FROM db_database_tables t
ORDER BY t.audit_id DESC, t.total_size_bytes DESC;

-- 7. Aggregated Snapshot Table for Frontend API & Rust Backend
CREATE TABLE IF NOT EXISTS infra_instances (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('ec2', 'rds')),
    payload      JSONB NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS infra_instances_kind_idx
    ON infra_instances (kind);
"""


def get_rds_instance_identity(host: str, env_profile: str, cluster_title: str) -> Tuple[str, str, str, str]:
    """Returns (inst_id, display_name, short_name, env_name) matching backend contract."""
    host_lower = (host or "").lower()
    prof_lower = (env_profile or "").lower()
    if host == "34.100.237.205" or "uat" in prof_lower:
        return ("rds-uat", "PostgreSQL UAT Cluster (34.100.237.205)", "UAT RDS", "uat")
    elif host == "34.93.217.164" or "dev" in prof_lower:
        return ("rds-dev", "PostgreSQL Dev Cluster (34.93.217.164)", "Dev RDS", "development")
    elif "bettrlabs-mp-prod" in host_lower or prof_lower in ("prod", "production", "marketplace"):
        return ("rds-prod", "PostgreSQL Production Cluster (AWS RDS Marketplace)", "Prod RDS", "production")
    elif "bettrlabsprod" in host_lower or "old" in prof_lower:
        return ("rds-old-prod", "PostgreSQL Old Prod Cluster (AWS RDS Live Past)", "Old Prod RDS", "old_production")
    else:
        clean_host = host.replace(".", "-")
        return (f"rds-{clean_host}", cluster_title or f"PostgreSQL Cluster ({host})", f"RDS {host}", prof_lower or "production")


def upsert_infra_instance_db(store_con, inst_id: str, kind: str, payload: Dict[str, Any]) -> str:
    """
    Inserts or updates database instance details into `infra_instances` with primary key constraint:
      - First time: Inserts the basic & full database instance details into `infra_instances`.
      - Already inserted: Compares values with stored payload; if unchanged, skips update; if changed, updates payload.
    Returns: 'INSERTED', 'UPDATED', or 'UNCHANGED'
    """
    # 1. Ensure table and constraint exist
    store_con.run("""
        CREATE TABLE IF NOT EXISTS infra_instances (
            id           TEXT PRIMARY KEY,
            kind         TEXT NOT NULL CHECK (kind IN ('ec2', 'rds')),
            payload      JSONB NOT NULL,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS infra_instances_kind_idx ON infra_instances (kind);
    """)

    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    # 2. Check if instance already exists
    existing_rows = store_con.run(
        "SELECT payload, kind FROM infra_instances WHERE id = :id",
        id=inst_id
    )

    if not existing_rows:
        # First time for this instance: INSERT
        store_con.run(
            """
            INSERT INTO infra_instances (id, kind, payload, refreshed_at)
            VALUES (:id, :kind, :payload, now())
            """,
            id=inst_id,
            kind=kind,
            payload=payload_json
        )
        print(f"{BOLD}{GREEN}[✓] infra_instances: FIRST-TIME INSERT for database instance '{inst_id}' ({kind}){RESET}")
        return "INSERTED"
    else:
        # Already inserted: compare values
        existing_raw = existing_rows[0][0]
        existing_kind = existing_rows[0][1]
        if isinstance(existing_raw, str):
            try:
                existing_payload = json.loads(existing_raw)
            except Exception:
                existing_payload = {}
        elif isinstance(existing_raw, dict):
            existing_payload = existing_raw
        else:
            existing_payload = {}

        # Compare payloads ignoring volatile timestamp
        comp_existing = {k: v for k, v in existing_payload.items() if k not in ("timestamp",)}
        comp_new = {k: v for k, v in payload.items() if k not in ("timestamp",)}

        if comp_existing == comp_new and existing_kind == kind:
            print(f"{GRAY}[=] infra_instances: Database instance '{inst_id}' already exists and values are unchanged; skipping update.{RESET}")
            return "UNCHANGED"
        else:
            store_con.run(
                """
                UPDATE infra_instances
                SET kind = :kind,
                    payload = :payload,
                    refreshed_at = now()
                WHERE id = :id
                """,
                id=inst_id,
                kind=kind,
                payload=payload_json
            )
            print(f"{BOLD}{YELLOW}[~] infra_instances: Database instance '{inst_id}' values changed; updated payload.{RESET}")
            return "UPDATED"


def cleanup_old_db_audits(store_con, days: int = 10, dry_run: bool = False) -> int:
    """
    Deletes audit sessions older than `days` days from db_instance_audits in e34data78.
    Because of ON DELETE CASCADE on foreign keys, all related records in:
      - db_cluster_users
      - db_cluster_settings
      - db_database_catalog
      - db_database_tables
      - db_database_active_queries
    are automatically pruned.
    Note: infra_instances is the current snapshot table and is NOT deleted.
    """
    if days <= 0:
        return 0
    try:
        count_rows = store_con.run(
            "SELECT COUNT(*) FROM db_instance_audits WHERE audit_timestamp < NOW() - (:days * INTERVAL '1 day') OR created_at < NOW() - (:days * INTERVAL '1 day');",
            days=days
        )
        count = count_rows[0][0] if count_rows else 0
        if count == 0:
            return 0
        if dry_run:
            print(f"{YELLOW}[Retention] DRY-RUN: {count} database cluster audit session(s) older than {days} days would be deleted.{RESET}")
            return count
        store_con.run(
            "DELETE FROM db_instance_audits WHERE audit_timestamp < NOW() - (:days * INTERVAL '1 day') OR created_at < NOW() - (:days * INTERVAL '1 day');",
            days=days
        )
        print(f"{GREEN}[Retention] Successfully pruned {count} database cluster audit session(s) older than {days} days from e34data78.{RESET}")
        return count
    except Exception as e:
        print(f"{YELLOW}[Retention] Warning: Automatic retention cleanup failed: {e}{RESET}")
        return 0


def ensure_target_db_and_schema(storage_creds: Dict[str, Any]):
    """Connects to the storage host, ensures target DB exists, and runs DDL statements."""
    host = storage_creds["host"]
    port = storage_creds["port"]
    user = storage_creds["user"]
    password = storage_creds["password"]
    storage_db = storage_creds["storage_db"]

    print(f"\n[*] Checking target storage database '{storage_db}' on {host}:{port}...")
    
    # 1. Connect to postgres admin db to verify database exists
    con = get_pg_connection(user, password, host, port, "postgres")
    try:
        check_q = f"SELECT 1 FROM pg_database WHERE datname = '{storage_db}'"
        exists = len(con.run(check_q)) > 0
        if not exists:
            print(f"[*] Database '{storage_db}' does not exist. Creating it now...")
            con.run(f"CREATE DATABASE {storage_db}")
            print(f"[✓] Successfully created database '{storage_db}'.")
        else:
            print(f"[✓] Storage database '{storage_db}' already exists.")
    finally:
        con.close()

    # 2. Connect to the target storage database and execute schema DDL
    print(f"[*] Ensuring storage schema and tables exist in '{storage_db}'...")
    store_con = get_pg_connection(user, password, host, port, storage_db)
    try:
        statements = [stmt.strip() for stmt in SCHEMA_SQL.split(";") if stmt.strip()]
        for stmt in statements:
            store_con.run(stmt)
        print(f"[✓] Storage schema in '{storage_db}' is ready (tables, indexes, views verified).")
    finally:
        store_con.close()


# ==============================================================================
# AUDIT AND INSERTION PIPELINE
# ==============================================================================

def execute_discovery_and_store(
    source_url: Optional[str] = None,
    target_name: Optional[str] = None,
    storage_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main execution pipeline:
    1. Connects to primary cluster to audit.
    2. Collects hardware, settings, users, and version info.
    3. Gathers all databases and per-database tables.
    4. Inserts all collected data into 'e34data78'.
    5. Syncs the backend cache.
    """
    source_creds = parse_db_credentials(custom_url=source_url, target=target_name)
    storage_creds = parse_storage_credentials(custom_storage_url=storage_url)

    s_host = source_creds["host"]
    s_port = source_creds["port"]
    s_user = source_creds["user"]
    s_pwd = source_creds["password"]
    s_admin_db = source_creds["admin_db"]
    cluster_title = source_creds["name"]
    cluster_env = source_creds["environment"]

    t_host = storage_creds["host"]
    t_port = storage_creds["port"]
    t_db = storage_creds["storage_db"]

    print("=" * 85)
    print(f" DATABASE AUDIT & DATA INGESTION ENGINE -> {t_db} ".center(85, "="))
    print(f" Source Cluster: {cluster_title} ({s_host}:{s_port}) ".center(85, " "))
    print(f" Target Storage: {t_db} on {t_host}:{t_port} ".center(85, " "))
    print("=" * 85)

    # 1. Ensure storage DB and schema are ready
    ensure_target_db_and_schema(storage_creds)

    # 2. Connect to the cluster via admin_db to collect instance-wide metrics
    print(f"\n[*] Connecting to source cluster '{cluster_title}' via '{s_admin_db}' on {s_host}:{s_port}...")
    root_con = get_pg_connection(s_user, s_pwd, s_host, s_port, s_admin_db)

    audit_timestamp = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        # Version & Uptime
        ver_info = root_con.run("""
            SELECT 
                version(),
                current_setting('server_version'),
                pg_postmaster_start_time(),
                (now() - pg_postmaster_start_time())::text
        """)[0]
        full_version = ver_info[0]
        engine_version = ver_info[1]
        postmaster_start = ver_info[2]
        uptime = ver_info[3]

        # Total Cluster Storage
        st_row = root_con.run("""
            SELECT 
                pg_size_pretty(sum(pg_database_size(datname))), 
                sum(pg_database_size(datname))::bigint 
            FROM pg_database;
        """)[0]
        total_storage_pretty = st_row[0]
        total_storage_bytes = st_row[1] or 0

        # Cache Hit Ratio
        cache_row = root_con.run("""
            SELECT round(sum(blks_hit)*100.0/nullif(sum(blks_hit + blks_read),0), 2) 
            FROM pg_stat_database;
        """)[0]
        cache_hit_pct = float(cache_row[0]) if cache_row[0] is not None else None

        # Connection Stats
        conn_stats = root_con.run("""
            SELECT 
                (SELECT count(*) FROM pg_stat_activity) AS current_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') AS idle_in_tx,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed,
                ROUND(
                    ((SELECT count(*)::numeric FROM pg_stat_activity) / 
                     (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2
                ) AS usage_pct;
        """)[0]
        curr_conns, active_conns, idle_conns, idle_tx, max_conns, conn_usage_pct = conn_stats

        # CPU Query Activity
        act_row = root_con.run("""
            SELECT 
                count(*) FILTER (WHERE state = 'active' AND pid != pg_backend_pid()),
                count(*) FILTER (WHERE wait_event_type = 'IO'),
                count(*) FILTER (WHERE wait_event_type = 'Lock')
            FROM pg_stat_activity;
        """)[0]
        cpu_computing, io_waiting, lock_waiting = act_row

        # Roles / Users
        roles_rows = root_con.run("""
            SELECT 
                r.rolname, 
                r.rolsuper, 
                r.rolcanlogin, 
                r.rolconnlimit,
                ARRAY(
                    SELECT b.rolname 
                    FROM pg_auth_members m 
                    JOIN pg_roles b ON (m.roleid = b.oid) 
                    WHERE m.member = r.oid
                )::text AS member_of
            FROM pg_roles r
            ORDER BY r.rolcanlogin DESC, r.rolname ASC;
        """)

        # Cluster Settings (Memory, Worker Limits, Network)
        mem_settings = root_con.run("""
            SELECT 'memory' AS category, name, setting, unit, source, short_desc 
            FROM pg_settings 
            WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'temp_buffers');
        """)
        worker_settings = root_con.run("""
            SELECT 'worker_limit' AS category, name, setting, unit, source, short_desc 
            FROM pg_settings 
            WHERE name IN ('max_worker_processes', 'max_parallel_workers', 'max_parallel_workers_per_gather', 'autovacuum_max_workers');
        """)
        net_settings = root_con.run("""
            SELECT 'network' AS category, name, setting, unit, source, short_desc 
            FROM pg_settings 
            WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers', 'ssl_min_protocol_version');
        """)
        postmaster_settings = root_con.run("""
            SELECT 'postmaster' AS category, name, setting, unit, source, short_desc 
            FROM pg_settings 
            WHERE context = 'postmaster';
        """)

        # Discover all databases across the instance
        db_catalog_rows = root_con.run("""
            SELECT 
                datname, 
                datistemplate,
                pg_size_pretty(pg_database_size(datname)) AS size_pretty,
                pg_database_size(datname)::bigint AS size_bytes,
                pg_encoding_to_char(encoding) AS encoding, 
                datcollate
            FROM pg_database
            ORDER BY pg_database_size(datname) DESC;
        """)

        # Per-database connection distribution
        per_db_conns_data = root_con.run("""
            SELECT 
                datname,
                count(*) AS total_conns,
                count(*) FILTER (WHERE state = 'active') AS active,
                count(*) FILTER (WHERE state = 'idle') AS idle,
                count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
            FROM pg_stat_activity
            WHERE datname IS NOT NULL
            GROUP BY datname;
        """)
        conns_by_db = {r[0]: {"total": r[1], "active": r[2], "idle": r[3], "idle_in_tx": r[4]} for r in per_db_conns_data}

    finally:
        root_con.close()

    print(f"[✓] Instance-level metrics gathered: Engine {engine_version}, {len(db_catalog_rows)} databases discovered.")

    # 3. Connect to target storage DB (e34data78) to record Audit Session
    print(f"\n[*] Storing audit session metadata in '{t_db}' on {t_host}:{t_port}...")
    store_con = get_pg_connection(storage_creds["user"], storage_creds["password"], t_host, t_port, t_db)

    try:
        summary_payload = json.dumps({
            "total_databases": len(db_catalog_rows),
            "databases_list": [r[0] for r in db_catalog_rows],
            "total_storage": total_storage_pretty,
            "cache_hit_pct": cache_hit_pct,
            "current_connections": curr_conns,
            "max_connections": max_conns,
            "environment": cluster_env,
            "cluster_name": cluster_title,
        })

        insert_audit_q = """
            INSERT INTO db_instance_audits (
                audit_timestamp, host, port, engine_version, full_version,
                postmaster_started_at, uptime, total_databases_count,
                total_cluster_storage_pretty, total_cluster_storage_bytes,
                cache_hit_ratio_pct, current_connections, active_connections,
                idle_connections, idle_in_transaction, max_connections,
                connection_usage_pct, cpu_computing_queries, io_waiting_queries,
                lock_waiting_queries, raw_json_summary, environment_profile, instance_name
            ) VALUES (
                :ts, :host, :port, :eng_ver, :full_ver,
                :started, :uptime, :total_dbs,
                :st_pretty, :st_bytes,
                :cache_hit, :c_conns, :act_conns,
                :idle_conns, :idle_tx, :max_conns,
                :conn_usage, :cpu_comp, :io_wait,
                :lock_wait, :summary, :env_prof, :inst_name
            ) RETURNING id;
        """
        audit_id = store_con.run(
            insert_audit_q,
            ts=audit_timestamp,
            host=s_host,
            port=s_port,
            eng_ver=engine_version,
            full_ver=full_version,
            started=postmaster_start,
            uptime=uptime,
            total_dbs=len(db_catalog_rows),
            st_pretty=total_storage_pretty,
            st_bytes=total_storage_bytes,
            cache_hit=cache_hit_pct,
            c_conns=curr_conns,
            act_conns=active_conns,
            idle_conns=idle_conns,
            idle_tx=idle_tx,
            max_conns=max_conns,
            conn_usage=float(conn_usage_pct) if conn_usage_pct is not None else None,
            cpu_comp=cpu_computing,
            io_wait=io_waiting,
            lock_wait=lock_waiting,
            summary=summary_payload,
            env_prof=cluster_env,
            inst_name=cluster_title
        )[0][0]

        print(f"[✓] Created master audit session record: ID = #{audit_id}")

        # B. Insert Roles/Users into db_cluster_users
        for u in roles_rows:
            store_con.run("""
                INSERT INTO db_cluster_users (
                    audit_id, username, is_superuser, can_login, conn_limit, granted_roles, recorded_at
                ) VALUES (
                    :aid, :uname, :super, :login, :lim, :roles, :rec_at
                );
            """, aid=audit_id, uname=u[0], super=u[1], login=u[2], lim=u[3], roles=u[4], rec_at=audit_timestamp)

        # C. Insert Settings into db_cluster_settings
        all_settings = mem_settings + worker_settings + net_settings + postmaster_settings
        for s in all_settings:
            store_con.run("""
                INSERT INTO db_cluster_settings (
                    audit_id, category, setting_name, setting_value, unit, source, short_desc, recorded_at
                ) VALUES (
                    :aid, :cat, :name, :val, :unit, :src, :desc, :rec_at
                );
            """, aid=audit_id, cat=s[0], name=s[1], val=s[2], unit=s[3], src=s[4], desc=s[5], rec_at=audit_timestamp)

        print(f"[✓] Stored cluster users ({len(roles_rows)}) and system configurations in '{t_db}'.")

        # 4. Process Every Database on the Cluster
        print("\n" + "=" * 85)
        print(f" INSPECTING ALL {len(db_catalog_rows)} DATABASES & INSERTING TABLES TO {t_db} ".center(85, "="))
        print("=" * 85)

        total_tables_inserted = 0
        total_queries_inserted = 0

        for db_row in db_catalog_rows:
            db_name = db_row[0]
            is_template = bool(db_row[1])
            size_pretty = db_row[2]
            size_bytes = int(db_row[3] or 0)
            encoding = db_row[4]
            collation = db_row[5]

            c_info = conns_by_db.get(db_name, {"total": 0, "active": 0, "idle": 0, "idle_in_tx": 0})

            # Check if template DB
            if is_template:
                status = "SKIPPED_TEMPLATE"
                error_msg = "Skipped template database"
                cat_id = store_con.run("""
                    INSERT INTO db_database_catalog (
                        audit_id, database_name, is_template, disk_size_pretty, disk_size_bytes,
                        encoding, db_collation, total_connections, active_connections, idle_connections,
                        idle_in_transaction, user_tables_count, user_views_count, user_indexes_count,
                        inspection_status, inspection_error, recorded_at
                    ) VALUES (
                        :aid, :dbname, :tmpl, :sz_p, :sz_b, :enc, :col, :t_c, :a_c, :i_c, :itx_c,
                        0, 0, 0, :status, :err, :rec_at
                    ) RETURNING id;
                """, aid=audit_id, dbname=db_name, tmpl=True, sz_p=size_pretty, sz_b=size_bytes, enc=encoding, col=collation,
                     t_c=c_info["total"], a_c=c_info["active"], i_c=c_info["idle"], itx_c=c_info["idle_in_tx"],
                     status=status, err=error_msg, rec_at=audit_timestamp)[0][0]
                print(f"  [-] {db_name:<30} | {size_pretty:<10} | Template DB (Skipped)")
                continue

            # Connect to this individual database to collect detailed table & schema information
            user_tables_count = 0
            user_views_count = 0
            user_indexes_count = 0
            inspection_status = "SUCCESS"
            inspection_error = None
            db_tables_list = []
            db_active_queries = []

            try:
                db_con = get_pg_connection(s_user, s_pwd, s_host, s_port, db_name, timeout=8)
                try:
                    # User tables, views, indexes count
                    counts_row = db_con.run("""
                        SELECT 
                            (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_tables,
                            (SELECT count(*) FROM information_schema.views WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_views,
                            (SELECT count(*) FROM pg_stat_user_indexes) AS user_indexes;
                    """)[0]
                    user_tables_count = counts_row[0]
                    user_views_count = counts_row[1]
                    user_indexes_count = counts_row[2]

                    # Detailed list of all user tables with physical sizes and rows
                    db_tables_list = db_con.run("""
                        SELECT 
                            schemaname,
                            relname AS table_name,
                            (schemaname || '.' || relname) AS full_table_name,
                            pg_size_pretty(pg_total_relation_size(relid)) AS total_size_pretty,
                            pg_total_relation_size(relid)::bigint AS total_size_bytes,
                            pg_size_pretty(pg_relation_size(relid)) AS table_size_pretty,
                            pg_relation_size(relid)::bigint AS table_size_bytes,
                            pg_size_pretty(pg_indexes_size(relid)) AS index_size_pretty,
                            pg_indexes_size(relid)::bigint AS index_size_bytes,
                            COALESCE(n_live_tup, 0)::bigint AS estimated_rows,
                            COALESCE(seq_scan, 0)::bigint AS seq_scan,
                            COALESCE(idx_scan, 0)::bigint AS idx_scan,
                            COALESCE(n_dead_tup, 0)::bigint AS n_dead_tup,
                            last_vacuum,
                            last_autovacuum,
                            last_analyze
                        FROM pg_stat_user_tables
                        ORDER BY pg_total_relation_size(relid) DESC;
                    """)

                    # Active in-flight queries on this database
                    db_active_queries = db_con.run("""
                        SELECT 
                            pid, usename, client_addr::text, state,
                            ROUND(EXTRACT(EPOCH FROM (now() - query_start))::numeric, 2) AS duration_seconds,
                            to_char(now() - query_start, 'HH24:MI:SS') AS duration_formatted,
                            wait_event_type, wait_event,
                            left(query, 300) AS query_preview
                        FROM pg_stat_activity
                        WHERE datname = current_database() 
                          AND state != 'idle' 
                          AND pid != pg_backend_pid()
                        ORDER BY query_start ASC;
                    """)

                finally:
                    db_con.close()

            except Exception as e:
                inspection_status = "FAILED"
                inspection_error = str(e)

            # Insert Catalog Entry into e34data78
            cat_id = store_con.run("""
                INSERT INTO db_database_catalog (
                    audit_id, database_name, is_template, disk_size_pretty, disk_size_bytes,
                    encoding, db_collation, total_connections, active_connections, idle_connections,
                    idle_in_transaction, user_tables_count, user_views_count, user_indexes_count,
                    inspection_status, inspection_error, recorded_at
                ) VALUES (
                    :aid, :dbname, :tmpl, :sz_p, :sz_b, :enc, :col, :t_c, :a_c, :i_c, :itx_c,
                    :u_tbls, :u_views, :u_idxs, :status, :err, :rec_at
                ) RETURNING id;
            """, aid=audit_id, dbname=db_name, tmpl=False, sz_p=size_pretty, sz_b=size_bytes, enc=encoding, col=collation,
                 t_c=c_info["total"], a_c=c_info["active"], i_c=c_info["idle"], itx_c=c_info["idle_in_tx"],
                 u_tbls=user_tables_count, u_views=user_views_count, u_idxs=user_indexes_count,
                 status=inspection_status, err=inspection_error, rec_at=audit_timestamp)[0][0]

            # Insert Tables into e34data78
            for t in db_tables_list:
                store_con.run("""
                    INSERT INTO db_database_tables (
                        database_catalog_id, audit_id, database_name, schema_name, table_name,
                        full_table_name, total_size_pretty, total_size_bytes, table_size_pretty,
                        table_size_bytes, index_size_pretty, index_size_bytes, estimated_rows,
                        seq_scan, idx_scan, n_dead_tup, last_vacuum, last_autovacuum, last_analyze, recorded_at
                    ) VALUES (
                        :cid, :aid, :dbname, :sname, :tname, :fname, :tot_p, :tot_b,
                        :tbl_p, :tbl_b, :idx_p, :idx_b, :rows, :seq, :idx, :dead,
                        :vac, :autovac, :anl, :rec_at
                    );
                """, cid=cat_id, aid=audit_id, dbname=db_name, sname=t[0], tname=t[1], fname=t[2],
                     tot_p=t[3], tot_b=t[4], tbl_p=t[5], tbl_b=t[6], idx_p=t[7], idx_b=t[8],
                     rows=t[9], seq=t[10], idx=t[11], dead=t[12], vac=t[13], autovac=t[14], anl=t[15],
                     rec_at=audit_timestamp)
                total_tables_inserted += 1

            # Insert Active In-flight Queries into e34data78
            for q in db_active_queries:
                store_con.run("""
                    INSERT INTO db_database_active_queries (
                        audit_id, database_name, pid, username, client_addr, state,
                        duration_seconds, duration_formatted, wait_event_type, wait_event,
                        query_preview, recorded_at
                    ) VALUES (
                        :aid, :dbname, :pid, :uname, :addr, :state, :dur_s, :dur_f,
                        :w_type, :w_ev, :preview, :rec_at
                    );
                """, aid=audit_id, dbname=db_name, pid=q[0], uname=q[1], addr=q[2], state=q[3],
                     dur_s=q[4], dur_f=q[5], w_type=q[6], w_ev=q[7], preview=q[8], rec_at=audit_timestamp)
                total_queries_inserted += 1

            status_icon = "✓" if inspection_status == "SUCCESS" else "!"
            print(f"  [{status_icon}] {db_name:<30} | {size_pretty:<10} | Tables: {len(db_tables_list):<4} | Views: {user_views_count:<3} | Stored into {t_db}")

        print("=" * 85)

        # 5. Query verification from e34data78
        verification_summary = store_con.run("""
            SELECT 
                (SELECT count(*) FROM db_database_catalog WHERE audit_id = :aid) AS total_dbs,
                (SELECT count(*) FROM db_database_tables WHERE audit_id = :aid) AS total_tables,
                (SELECT count(*) FROM db_cluster_users WHERE audit_id = :aid) AS total_users,
                (SELECT count(*) FROM db_cluster_settings WHERE audit_id = :aid) AS total_settings;
        """, aid=audit_id)[0]

        # 6. Insert / Update infra_instances table with constraint & compare-update
        infra_action = "SKIPPED"
        try:
            cluster_top_tables = store_con.run("""
                SELECT schema_name, database_name, table_name, total_size_pretty, table_size_pretty, index_size_pretty, estimated_rows, n_dead_tup
                FROM db_database_tables
                WHERE audit_id = :aid
                ORDER BY total_size_bytes DESC LIMIT 15;
            """, aid=audit_id)

            db_top_tables = store_con.run("""
                SELECT database_name, table_name, total_size_pretty, table_size_pretty, index_size_pretty, estimated_rows, n_dead_tup
                FROM db_database_tables
                WHERE audit_id = :aid
                ORDER BY total_size_bytes DESC;
            """, aid=audit_id)

            databases_payload = []
            for db_row in db_catalog_rows:
                d_name = db_row[0]
                d_size = db_row[2]
                d_enc = db_row[4] or "UTF8"
                d_coll = db_row[5] or "en_US.UTF-8"
                top_t = [
                    {
                        "name": t[1],
                        "totalSize": t[2],
                        "dataSize": t[3],
                        "indexSize": t[4],
                        "liveRows": int(t[5] or 0),
                        "deadRows": int(t[6] or 0),
                    }
                    for t in db_top_tables if t[0] == d_name
                ][:5]
                c_info = conns_by_db.get(d_name, {"total": 0})
                databases_payload.append({
                    "name": d_name,
                    "owner": "postgres",
                    "size": d_size,
                    "encoding": d_enc,
                    "collation": d_coll,
                    "connectionLimit": -1,
                    "currentConnections": c_info.get("total", 0),
                    "tablesCount": len(top_t),
                    "schemasCount": 1,
                    "topTables": top_t,
                })

            inst_id, display_name, short_name, env_name = get_rds_instance_identity(s_host, cluster_env, cluster_title)

            rds_payload = {
                "id": inst_id,
                "kind": "rds",
                "name": display_name,
                "shortName": short_name,
                "environment": env_name,
                "region": "ap-south-1 / ap-south-1a",
                "status": "warning" if (conn_usage_pct and float(conn_usage_pct) > 80.0) else "healthy",
                "instanceType": "db.r6g.xlarge",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "rdsEndpoint": f"{s_host}:{s_port}",
                "rdsDefaultDb": s_admin_db or "postgres",
                "rdsUser": s_user,
                "rdsEngineVersion": engine_version,
                "rdsUptime": uptime,
                "rdsStartTime": postmaster_start.strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(postmaster_start, (datetime.datetime, datetime.date)) else str(postmaster_start or ""),
                "totalDatabases": len(db_catalog_rows),
                "totalStorageUsed": total_storage_pretty,
                "databases": databases_payload,
                "connectionSummary": {
                    "currentConnections": curr_conns,
                    "clusterMax": max_conns,
                    "superuserReserved": 3,
                    "usablePool": max(0, max_conns - 3),
                    "usagePct": float(conn_usage_pct) if conn_usage_pct is not None else 0.0,
                },
                "memorySettings": [
                    {"parameter": r[1], "value": r[2], "description": r[5] or ""}
                    for r in mem_settings
                ],
                "cacheHitRatio": cache_hit_pct,
                "cpuState": {
                    "totalBackends": curr_conns,
                    "cpuComputing": cpu_computing,
                    "idleSessions": idle_conns,
                    "idleInTx": idle_tx,
                    "ioWaiting": io_waiting,
                    "lockWaiting": lock_waiting,
                },
                "dbUsers": [
                    {
                        "username": u[0],
                        "isSuperuser": bool(u[1]),
                        "inherits": True,
                        "canCreateRoles": False,
                        "canCreateDb": False,
                        "canLogin": bool(u[2]),
                        "memberOf": u[4] or "",
                    }
                    for u in roles_rows
                ],
                "topTables": [
                    {
                        "schema": t[0],
                        "name": f"{t[1]}.{t[2]}",
                        "totalSize": t[3],
                        "dataSize": t[4],
                        "indexSize": t[5],
                        "liveRows": int(t[6] or 0),
                        "deadRows": int(t[7] or 0),
                    }
                    for t in cluster_top_tables
                ],
                "networkSettings": [
                    {"name": r[1], "value": r[2], "description": r[5] or ""}
                    for r in net_settings
                ],
            }

            infra_action = upsert_infra_instance_db(store_con, inst_id, "rds", rds_payload)
        except Exception as e:
            print(f"{YELLOW}Warning: Failed to upsert infra_instances for {cluster_title}: {e}{RESET}")

        # 7. Automated 10-day retention cleanup
        try:
            retention_days = int(os.getenv("AUDIT_RETENTION_DAYS", "10"))
            cleanup_old_db_audits(store_con, days=retention_days)
        except Exception as e:
            print(f"{YELLOW}[Retention] Warning: DB audit retention cleanup failed: {e}{RESET}")

    finally:
        store_con.close()

    result = {
        "status": "SUCCESS",
        "audit_id": audit_id,
        "storage_database": t_db,
        "instance_host": f"{s_host}:{s_port}",
        "environment": cluster_env,
        "cluster_name": cluster_title,
        "engine_version": engine_version,
        "total_databases_recorded": verification_summary[0],
        "total_tables_stored": verification_summary[1],
        "total_users_stored": verification_summary[2],
        "total_settings_stored": verification_summary[3],
        "total_cluster_storage": total_storage_pretty,
        "infra_instances_action": infra_action,
    }

    # Save timestamped JSON artifact for reference
    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"db_audit_{cluster_env}_{ts_str}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n{BOLD}{GREEN}[✓] ALL INFORMATION STORED SUCCESSFULLY INTO DATABASE: '{t_db}'{RESET}")
    print(print_table([
        ["Audit Session ID", f"#{audit_id}"],
        ["Target Storage DB", t_db],
        ["Cluster Host", f"{s_host}:{s_port}"],
        ["Environment Profile", f"{cluster_env} ({cluster_title})"],
        ["Engine Version", engine_version],
        ["Total Databases Audited", verification_summary[0]],
        ["Total User Tables Stored", verification_summary[1]],
        ["Cluster Roles Stored", verification_summary[2]],
        ["Cluster Settings Stored", verification_summary[3]],
        ["Total Storage Across All DBs", total_storage_pretty],
        ["infra_instances Table Action", infra_action],
        ["Local JSON Summary", os.path.abspath(json_filename)]
    ], headers=["Audit Metric", "Persisted Value"]))

    # 6. Trigger backend live sync if backend is running
    try:
        req = urllib.request.Request("http://127.0.0.1:3001/api/instances/sync", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print(f"  {GREEN}✓ Backend cache synchronized at http://127.0.0.1:3001/api/instances{RESET}")
    except Exception:
        pass

    return result


def audit_both_instances(storage_url: Optional[str] = None):
    """Audits both UAT and Dev clusters sequentially and stores everything in e34data78."""
    print(f"\n{BOLD}{CYAN}╔{'═' * 80}╗{RESET}")
    print(f"{BOLD}{CYAN}║  DISCOVERING & INGESTING ALL DATABASES (UAT + DEV) INTO e34data78            ║{RESET}")
    print(f"{BOLD}{CYAN}╚{'═' * 80}╝{RESET}\n")

    res_uat = execute_discovery_and_store(target_name="uat", storage_url=storage_url)
    print("\n" + "#" * 85 + "\n")
    res_dev = execute_discovery_and_store(target_name="dev", storage_url=storage_url)

    print(f"\n{BOLD}{CYAN}╔{'═' * 80}╗{RESET}")
    print(f"{BOLD}{CYAN}║  BOTH DATABASE CLUSTERS SUCCESSFULLY AUDITED AND PERSISTED                  ║{RESET}")
    print(f"{BOLD}{CYAN}╚{'═' * 80}╝{RESET}\n")
    print(f"  • UAT Cluster (34.100.237.205): #{res_uat['audit_id']} ({res_uat['total_databases_recorded']} DBs, {res_uat['total_tables_stored']} tables)")
    print(f"  • Dev Cluster (34.93.217.164):  #{res_dev['audit_id']} ({res_dev['total_databases_recorded']} DBs, {res_dev['total_tables_stored']} tables)")
    print(f"  • Target Central Warehouse:      e34data78 on 34.100.237.205:5432\n")


def audit_all_four_instances(storage_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Audits all four database clusters (UAT, Dev, Production, Old Production) and stores into e34data78."""
    print(f"\n{BOLD}{CYAN}╔{'═' * 80}╗{RESET}")
    print(f"{BOLD}{CYAN}║  DISCOVERING & INGESTING ALL FOUR DATABASE CLUSTERS INTO e34data78          ║{RESET}")
    print(f"{BOLD}{CYAN}╚{'═' * 80}╝{RESET}\n")

    targets = ["uat", "dev", "prod", "old_prod"]
    results = []
    for tgt in targets:
        cluster_info = CLUSTERS_REGISTRY[tgt]
        print(f"\n{BOLD}{YELLOW}>>> Processing [{cluster_info['name']}] ({tgt})...{RESET}")
        try:
            res = execute_discovery_and_store(target_name=tgt, storage_url=storage_url)
            results.append(res)
        except Exception as e:
            err_msg = str(e)
            print(f"{RED}[✗] Failed to audit {cluster_info['name']}: {err_msg}{RESET}")
            if "timeout" in err_msg.lower() or "source_address is none" in err_msg.lower():
                print(f"  {YELLOW}ℹ Note: AWS RDS endpoints require network access from inside the AWS VPC/EC2 instance.{RESET}")
            results.append({
                "target": tgt,
                "status": "FAILED",
                "error": err_msg,
                "cluster_name": cluster_info["name"]
            })

    print(f"\n{BOLD}{CYAN}╔{'═' * 80}╗{RESET}")
    print(f"{BOLD}{CYAN}║  ALL FOUR DATABASE CLUSTERS AUDIT EXECUTION FINISHED                        ║{RESET}")
    print(f"{BOLD}{CYAN}╚{'═' * 80}╝{RESET}\n")
    for r in results:
        status_sym = f"{GREEN}✓ SUCCESS{RESET}" if r.get("status") == "SUCCESS" else f"{RED}✗ FAILED{RESET}"
        if r.get("status") == "SUCCESS":
            print(f"  • {r.get('cluster_name', 'Unknown')}: {status_sym} (Audit #{r.get('audit_id')}, {r.get('total_databases_recorded')} DBs, {r.get('total_tables_stored')} tables)")
        else:
            print(f"  • {r.get('cluster_name', 'Unknown')}: {status_sym} - {r.get('error')}")
    print(f"\n  • Target Central Warehouse: e34data78 on 34.100.237.205:5432\n")
    return results


# ==============================================================================
# CLI DISPATCHER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Multi-Database Discovery & Insertion Engine for e34data78")
    parser.add_argument("target", nargs="?", default=None, help="Target cluster: uat, dev, prod, old_prod, both, four, or all")
    parser.add_argument("--uat", action="store_true", help="Audit UAT PostgreSQL instance (34.100.237.205)")
    parser.add_argument("--dev", action="store_true", help="Audit Dev PostgreSQL instance (34.93.217.164)")
    parser.add_argument("--prod", "--production", action="store_true", help="Audit Production RDS instance (bettrlabs-mp-prod)")
    parser.add_argument("--old-prod", "--old-production", "--live-past", action="store_true", help="Audit Old Production RDS instance (bettrlabsprod)")
    parser.add_argument("--both", action="store_true", help="Audit BOTH UAT and Dev database instances")
    parser.add_argument("--four", "--all", action="store_true", help="Audit ALL FOUR database clusters (UAT, Dev, Prod, Old Prod)")
    parser.add_argument("--url", help="Database connection URL to audit", default=None)
    parser.add_argument("--storage-url", help="Central storage database URL (default: e34data78 on 34.100.237.205)", default=None)
    parser.add_argument("--target-db", help="Target storage database name (default: e34data78)", default="e34data78")
    parser.add_argument("--cleanup", type=int, nargs="?", const=10, default=None, help="Prune database cluster audits older than N days (default: 10)")
    parser.add_argument("--dry-run-cleanup", action="store_true", help="Report records older than retention period without deleting")
    parser.add_argument("--host", help="PostgreSQL host IP/hostname", default=None)
    parser.add_argument("--port", help="PostgreSQL port (default 5432)", type=int, default=None)
    parser.add_argument("--user", help="PostgreSQL username", default=None)
    parser.add_argument("--password", help="PostgreSQL password", default=None)
    
    args = parser.parse_args()

    if args.target_db:
        os.environ["TARGET_STORAGE_DB"] = args.target_db
    if args.host:
        os.environ["DB_HOST"] = args.host
    if args.port:
        os.environ["DB_PORT"] = str(args.port)
    if args.user:
        os.environ["DB_USER"] = args.user
    if args.password:
        os.environ["DB_PWD"] = args.password

    # Standalone cleanup trigger
    if args.cleanup is not None or args.dry_run_cleanup:
        days = args.cleanup if args.cleanup is not None else int(os.getenv("AUDIT_RETENTION_DAYS", "10"))
        storage_creds = parse_storage_credentials(custom_storage_url=args.storage_url)
        store_con = get_pg_connection(
            storage_creds["user"], storage_creds["password"],
            storage_creds["host"], storage_creds["port"], storage_creds["storage_db"]
        )
        try:
            pruned = cleanup_old_db_audits(store_con, days=days, dry_run=args.dry_run_cleanup)
            action_desc = "would be pruned" if args.dry_run_cleanup else "pruned"
            print(f"[i] Retention check completed: {pruned} database cluster audit sessions {action_desc} (threshold: {days} days).")
        finally:
            store_con.close()
        return

    # Check target
    target = (args.target or "").strip().lower()
    canonical_target = CLUSTER_ALIASES.get(target, target)

    if args.four or canonical_target in ("all", "four", "all_four"):
        audit_all_four_instances(storage_url=args.storage_url)
    elif args.both or canonical_target in ("both", "dev_uat"):
        audit_both_instances(storage_url=args.storage_url)
    elif args.uat or canonical_target == "uat":
        execute_discovery_and_store(target_name="uat", storage_url=args.storage_url)
    elif args.dev or canonical_target == "dev":
        execute_discovery_and_store(target_name="dev", storage_url=args.storage_url)
    elif args.prod or canonical_target == "prod":
        execute_discovery_and_store(target_name="prod", storage_url=args.storage_url)
    elif args.old_prod or canonical_target == "old_prod":
        execute_discovery_and_store(target_name="old_prod", storage_url=args.storage_url)
    elif args.url:
        execute_discovery_and_store(custom_url=args.url, storage_url=args.storage_url)
    elif canonical_target in CLUSTERS_REGISTRY:
        execute_discovery_and_store(target_name=canonical_target, storage_url=args.storage_url)
    else:
        # Default fallback: run all four
        audit_all_four_instances(storage_url=args.storage_url)


if __name__ == "__main__":
    main()
