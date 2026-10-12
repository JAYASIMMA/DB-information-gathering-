#!/usr/bin/env python3
"""
Production Multi-Database Audit Script for AWS RDS & Aurora PostgreSQL.
Designed to run in production environments (EC2, Bastion, or directly via uv/python).

Features:
- Connects at the instance level.
- Discovers all databases dynamically.
- Connects to every individual database on the instance.
- Audits connections, users, workers, startup settings, and per-database tables/sizes.
- Writes a timestamped production log file with full details.
"""

import os
import sys
import datetime
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

load_dotenv()

try:
    import pg8000.native
except ImportError:
    print("pg8000 is required. Run with `uv run prod_audit_all_dbs.py` or `pip install pg8000`")
    sys.exit(1)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def print_table(rows, headers):
    if HAS_TABULATE:
        return tabulate(rows, headers=headers, tablefmt="rounded_grid")
    # Fallback if tabulate is not installed
    lines = [" | ".join(str(h) for h in headers), "-" * 60]
    for r in rows:
        lines.append(" | ".join(str(v) for v in r))
    return "\n".join(lines)


def run_production_audit():
    # 1. Parse connection string
    db_url = os.getenv("DATABASE_URL")
    if not db_url and len(sys.argv) > 1:
        db_url = sys.argv[1]

    if not db_url:
        print("[!] ERROR: DATABASE_URL not set in .env or passed as argument.")
        print("Usage: uv run prod_audit_all_dbs.py [DATABASE_URL]")
        sys.exit(1)

    parsed = urlparse(db_url)
    user = unquote(parsed.username) if parsed.username else "postgres"
    password = unquote(parsed.password) if parsed.password else ""
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    default_db = parsed.path.lstrip("/") if parsed.path else "postgres"

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"rds_production_audit_{timestamp}.log"

    log_lines = []

    def log(msg=""):
        print(msg)
        log_lines.append(str(msg))

    log("=" * 85)
    log(f" AWS RDS MULTI-DATABASE PRODUCTION AUDIT REPORT ".center(85, "="))
    log(f" Generated: {datetime.datetime.now().isoformat()} ".center(85, " "))
    log(f" Target Host: {host}:{port} ".center(85, " "))
    log("=" * 85)

    # 2. Connect to primary database to collect cluster-wide metrics
    log(f"\n[*] Connecting to primary database '{default_db}' at {host}:{port}...")
    try:
        root_con = pg8000.native.Connection(
            user=user,
            password=password,
            host=host,
            port=port,
            database=default_db,
            ssl_context=True,
            timeout=15,
        )
    except Exception as e:
        log(f"\n[!] CRITICAL ERROR: Could not connect to instance: {e}")
        log("[!] Please ensure this script is run from a host with VPC network access to the RDS instance.")
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
        return

    # --------------------------------------------------------------------------
    # SECTION 1: INSTANCE-LEVEL CONNECTION SUMMARY
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 1. INSTANCE-LEVEL CONNECTIONS & USAGE")
    log("=" * 85)

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

    log(print_table(
        [[conn_stats[0], conn_stats[1], conn_stats[2], conn_stats[3], conn_stats[4], f"{conn_stats[5]}%"]],
        headers=["Current Conns", "Active", "Idle", "Idle in TX", "Max Allowed", "Usage %"]
    ))

    # Connection distribution across each database
    log("\n[*] Connection Distribution Across Individual Databases:")
    per_db_conns = root_con.run("""
        SELECT 
            COALESCE(datname, '[Cluster Background Worker]') AS database_name,
            count(*) AS total_conns,
            count(*) FILTER (WHERE state = 'active') AS active,
            count(*) FILTER (WHERE state = 'idle') AS idle,
            count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
        FROM pg_stat_activity
        GROUP BY datname
        ORDER BY total_conns DESC;
    """)
    log(print_table(per_db_conns, headers=["Database Name", "Total Conns", "Active", "Idle", "Idle in TX"]))

    # --------------------------------------------------------------------------
    # SECTION 2: INSTANCE-WIDE ROLES & USERS
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 2. INSTANCE ROLES & USERS (Cluster Level)")
    log("=" * 85)
    roles = root_con.run("""
        SELECT 
            rolname, 
            rolsuper AS is_superuser, 
            rolcanlogin AS can_login, 
            rolconnlimit AS conn_limit,
            ARRAY(
                SELECT b.rolname 
                FROM pg_auth_members m 
                JOIN pg_roles b ON (m.roleid = b.oid) 
                WHERE m.member = r.oid
            )::text AS member_of
        FROM pg_roles r
        ORDER BY rolcanlogin DESC, rolname ASC;
    """)
    log(print_table(roles, headers=["Username", "Superuser", "Can Login", "Conn Limit", "Granted Roles"]))

    # --------------------------------------------------------------------------
    # SECTION 3: OS VERSION, ENGINE VERSION & UPTIME
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 3. OS & ENGINE VERSION DETAILS")
    log("=" * 85)
    ver_info = root_con.run("""
        SELECT 
            version() AS full_version,
            current_setting('server_version') AS server_version,
            to_char(pg_postmaster_start_time(), 'YYYY-MM-DD HH24:MI:SS TZ') AS started_at,
            (now() - pg_postmaster_start_time())::text AS uptime;
    """)[0]
    log(f"  * Engine Version      : {ver_info[1]}")
    log(f"  * Instance Started At : {ver_info[2]} (Uptime: {ver_info[3]})")
    log(f"  * Full Platform String: {ver_info[0]}")

    # --------------------------------------------------------------------------
    # SECTION 4: OPEN PORTS & NETWORK SETTINGS
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 4. OPEN PORTS & SSL SETTINGS")
    log("=" * 85)
    ports = root_con.run("""
        SELECT name, setting, short_desc 
        FROM pg_settings 
        WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers', 'ssl_min_protocol_version');
    """)
    log(print_table(ports, headers=["Setting Name", "Configured Value", "Description"]))

    # --------------------------------------------------------------------------
    # SECTION 5: ACTIVE WORKERS & LIMITS
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 5. RUNNING WORKERS (Process Types & Limits)")
    log("=" * 85)
    workers = root_con.run("""
        SELECT backend_type, count(*) AS running_count
        FROM pg_stat_activity
        GROUP BY backend_type
        ORDER BY running_count DESC;
    """)
    log(print_table(workers, headers=["Backend Worker Type", "Running Count"]))

    limits = root_con.run("""
        SELECT name, setting, unit, short_desc
        FROM pg_settings
        WHERE name IN ('max_worker_processes', 'max_parallel_workers', 'max_parallel_workers_per_gather', 'autovacuum_max_workers');
    """)
    log("\n[*] Worker Limits Configured:")
    log(print_table([[r[0], f"{r[1]} {r[2] or ''}".strip(), r[3]] for r in limits], headers=["Limit Setting", "Value", "Description"]))

    # --------------------------------------------------------------------------
    # SECTION 6: STARTUP COMMAND FLAGS (Postmaster Context)
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 6. STARTUP PARAMETERS (Postmaster Context / RDS Parameter Group)")
    log("=" * 85)
    startup_params = root_con.run("""
        SELECT name, setting, source 
        FROM pg_settings 
        WHERE context = 'postmaster' 
        ORDER BY name;
    """)
    log(print_table(startup_params[:20], headers=["Startup Parameter", "Active Value", "Source"]))
    if len(startup_params) > 20:
        log(f"  (... {len(startup_params) - 20} additional postmaster parameters configured)")

    # --------------------------------------------------------------------------
    # SECTION 7: MULTI-DATABASE DEEP DIVE (Connecting to Every Database)
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 7. MULTI-DATABASE INSPECTION (Connecting to Each Database Individually)")
    log("=" * 85)

    all_dbs = root_con.run("""
        SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size,
               pg_encoding_to_char(encoding) AS encoding, datcollate
        FROM pg_database
        ORDER BY pg_database_size(datname) DESC;
    """)
    log(f"Discovered {len(all_dbs)} total databases on the instance.\n")
    log(print_table(all_dbs, headers=["Database Name", "Disk Size", "Encoding", "Collate"]))

    root_con.close()

    # Iterate through each database
    for db_row in all_dbs:
        target_db = db_row[0]
        db_size = db_row[1]

        log("\n" + "-" * 85)
        log(f" >>> DATABASE: {target_db} (Size: {db_size}) <<< ".center(85, "-"))
        log("-" * 85)

        if target_db in ("template0", "template1"):
            log("  [i] Skipping template database system tables.")
            continue

        try:
            db_con = pg8000.native.Connection(
                user=user,
                password=password,
                host=host,
                port=port,
                database=target_db,
                ssl_context=True,
                timeout=10,
            )

            # Table & Schema counts
            table_summary = db_con.run("""
                SELECT 
                    (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_tables,
                    (SELECT count(*) FROM information_schema.views WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_views,
                    (SELECT count(*) FROM pg_stat_user_indexes) AS user_indexes;
            """)[0]
            log(f"  * User Tables: {table_summary[0]} | Views: {table_summary[1]} | Indexes: {table_summary[2]}")

            # Top 10 largest tables in this database
            top_tables = db_con.run("""
                SELECT 
                    schemaname || '.' || relname AS table_name,
                    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                    n_live_tup AS estimated_rows
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT 8;
            """)
            if top_tables:
                log("  * Top Tables by Disk Size:")
                log(print_table(top_tables, headers=["Table Name", "Total Size (Data+Indexes)", "Estimated Rows"]))
            else:
                log("  * No user tables found in this database.")

            # Active queries on this database right now
            active_queries = db_con.run("""
                SELECT pid, usename, client_addr, state, 
                       to_char(now() - query_start, 'HH24:MI:SS') AS duration,
                       left(query, 60) AS query_preview
                FROM pg_stat_activity
                WHERE datname = current_database() AND state != 'idle' AND pid != pg_backend_pid()
                LIMIT 5;
            """)
            if active_queries:
                log("\n  * Active In-Flight Queries on this Database:")
                log(print_table(active_queries, headers=["PID", "User", "Client IP", "State", "Duration", "Query Preview"]))
            else:
                log("  * No long-running queries currently active on this database.")

            db_con.close()
        except Exception as e:
            log(f"  [!] Failed to connect to database '{target_db}': {str(e)}")

    log("\n" + "=" * 85)
    log(f" [✓] AUDIT COMPLETED SUCCESSFULLY. Written to: {log_filename} ".center(85, "="))
    log("=" * 85 + "\n")

    # Save to file
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print(f"\n[✓] Full log saved locally to: {os.path.abspath(log_filename)}")


if __name__ == "__main__":
    run_production_audit()
