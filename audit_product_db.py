#!/usr/bin/env python3
"""
Production Multi-Database Audit Script for Product DB (bettrlabsprod / ag4good_db).
Connects to AWS RDS Managed PostgreSQL instance and audits hardware performance
(CPU utilization, Free/Allocated Storage, RAM usage & cache hit ratio),
as well as all databases, connections, users, versions, ports, workers, and startup configurations.

Uses PRODUCT_DATABASE_URL or PRODUCT_DB_* environment variables from .env.
Automatically handles 'postgresql+asyncpg://' dialect URLs.
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
    print("pg8000 is required. Run with `uv run audit_product_db.py` or `pip install pg8000`")
    sys.exit(1)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def print_table(rows, headers):
    if HAS_TABULATE:
        return tabulate(rows, headers=headers, tablefmt="rounded_grid")
    lines = [" | ".join(str(h) for h in headers), "-" * 60]
    for r in rows:
        lines.append(" | ".join(str(v) for v in r))
    return "\n".join(lines)


def fetch_cloudwatch_hardware_metrics(instance_id: str, region: str = "ap-south-1"):
    """
    Fetches real-time AWS CloudWatch hardware metrics for bettrlabsprod:
    - CPUUtilization (%)
    - FreeableMemory (RAM in GB/MB)
    - FreeStorageSpace (EBS Storage in GB)
    - Read/Write IOPS
    - RDS Instance specifications (Allocated storage, instance class)
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return {"error": "boto3 library not installed"}

    metrics = {}
    try:
        rds = boto3.client("rds", region_name=region)
        try:
            db_res = rds.describe_db_instances(DBInstanceIdentifier=instance_id)
            if db_res.get("DBInstances"):
                db = db_res["DBInstances"][0]
                metrics["allocated_storage_gb"] = db.get("AllocatedStorage")
                metrics["storage_type"] = db.get("StorageType")
                metrics["instance_class"] = db.get("DBInstanceClass")
                metrics["max_allocated_storage_gb"] = db.get("MaxAllocatedStorage")
        except Exception as e:
            metrics["rds_info_note"] = str(e)

        cw = boto3.client("cloudwatch", region_name=region)
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(minutes=15)

        metric_names = ["CPUUtilization", "FreeableMemory", "FreeStorageSpace", "ReadIOPS", "WriteIOPS"]
        for m_name in metric_names:
            try:
                res = cw.get_metric_statistics(
                    Namespace="AWS/RDS",
                    MetricName=m_name,
                    Dimensions=[{"Name": "DBInstanceIdentifier", "Value": instance_id}],
                    StartTime=start,
                    EndTime=now,
                    Period=300,
                    Statistics=["Average", "Maximum"],
                )
                datapoints = res.get("Datapoints", [])
                if datapoints:
                    datapoints.sort(key=lambda x: x["Timestamp"], reverse=True)
                    latest = datapoints[0]
                    metrics[m_name] = {
                        "Average": latest.get("Average"),
                        "Maximum": latest.get("Maximum"),
                    }
            except Exception:
                pass
        return metrics
    except (NoCredentialsError, ClientError) as e:
        return {"error": f"AWS credentials/CloudWatch unavailable: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


def get_product_credentials():
    """Extracts and normalizes Product DB credentials from .env or CLI."""
    db_url = os.getenv("PRODUCT_DATABASE_URL")
    if len(sys.argv) > 1 and sys.argv[1].startswith("postgres"):
        db_url = sys.argv[1]

    user = os.getenv("PRODUCT_DB_USER", "bl_pg_admin")
    password = os.getenv("PRODUCT_DB_PWD") or os.getenv("PRODUCT_DB_PASSWORD", "")
    host = os.getenv("PRODUCT_DB_HOST", "bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com")
    port = int(os.getenv("PRODUCT_DB_PORT", "5432"))
    dbname = os.getenv("PRODUCT_DB_NAME", "ag4good_db")

    if db_url:
        normalized_url = db_url
        if "+asyncpg" in normalized_url:
            normalized_url = normalized_url.replace("+asyncpg", "")
        elif "+" in normalized_url.split("://")[0]:
            scheme = normalized_url.split("://")[0].split("+")[0]
            rest = normalized_url.split("://")[1]
            normalized_url = f"{scheme}://{rest}"

        parsed = urlparse(normalized_url)
        if parsed.username:
            user = unquote(parsed.username)
        if parsed.password:
            password = unquote(parsed.password)
        if parsed.hostname:
            host = parsed.hostname
        if parsed.port:
            port = parsed.port
        if parsed.path and parsed.path.lstrip("/"):
            dbname = parsed.path.lstrip("/")

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "dbname": dbname,
        "instance_id": os.getenv("PRODUCT_DB_INSTANCE_IDENTIFIER", "bettrlabsprod"),
        "region": os.getenv("PRODUCT_AWS_REGION", "ap-south-1"),
    }


def run_product_db_audit():
    creds = get_product_credentials()
    user = creds["user"]
    password = creds["password"]
    host = creds["host"]
    port = creds["port"]
    default_db = creds["dbname"]
    instance_id = creds["instance_id"]
    region = creds["region"]

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"product_db_audit_{timestamp}.log"
    log_lines = []

    def log(msg=""):
        print(msg)
        log_lines.append(str(msg))

    log("=" * 85)
    log(" AWS RDS PRODUCT DATABASE AUDIT REPORT (bettrlabsprod) ".center(85, "="))
    log(f" Generated  : {datetime.datetime.now().isoformat()} ".center(85, " "))
    log(f" Target Host: {host}:{port} ".center(85, " "))
    log(f" Primary DB : {default_db} | Instance: {instance_id} | User: {user} ".center(85, " "))
    log("=" * 85)

    # 1. Connect at instance level
    log(f"\n[*] Connecting to Product RDS instance at {host}:{port}/{default_db}...")
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
        log(f"\n[!] CRITICAL ERROR: Could not connect to Product DB: {e}")
        log("[!] Network Note: Managed RDS instances are typically protected in private VPC subnets.")
        log("[!] Please execute this script from an EC2 instance / Bastion within the AWS VPC using:")
        log(f"    psql -h {host} -U {user} -d {default_db}")
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
        return

    # --------------------------------------------------------------------------
    # HARDWARE RESOURCE AUDIT: CPU, STORAGE & RAM USAGE
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] HARDWARE METRICS: CPU USAGE, STORAGE & RAM USAGE (bettrlabsprod)")
    log("=" * 85)

    # A. AWS CloudWatch Metrics
    cw_metrics = fetch_cloudwatch_hardware_metrics(instance_id, region=region)
    if cw_metrics and "error" not in cw_metrics:
        log("\n--- [AWS CloudWatch Real-Time Host Metrics] ---")
        hw_rows = []
        if "instance_class" in cw_metrics:
            hw_rows.append(["Instance Class", cw_metrics.get("instance_class", "N/A")])
        if "allocated_storage_gb" in cw_metrics:
            hw_rows.append(["Allocated EBS Storage", f"{cw_metrics.get('allocated_storage_gb')} GB ({cw_metrics.get('storage_type', 'gp3')})"])
        if "CPUUtilization" in cw_metrics:
            cpu = cw_metrics["CPUUtilization"]
            hw_rows.append(["CPU Utilization (Host)", f"Average: {cpu['Average']:.2f}% | Peak: {cpu['Maximum']:.2f}%"])
        if "FreeableMemory" in cw_metrics:
            mem_bytes = cw_metrics["FreeableMemory"]["Average"]
            hw_rows.append(["Freeable RAM (Host)", f"{mem_bytes / (1024**3):.2f} GB ({mem_bytes / (1024**2):.1f} MB)"])
        if "FreeStorageSpace" in cw_metrics:
            disk_bytes = cw_metrics["FreeStorageSpace"]["Average"]
            hw_rows.append(["Free Storage Space (EBS)", f"{disk_bytes / (1024**3):.2f} GB remaining"])
        if "ReadIOPS" in cw_metrics and "WriteIOPS" in cw_metrics:
            r_iops = cw_metrics['ReadIOPS']['Average']
            w_iops = cw_metrics['WriteIOPS']['Average']
            hw_rows.append(["Disk IOPS", f"Read: {r_iops:.1f} IOPS | Write: {w_iops:.1f} IOPS"])

        log(print_table(hw_rows, headers=["Host Hardware Metric", "Measured Value"]))
    else:
        log(f"\n[*] CloudWatch Notice: {cw_metrics.get('error', 'AWS API not queried directly')}")
        log("    (Reading detailed internal database storage & memory metrics below via SQL)")

    # B. Database Engine Storage Metrics
    log("\n--- [Database Engine Storage Allocation] ---")
    total_db_storage = root_con.run("SELECT pg_size_pretty(sum(pg_database_size(datname))) FROM pg_database;")[0][0]
    log(f"  * Total Storage Consumed Across All Databases: {total_db_storage}")

    tablespace_rows = root_con.run("SELECT spcname, pg_size_pretty(pg_tablespace_size(spcname)) FROM pg_tablespace;")
    log(print_table(tablespace_rows, headers=["Tablespace Name", "Disk Space Used"]))

    # C. Database RAM Memory Settings & Cache Hit Ratio
    log("\n--- [Database RAM Allocation & Cache Performance] ---")
    mem_settings = root_con.run("""
        SELECT name, setting, unit, short_desc 
        FROM pg_settings 
        WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'temp_buffers');
    """)
    log(print_table([[r[0], f"{r[1]} {r[2] or ''}".strip(), r[3]] for r in mem_settings], headers=["Memory Parameter", "Allocated RAM", "Description"]))

    cache_hit = root_con.run("SELECT round(sum(blks_hit)*100.0/nullif(sum(blks_hit + blks_read),0), 2) FROM pg_stat_database;")[0][0]
    log(f"\n  * Buffer Cache Hit Ratio: {cache_hit}% (RAM Cache Efficiency - healthy is >99%)")

    # D. Database Active CPU Query Load
    log("\n--- [Database Query Activity & CPU Load Breakdown] ---")
    query_load = root_con.run("""
        SELECT 
            count(*) AS total_backends,
            count(*) FILTER (WHERE state = 'active' AND pid != pg_backend_pid()) AS cpu_computing_queries,
            count(*) FILTER (WHERE wait_event_type = 'IO') AS io_waiting_queries,
            count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting_queries,
            count(*) FILTER (WHERE state = 'idle') AS idle_sessions
        FROM pg_stat_activity;
    """)[0]
    log(print_table(
        [[query_load[0], query_load[1], query_load[2], query_load[3], query_load[4]]],
        headers=["Total Backends", "Active CPU Queries", "I/O Waiting", "Lock Waiting", "Idle Sessions"]
    ))

    # --------------------------------------------------------------------------
    # 1. INSTANCE CONNECTIONS
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

    # Connection breakdown by database
    log("\n[*] Connection Breakdown Across All Databases in bettrlabsprod:")
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
    # 2. INSTANCE ROLES & USERS
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 2. INSTANCE ROLES & USERS (Cluster Catalog)")
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
            )::text AS granted_roles
        FROM pg_roles r
        ORDER BY rolcanlogin DESC, rolname ASC;
    """)
    log(print_table(roles, headers=["Username", "Superuser", "Can Login", "Conn Limit", "Granted Roles"]))

    # --------------------------------------------------------------------------
    # 3. OS & ENGINE VERSIONS
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
    log(f"  * Platform & OS String: {ver_info[0]}")

    # --------------------------------------------------------------------------
    # 4. OPEN PORTS & SSL
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 4. OPEN PORTS & SSL CONFIGURATION")
    log("=" * 85)
    ports = root_con.run("""
        SELECT name, setting, short_desc 
        FROM pg_settings 
        WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers', 'ssl_min_protocol_version');
    """)
    log(print_table(ports, headers=["Parameter", "Setting", "Description"]))

    # --------------------------------------------------------------------------
    # 5. RUNNING WORKERS
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 5. RUNNING WORKERS & THREAD LIMITS")
    log("=" * 85)
    workers = root_con.run("""
        SELECT backend_type, count(*) AS running_count
        FROM pg_stat_activity
        GROUP BY backend_type
        ORDER BY running_count DESC;
    """)
    log(print_table(workers, headers=["Worker Type", "Running Count"]))

    limits = root_con.run("""
        SELECT name, setting, unit, short_desc
        FROM pg_settings
        WHERE name IN ('max_worker_processes', 'max_parallel_workers', 'max_parallel_workers_per_gather', 'autovacuum_max_workers');
    """)
    log("\n[*] Configured Capacity Limits:")
    log(print_table([[r[0], f"{r[1]} {r[2] or ''}".strip(), r[3]] for r in limits], headers=["Setting", "Value", "Description"]))

    # --------------------------------------------------------------------------
    # 6. STARTUP PARAMETERS (Postmaster Context)
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 6. STARTUP PARAMETERS (Postmaster Context / DB Parameter Group)")
    log("=" * 85)
    startup_params = root_con.run("""
        SELECT name, setting, source 
        FROM pg_settings 
        WHERE context = 'postmaster' 
        ORDER BY name;
    """)
    log(print_table(startup_params[:20], headers=["Parameter", "Value", "Source"]))
    if len(startup_params) > 20:
        log(f"  (... {len(startup_params) - 20} additional postmaster parameters)")

    # --------------------------------------------------------------------------
    # 7. MULTI-DATABASE DISCOVERY & DEEP DIVE
    # --------------------------------------------------------------------------
    log("\n" + "=" * 85)
    log("[+] 7. MULTI-DATABASE INSPECTION (Connecting to Each DB on bettrlabsprod)")
    log("=" * 85)
    all_dbs = root_con.run("""
        SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size,
               pg_encoding_to_char(encoding) AS encoding, datcollate
        FROM pg_database
        ORDER BY pg_database_size(datname) DESC;
    """)
    log(f"Discovered {len(all_dbs)} databases hosted on this RDS instance.\n")
    log(print_table(all_dbs, headers=["Database Name", "Disk Size", "Encoding", "Collate"]))

    root_con.close()

    # Iterate through every database on the Product DB instance
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

            # Table, view, index counts
            table_summary = db_con.run("""
                SELECT 
                    (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_tables,
                    (SELECT count(*) FROM information_schema.views WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_views,
                    (SELECT count(*) FROM pg_stat_user_indexes) AS user_indexes;
            """)[0]
            log(f"  * User Tables: {table_summary[0]} | Views: {table_summary[1]} | Indexes: {table_summary[2]}")

            # Top 8 largest tables in this database
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

            # In-flight active queries
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
                log("  * No active running queries on this database.")

            db_con.close()
        except Exception as e:
            log(f"  [!] Failed to connect to database '{target_db}': {str(e)}")

    log("\n" + "=" * 85)
    log(f" [✓] PRODUCT DB AUDIT COMPLETED. Log saved to: {log_filename} ".center(85, "="))
    log("=" * 85 + "\n")

    with open(log_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print(f"[✓] Full log saved locally to: {os.path.abspath(log_filename)}")


if __name__ == "__main__":
    run_product_db_audit()
