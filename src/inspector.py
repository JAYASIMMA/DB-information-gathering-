import os
import sys
import json
import argparse
import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from tabulate import tabulate

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

# ==============================================================================
# AWS RDS INSTANCE HARDWARE SPECIFICATIONS DATABASE
# ==============================================================================
RDS_INSTANCE_SPECS: Dict[str, Dict[str, Any]] = {
    # T4g (Graviton2)
    "db.t4g.micro": {"vcpus": 2, "ram_gb": 1.0},
    "db.t4g.small": {"vcpus": 2, "ram_gb": 2.0},
    "db.t4g.medium": {"vcpus": 2, "ram_gb": 4.0},
    "db.t4g.large": {"vcpus": 2, "ram_gb": 8.0},
    "db.t4g.xlarge": {"vcpus": 4, "ram_gb": 16.0},
    "db.t4g.2xlarge": {"vcpus": 8, "ram_gb": 32.0},
    # T3 (Intel)
    "db.t3.micro": {"vcpus": 2, "ram_gb": 1.0},
    "db.t3.small": {"vcpus": 2, "ram_gb": 2.0},
    "db.t3.medium": {"vcpus": 2, "ram_gb": 4.0},
    "db.t3.large": {"vcpus": 2, "ram_gb": 8.0},
    "db.t3.xlarge": {"vcpus": 4, "ram_gb": 16.0},
    "db.t3.2xlarge": {"vcpus": 8, "ram_gb": 32.0},
    # M6g (Graviton2)
    "db.m6g.large": {"vcpus": 2, "ram_gb": 8.0},
    "db.m6g.xlarge": {"vcpus": 4, "ram_gb": 16.0},
    "db.m6g.2xlarge": {"vcpus": 8, "ram_gb": 32.0},
    "db.m6g.4xlarge": {"vcpus": 16, "ram_gb": 64.0},
    "db.m6g.8xlarge": {"vcpus": 32, "ram_gb": 128.0},
    "db.m6g.12xlarge": {"vcpus": 48, "ram_gb": 192.0},
    "db.m6g.16xlarge": {"vcpus": 64, "ram_gb": 256.0},
    # M5 (Intel)
    "db.m5.large": {"vcpus": 2, "ram_gb": 8.0},
    "db.m5.xlarge": {"vcpus": 4, "ram_gb": 16.0},
    "db.m5.2xlarge": {"vcpus": 8, "ram_gb": 32.0},
    "db.m5.4xlarge": {"vcpus": 16, "ram_gb": 64.0},
    # R6g (Memory-Optimized Graviton2)
    "db.r6g.large": {"vcpus": 2, "ram_gb": 16.0},
    "db.r6g.xlarge": {"vcpus": 4, "ram_gb": 16.0},
    "db.r6g.2xlarge": {"vcpus": 8, "ram_gb": 64.0},
    "db.r6g.4xlarge": {"vcpus": 16, "ram_gb": 128.0},
    # R5 (Memory-Optimized Intel)
    "db.r5.large": {"vcpus": 2, "ram_gb": 16.0},
    "db.r5.xlarge": {"vcpus": 4, "ram_gb": 32.0},
    "db.r5.2xlarge": {"vcpus": 8, "ram_gb": 64.0},
}


def get_instance_class_specs(instance_class: Optional[str]) -> Dict[str, Any]:
    if not instance_class:
        return {"vcpus": "Unknown", "ram_gb": None, "label": "Unknown"}
    cls_key = instance_class.strip().lower()
    if cls_key in RDS_INSTANCE_SPECS:
        s = RDS_INSTANCE_SPECS[cls_key]
        return {
            "vcpus": s["vcpus"],
            "ram_gb": s["ram_gb"],
            "label": f"{instance_class} ({s['vcpus']} vCPUs, {s['ram_gb']} GB RAM)",
        }
    return {
        "vcpus": "N/A",
        "ram_gb": None,
        "label": instance_class,
    }


# ==============================================================================
# AWS RDS & AURORA INFRASTRUCTURE & CLOUDWATCH COLLECTOR (via boto3)
# ==============================================================================

def audit_aws_rds_infra(db_identifier: str, region_name: str = "ap-south-1") -> Dict[str, Any]:
    """
    Audits AWS RDS / Aurora infrastructure configurations:
    - Real-time CPU Utilization, Freeable RAM, Free/Allocated Storage (via CloudWatch)
    - Engine & OS maintenance/patch updates
    - Network security groups and open ports
    - Database parameter groups (startup command equivalents)
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        return {"error": "boto3 library is required. Install via `uv add boto3`"}

    rds = boto3.client("rds", region_name=region_name)
    ec2 = boto3.client("ec2", region_name=region_name)

    results: Dict[str, Any] = {
        "db_identifier": db_identifier,
        "region": region_name,
        "instance_info": {},
        "hardware_metrics": {},
        "os_and_patches": {},
        "network_and_ports": {},
        "startup_parameters": {},
    }

    try:
        instances = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)
        if not instances["DBInstances"]:
            return {"error": f"No DB instance found with identifier: {db_identifier}"}
        db = instances["DBInstances"][0]
    except (NoCredentialsError, ClientError) as e:
        return {"error": f"AWS ClientError: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

    # 1. Instance & Engine
    engine = db.get("Engine")
    engine_ver = db.get("EngineVersion")
    endpoint = db.get("Endpoint", {})
    inst_class = db.get("DBInstanceClass")
    specs = get_instance_class_specs(inst_class)
    allocated_gb = db.get("AllocatedStorage")
    storage_type = db.get("StorageType", "gp3")
    max_allocated_gb = db.get("MaxAllocatedStorage")

    results["instance_info"] = {
        "DBInstanceIdentifier": db.get("DBInstanceIdentifier"),
        "DBClusterIdentifier": db.get("DBClusterIdentifier", "N/A (Standard RDS)"),
        "DBInstanceClass": specs.get("label", inst_class),
        "Engine": engine,
        "EngineVersion": engine_ver,
        "Status": db.get("DBInstanceStatus"),
        "MultiAZ": db.get("MultiAZ"),
        "StorageType": storage_type,
        "AllocatedStorage": f"{allocated_gb} GB",
        "MaxAllocatedStorage": f"{max_allocated_gb} GB" if max_allocated_gb else "N/A",
    }

    # 1.1 Real-time Hardware Metrics (CloudWatch)
    hw_metrics: Dict[str, Any] = {
        "instance_class": inst_class,
        "instance_class_specs": specs,
        "allocated_storage_gb": allocated_gb,
        "storage_type": storage_type,
        "max_allocated_storage_gb": max_allocated_gb,
    }
    try:
        cw = boto3.client("cloudwatch", region_name=region_name)
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(minutes=15)
        metric_names = ["CPUUtilization", "FreeableMemory", "FreeStorageSpace", "ReadIOPS", "WriteIOPS"]
        for m_name in metric_names:
            try:
                res = cw.get_metric_statistics(
                    Namespace="AWS/RDS",
                    MetricName=m_name,
                    Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_identifier}],
                    StartTime=start,
                    EndTime=now,
                    Period=300,
                    Statistics=["Average", "Maximum"],
                )
                datapoints = res.get("Datapoints", [])
                if datapoints:
                    datapoints.sort(key=lambda x: x["Timestamp"], reverse=True)
                    latest = datapoints[0]
                    hw_metrics[m_name] = {
                        "Average": latest.get("Average"),
                        "Maximum": latest.get("Maximum"),
                    }
            except Exception:
                pass

        if "CPUUtilization" in hw_metrics:
            hw_metrics["cpu_avg_pct"] = round(hw_metrics["CPUUtilization"]["Average"], 2)
            hw_metrics["cpu_max_pct"] = round(hw_metrics["CPUUtilization"]["Maximum"], 2)

        if "FreeableMemory" in hw_metrics:
            free_bytes = hw_metrics["FreeableMemory"]["Average"]
            hw_metrics["freeable_ram_gb"] = round(free_bytes / (1024**3), 2)
            hw_metrics["freeable_ram_mb"] = round(free_bytes / (1024**2), 1)
            total_ram = specs.get("ram_gb")
            if total_ram:
                used_ram = total_ram - hw_metrics["freeable_ram_gb"]
                hw_metrics["used_ram_gb"] = round(max(0.0, used_ram), 2)
                hw_metrics["ram_usage_pct"] = round((used_ram / total_ram) * 100, 1)

        if "FreeStorageSpace" in hw_metrics:
            free_st_bytes = hw_metrics["FreeStorageSpace"]["Average"]
            hw_metrics["free_storage_gb"] = round(free_st_bytes / (1024**3), 2)
            if allocated_gb:
                used_st = allocated_gb - hw_metrics["free_storage_gb"]
                hw_metrics["used_storage_gb"] = round(max(0.0, used_st), 2)
                hw_metrics["storage_usage_pct"] = round((used_st / allocated_gb) * 100, 1)

        if "ReadIOPS" in hw_metrics and "WriteIOPS" in hw_metrics:
            hw_metrics["read_iops"] = round(hw_metrics["ReadIOPS"]["Average"], 1)
            hw_metrics["write_iops"] = round(hw_metrics["WriteIOPS"]["Average"], 1)
    except Exception as e:
        hw_metrics["cw_error"] = str(e)

    results["hardware_metrics"] = hw_metrics

    # 2. OS Versions & Patch / Maintenance Details
    maint_window = db.get("PreferredMaintenanceWindow")
    auto_minor_upgrade = db.get("AutoMinorVersionUpgrade")
    pending_modified = db.get("PendingModifiedValues", {})

    pending_actions_list = []
    try:
        pending_actions = rds.describe_pending_maintenance_actions(
            ResourceIdentifier=db.get("DBInstanceArn")
        )
        for res in pending_actions.get("PendingMaintenanceActions", []):
            for action in res.get("PendingUpdateDetails", []):
                pending_actions_list.append({
                    "Action": action.get("Action"),
                    "AutoAppliedAfterDate": str(action.get("AutoAppliedAfterDate", "N/A")),
                    "OptInStatus": action.get("OptInStatus"),
                    "Description": action.get("Description"),
                })
    except ClientError:
        pass

    results["os_and_patches"] = {
        "EngineVersion": engine_ver,
        "AutoMinorVersionUpgrade": auto_minor_upgrade,
        "PreferredMaintenanceWindow": maint_window,
        "PendingModifiedValues": pending_modified,
        "PendingMaintenanceActions": pending_actions_list or "No pending OS/Engine patches",
    }

    # 3. Ports & Open Security Group Ingress Rules
    port = endpoint.get("Port")
    publicly_accessible = db.get("PubliclyAccessible", False)
    vpc_sg_ids = [sg["VpcSecurityGroupId"] for sg in db.get("VpcSecurityGroups", [])]

    sg_rules_list = []
    if vpc_sg_ids:
        try:
            sgs = ec2.describe_security_groups(GroupIds=vpc_sg_ids)
            for sg in sgs.get("SecurityGroups", []):
                sg_id = sg.get("GroupId")
                for perm in sg.get("IpPermissions", []):
                    from_port = perm.get("FromPort", "All")
                    to_port = perm.get("ToPort", "All")
                    ip_proto = perm.get("IpProtocol", "All")
                    cidrs = [ip.get("CidrIp") for ip in perm.get("IpRanges", []) if ip.get("CidrIp")]
                    ipv6_cidrs = [ip.get("CidrIpv6") for ip in perm.get("Ipv6Ranges", []) if ip.get("CidrIpv6")]
                    sources = cidrs + ipv6_cidrs
                    sg_rules_list.append({
                        "SecurityGroupId": sg_id,
                        "Protocol": ip_proto,
                        "PortRange": f"{from_port}-{to_port}" if from_port != to_port else str(from_port),
                        "AllowedSources": ", ".join(sources) if sources else "Security Group Reference",
                    })
        except ClientError as e:
            sg_rules_list.append({"Error": f"Failed to fetch SG rules: {str(e)}"})

    results["network_and_ports"] = {
        "Endpoint": endpoint.get("Address"),
        "Port": port,
        "PubliclyAccessible": publicly_accessible,
        "VpcSecurityGroups": vpc_sg_ids,
        "OpenIngressRules": sg_rules_list,
    }

    # 4. Parameter Groups (Startup Command Equivalent)
    pg_names = [pg["DBParameterGroupName"] for pg in db.get("DBParameterGroups", [])]
    user_modified_params = []
    for pg_name in pg_names:
        try:
            paginator = rds.get_paginator("describe_db_parameters")
            for page in paginator.paginate(DBParameterGroupName=pg_name, Source="user"):
                for p in page.get("Parameters", []):
                    user_modified_params.append({
                        "ParameterGroup": pg_name,
                        "ParameterName": p.get("ParameterName"),
                        "Value": p.get("ParameterValue"),
                        "ApplyType": p.get("ApplyType"),
                        "DataType": p.get("DataType"),
                    })
        except ClientError:
            pass

    results["startup_parameters"] = {
        "AttachedParameterGroups": pg_names,
        "CustomModifiedParameters": user_modified_params or "All default RDS parameters (no user overrides)",
    }

    return results


# ==============================================================================
# DATABASE ENGINE COLLECTORS (via Direct SQL Connection)
# ==============================================================================

def audit_postgresql(
    host: str,
    port: int,
    user: str,
    password: str,
    dbname: str,
    inspect_all_databases: bool = True
) -> Dict[str, Any]:
    """
    Audits PostgreSQL database instance:
    1. Cluster-wide databases list, total storage sizes, connections, users/roles
    2. Engine hardware allocation (shared_buffers, effective_cache_size, tablespaces)
    3. Buffer cache hit ratio & active CPU computing queries
    4. Multi-database inspection: iterates through each non-template database
    5. Version and compile info
    6. Configured port and SSL settings
    7. Workers running (pg_stat_activity backend types, worker limits)
    8. Postmaster startup settings
    """
    try:
        import pg8000.native
    except ImportError:
        return {"error": "pg8000 is required. Install via `uv add pg8000`"}

    report: Dict[str, Any] = {}
    try:
        con = pg8000.native.Connection(
            user=user,
            password=password,
            host=host,
            port=port,
            database=dbname,
            ssl_context=True,
            timeout=10,
        )
    except Exception as e:
        return {"error": f"Failed to connect to PostgreSQL ({host}:{port}/{dbname}): {str(e)}"}

    all_db_names = []
    try:
        # Hardware Metrics: Engine Storage, Memory, Cache Hit & CPU Queries
        st_row = con.run("""
            SELECT pg_size_pretty(sum(pg_database_size(datname))), sum(pg_database_size(datname))
            FROM pg_database
            WHERE datistemplate = false;
        """)[0]
        ts_rows = con.run("SELECT spcname, pg_size_pretty(pg_tablespace_size(spcname)) FROM pg_tablespace;")
        mem_rows = con.run("""
            SELECT name, setting, unit, short_desc 
            FROM pg_settings 
            WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'temp_buffers');
        """)
        cache_row = con.run("""
            SELECT round(sum(blks_hit)*100.0/nullif(sum(blks_hit + blks_read),0), 2)
            FROM pg_stat_database;
        """)[0]
        act_rows = con.run("""
            SELECT 
                count(*) AS total_backends,
                count(*) FILTER (WHERE state = 'active' AND pid != pg_backend_pid()) AS cpu_computing_queries,
                count(*) FILTER (WHERE wait_event_type = 'IO') AS io_waiting,
                count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting,
                count(*) FILTER (WHERE state = 'idle') AS idle_sessions
            FROM pg_stat_activity;
        """)[0]
        report["hardware_metrics"] = {
            "total_database_storage_used": st_row[0],
            "total_database_storage_bytes": int(st_row[1] or 0),
            "tablespaces": [{"tablespace": r[0], "size": r[1]} for r in ts_rows],
            "memory_settings": {r[0]: f"{r[1]} {r[2] or ''}".strip() for r in mem_rows},
            "cache_hit_ratio_pct": float(cache_row[0]) if cache_row[0] is not None else None,
            "activity_breakdown": {
                "total_backends": act_rows[0],
                "cpu_computing_queries": act_rows[1],
                "io_waiting": act_rows[2],
                "lock_waiting": act_rows[3],
                "idle_sessions": act_rows[4],
            }
        }

        # 1. Databases across the entire RDS Cluster
        db_rows = con.run("""
            SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size,
                   pg_encoding_to_char(encoding) AS encoding, datcollate
            FROM pg_database
            WHERE datistemplate = false
            ORDER BY pg_database_size(datname) DESC;
        """)
        report["databases"] = [
            {"database_name": r[0], "size": r[1], "encoding": r[2], "collation": r[3]}
            for r in db_rows
        ]
        report["total_databases_count"] = len(db_rows)
        all_db_names = [r[0] for r in db_rows]

        # 1.1 Connections (Cluster-wide & per-database)
        conn_rows = con.run("""
            SELECT 
                (SELECT count(*) FROM pg_stat_activity) AS current_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle_connections,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') AS idle_in_tx,
                (SELECT setting FROM pg_settings WHERE name = 'max_connections') AS max_connections;
        """)
        c = conn_rows[0]
        report["connections"] = {
            "current_connections": c[0],
            "active_connections": c[1],
            "idle_connections": c[2],
            "idle_in_transaction": c[3],
            "max_allowed_connections": c[4],
        }

        # Connections by Database
        per_db_conn_rows = con.run("""
            SELECT COALESCE(datname, '[Cluster Worker]') AS database_name,
                   count(*) AS total_conns,
                   count(*) FILTER (WHERE state = 'active') AS active_conns,
                   count(*) FILTER (WHERE state = 'idle') AS idle_conns
            FROM pg_stat_activity
            GROUP BY datname
            ORDER BY total_conns DESC;
        """)
        report["connections_per_database"] = [
            {"database_name": r[0], "total_connections": r[1], "active": r[2], "idle": r[3]}
            for r in per_db_conn_rows
        ]

        # 1.2 Users / Roles (Global cluster catalog)
        user_rows = con.run("""
            SELECT rolname, rolsuper, rolcanlogin, rolconnlimit 
            FROM pg_roles 
            ORDER BY rolcanlogin DESC, rolname ASC;
        """)
        report["users"] = [
            {"username": r[0], "is_superuser": r[1], "can_login": r[2], "conn_limit": r[3]}
            for r in user_rows
        ]

        # 2. Version & Compile OS
        ver_rows = con.run("SELECT version(), current_setting('server_version');")
        report["version_info"] = {
            "full_version": ver_rows[0][0],
            "server_version": ver_rows[0][1],
        }

        # 3. Ports & SSL
        port_rows = con.run("""
            SELECT name, setting 
            FROM pg_settings 
            WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers');
        """)
        report["network"] = {r[0]: r[1] for r in port_rows}

        # 4. Workers Running
        worker_rows = con.run("""
            SELECT backend_type, count(*) 
            FROM pg_stat_activity 
            GROUP BY backend_type 
            ORDER BY count(*) DESC;
        """)
        report["active_workers"] = [{"backend_type": r[0], "count": r[1]} for r in worker_rows]

        worker_limits = con.run("""
            SELECT name, setting, unit 
            FROM pg_settings 
            WHERE name IN ('max_worker_processes', 'max_parallel_workers', 'autovacuum_max_workers');
        """)
        report["worker_limits"] = {r[0]: f"{r[1]} {r[2] or ''}".strip() for r in worker_limits}

        # 5. Startup Settings (Context = postmaster)
        startup_rows = con.run("""
            SELECT name, setting, source 
            FROM pg_settings 
            WHERE context = 'postmaster' 
            ORDER BY name;
        """)
        report["startup_postmaster_settings"] = [
            {"name": r[0], "value": r[1], "source": r[2]}
            for r in startup_rows
        ]

    finally:
        con.close()

    # Multi-Database Schema & Table Inspection
    if inspect_all_databases and all_db_names:
        per_database_details = []
        for target_db in all_db_names:
            if target_db in ("template0", "template1"):
                continue
            db_detail = {"database": target_db, "status": "ok"}
            try:
                db_conn = pg8000.native.Connection(
                    user=user,
                    password=password,
                    host=host,
                    port=port,
                    database=target_db,
                    ssl_context=True,
                    timeout=5,
                )
                try:
                    tbl_count = db_conn.run("""
                        SELECT count(*) 
                        FROM information_schema.tables 
                        WHERE table_schema NOT IN ('pg_catalog', 'information_schema');
                    """)[0][0]
                    schema_rows = db_conn.run("""
                        SELECT schema_name 
                        FROM information_schema.schemata 
                        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast');
                    """)
                    db_detail["user_table_count"] = tbl_count
                    db_detail["user_schemas"] = [s[0] for s in schema_rows]
                finally:
                    db_conn.close()
            except Exception as e:
                db_detail["status"] = f"error: {str(e)}"
            per_database_details.append(db_detail)
        report["per_database_inspection"] = per_database_details

    return report


def audit_mysql(host: str, port: int, user: str, password: str, dbname: str) -> Dict[str, Any]:
    """Audits MySQL / Aurora MySQL database instance."""
    try:
        import pymysql
    except ImportError:
        return {"error": "pymysql is required. Install via `uv add pymysql`"}

    report: Dict[str, Any] = {}
    try:
        con = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=dbname or None,
            connect_timeout=10,
        )
    except Exception as e:
        return {"error": f"Failed to connect to MySQL: {str(e)}"}

    try:
        with con.cursor() as cur:
            # 1. Databases
            cur.execute("""
                SELECT table_schema, ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
                FROM information_schema.tables
                GROUP BY table_schema
                ORDER BY size_mb DESC;
            """)
            db_rows = cur.fetchall()
            report["databases"] = [{"name": r[0], "size_mb": float(r[1] or 0)} for r in db_rows]
            report["total_databases_count"] = len(db_rows)

            # Connections
            cur.execute("SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Threads_running', 'Max_used_connections');")
            status_map = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute("SHOW VARIABLES LIKE 'max_connections';")
            var_map = {r[0]: r[1] for r in cur.fetchall()}

            report["connections"] = {
                "current_connections": status_map.get("Threads_connected"),
                "active_connections": status_map.get("Threads_running"),
                "max_used_connections": status_map.get("Max_used_connections"),
                "max_allowed_connections": var_map.get("max_connections"),
            }

            # Users
            cur.execute("SELECT user, host, account_locked FROM mysql.user ORDER BY user;")
            report["users"] = [{"username": r[0], "host": r[1], "locked": r[2]} for r in cur.fetchall()]

            # 2. Version
            cur.execute("SELECT VERSION(), @@version_comment, @@version_compile_os;")
            v = cur.fetchone()
            report["version_info"] = {
                "version": v[0],
                "comment": v[1],
                "os": v[2],
            }

            # 3. Network Ports
            cur.execute("SHOW VARIABLES WHERE Variable_name IN ('port', 'bind_address', 'have_ssl');")
            report["network"] = {r[0]: r[1] for r in cur.fetchall()}

            # 4. Workers / Processlist
            cur.execute("SHOW GLOBAL STATUS LIKE 'Threads_%';")
            report["thread_workers"] = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("SELECT command, count(*) FROM information_schema.processlist GROUP BY command;")
            report["active_workers"] = [{"command": r[0], "count": r[1]} for r in cur.fetchall()]

            # 5. Startup / Variable config
            cur.execute("""
                SELECT VARIABLE_NAME, VARIABLE_VALUE, VARIABLE_SOURCE
                FROM performance_schema.variables_info
                WHERE VARIABLE_SOURCE NOT IN ('COMPILED', 'DYNAMIC')
                LIMIT 50;
            """)
            report["startup_variables"] = [
                {"name": r[0], "value": r[1], "source": r[2]} for r in cur.fetchall()
            ]
    finally:
        con.close()

    return report


# ==============================================================================
# REPORT FORMATTER
# ==============================================================================

def format_pretty_report(aws_info: Dict[str, Any], db_info: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(" AWS RDS / AURORA DATABASE INFRASTRUCTURE AUDIT REPORT ".center(80, "="))
    lines.append("=" * 80)

    # 1. AWS INFRASTRUCTURE
    if aws_info and "error" not in aws_info:
        lines.append("\n[+] 1. AWS RDS / Aurora Instance Specifications")
        inst_table = [[k, v] for k, v in aws_info.get("instance_info", {}).items()]
        lines.append(tabulate(inst_table, headers=["Property", "Value"], tablefmt="rounded_grid"))

        lines.append("\n[+] 2. OS Version & Maintenance / Patch Details")
        os_info = aws_info.get("os_and_patches", {})
        lines.append(f"  * Engine Version            : {os_info.get('EngineVersion')}")
        lines.append(f"  * Auto Minor Version Upgrade: {os_info.get('AutoMinorVersionUpgrade')}")
        lines.append(f"  * Maintenance Window        : {os_info.get('PreferredMaintenanceWindow')}")
        pending = os_info.get("PendingMaintenanceActions")
        if isinstance(pending, list) and pending:
            lines.append("  * Pending Maintenance Actions:")
            lines.append(tabulate(pending, headers="keys", tablefmt="simple"))
        else:
            lines.append(f"  * Pending Maintenance Actions: {pending}")

        lines.append("\n[+] 3. Open Network Ports & Security Groups")
        net = aws_info.get("network_and_ports", {})
        lines.append(f"  * Endpoint: {net.get('Endpoint')}:{net.get('Port')}")
        lines.append(f"  * Publicly Accessible: {net.get('PubliclyAccessible')}")
        sg_rules = net.get("OpenIngressRules", [])
        if sg_rules:
            lines.append(tabulate(sg_rules, headers="keys", tablefmt="rounded_grid"))

        lines.append("\n[+] 5. DB Parameter Group (Startup Command Flags)")
        params = aws_info.get("startup_parameters", {})
        lines.append(f"  * Attached Parameter Groups: {params.get('AttachedParameterGroups')}")
        custom_params = params.get("CustomModifiedParameters")
        if isinstance(custom_params, list):
            lines.append(tabulate(custom_params[:20], headers="keys", tablefmt="simple"))
            if len(custom_params) > 20:
                lines.append(f"  (... and {len(custom_params) - 20} more custom parameters)")
        else:
            lines.append(f"  * Custom Parameters: {custom_params}")
    elif aws_info and "error" in aws_info:
        lines.append(f"\n[!] AWS Infra Fetch Note: {aws_info['error']}")

    # 2. HARDWARE METRICS: CPU USAGE, STORAGE & RAM USAGE
    hw_aws = aws_info.get("hardware_metrics", {}) if (aws_info and "error" not in aws_info) else {}
    hw_sql = db_info.get("hardware_metrics", {}) if (db_info and "error" not in db_info) else {}

    if hw_aws or hw_sql:
        lines.append("\n" + "-" * 80)
        lines.append(" INSTANCE HARDWARE METRICS: CPU USAGE, STORAGE & RAM USAGE ".center(80, "-"))
        lines.append("-" * 80)

        if hw_aws:
            lines.append("\n[+] AWS CloudWatch Real-Time Host Metrics")
            host_rows = []
            if "instance_class_specs" in hw_aws:
                host_rows.append(["Instance Class", hw_aws["instance_class_specs"].get("label", hw_aws.get("instance_class", "N/A"))])
            if "allocated_storage_gb" in hw_aws:
                host_rows.append(["Allocated EBS Storage", f"{hw_aws['allocated_storage_gb']} GB ({hw_aws.get('storage_type', 'gp3')})"])
            if "free_storage_gb" in hw_aws:
                host_rows.append(["Free Storage Space (EBS)", f"{hw_aws['free_storage_gb']} GB remaining"])
            if "used_storage_gb" in hw_aws:
                host_rows.append(["EBS Storage Used", f"{hw_aws['used_storage_gb']} GB ({hw_aws.get('storage_usage_pct', 'N/A')}%)"])
            if "cpu_avg_pct" in hw_aws:
                host_rows.append(["CPU Utilization (Host)", f"Average: {hw_aws['cpu_avg_pct']}% | Peak: {hw_aws.get('cpu_max_pct', 'N/A')}%"])
            if "instance_class_specs" in hw_aws and hw_aws["instance_class_specs"].get("ram_gb"):
                host_rows.append(["Total RAM Capacity", f"{hw_aws['instance_class_specs']['ram_gb']:.2f} GB"])
            if "freeable_ram_gb" in hw_aws:
                host_rows.append(["Freeable RAM (Host)", f"{hw_aws['freeable_ram_gb']} GB ({hw_aws.get('freeable_ram_mb', 'N/A')} MB freeable)"])
            if "used_ram_gb" in hw_aws:
                host_rows.append(["Host RAM Usage (Estimated)", f"{hw_aws['used_ram_gb']} GB ({hw_aws.get('ram_usage_pct', 'N/A')}%)"])
            if "read_iops" in hw_aws and "write_iops" in hw_aws:
                host_rows.append(["Disk IOPS", f"Read: {hw_aws['read_iops']} IOPS | Write: {hw_aws['write_iops']} IOPS"])
            if host_rows:
                lines.append(tabulate(host_rows, headers=["Host Hardware Metric", "Measured Value"], tablefmt="rounded_grid"))

        if hw_sql:
            if "total_database_storage_used" in hw_sql:
                lines.append("\n[+] Database Engine Storage Allocation")
                lines.append(f"  * Total Storage Consumed Across All Databases: {hw_sql['total_database_storage_used']}")
                if "tablespaces" in hw_sql:
                    ts_rows = [[t["tablespace"], t["size"]] for t in hw_sql["tablespaces"]]
                    lines.append(tabulate(ts_rows, headers=["Tablespace Name", "Disk Space Used"], tablefmt="rounded_grid"))

            if "memory_settings" in hw_sql:
                lines.append("\n[+] Database RAM Allocation & Cache Performance")
                mem_table = [[k, v] for k, v in hw_sql["memory_settings"].items()]
                lines.append(tabulate(mem_table, headers=["Memory Parameter", "Allocated RAM"], tablefmt="rounded_grid"))
                if hw_sql.get("cache_hit_ratio_pct") is not None:
                    lines.append(f"  * Buffer Cache Hit Ratio: {hw_sql['cache_hit_ratio_pct']}% (RAM Cache Efficiency - healthy is >99%)")

            if "activity_breakdown" in hw_sql:
                act = hw_sql["activity_breakdown"]
                lines.append("\n[+] Database Query Activity & CPU Load Breakdown")
                act_rows = [[act.get("total_backends"), act.get("cpu_computing_queries"), act.get("io_waiting"), act.get("lock_waiting"), act.get("idle_sessions")]]
                lines.append(tabulate(act_rows, headers=["Total Backends", "Active CPU Queries", "I/O Waiting", "Lock Waiting", "Idle Sessions"], tablefmt="rounded_grid"))

    # 3. DATABASE ENGINE AUDIT
    if db_info and "error" not in db_info:
        lines.append("\n" + "-" * 80)
        lines.append(" DATABASE ENGINE INTERNAL METRICS ".center(80, "-"))
        lines.append("-" * 80)

        # Databases
        lines.append(f"\n[+] 1. Databases in RDS Instance (Total: {db_info.get('total_databases_count')})")
        if "databases" in db_info:
            lines.append(tabulate(db_info["databases"], headers="keys", tablefmt="simple"))

        # Multi-database inspection
        if "per_database_inspection" in db_info:
            lines.append("\n[+] 1.1 Multi-Database Schema & User Table Inspection:")
            lines.append(tabulate(db_info["per_database_inspection"], headers="keys", tablefmt="simple"))

        # Connections
        lines.append("\n[+] Connections Summary")
        if "connections" in db_info:
            c = db_info["connections"]
            conn_table = [[k, v] for k, v in c.items()]
            lines.append(tabulate(conn_table, headers=["Metric", "Value"], tablefmt="simple"))

        # Connections by Database
        if "connections_per_database" in db_info:
            lines.append("\n[+] Connections Breakdown by Database:")
            lines.append(tabulate(db_info["connections_per_database"], headers="keys", tablefmt="simple"))

        # Users
        lines.append(f"\n[+] Users / Roles in Cluster (Total: {len(db_info.get('users', []))})")
        if "users" in db_info:
            lines.append(tabulate(db_info["users"], headers="keys", tablefmt="simple"))

        # Version & OS
        lines.append("\n[+] 2. Engine Version & OS Architecture")
        if "version_info" in db_info:
            v_info = db_info["version_info"]
            lines.append(f"  * Full Version String: {v_info.get('full_version')}")
            lines.append(f"  * Server Version     : {v_info.get('server_version')}")

        # Open Ports / Network
        lines.append("\n[+] 3. Open Listening Ports & SSL Status")
        if "network" in db_info:
            net_table = [[k, v] for k, v in db_info["network"].items()]
            lines.append(tabulate(net_table, headers=["Parameter", "Setting"], tablefmt="simple"))

        # Workers
        lines.append("\n[+] 4. Active Worker Processes / Threads")
        if "active_workers" in db_info:
            lines.append(tabulate(db_info["active_workers"], headers="keys", tablefmt="simple"))
        if "worker_limits" in db_info:
            lines.append("  * Configured Worker Limits:")
            w_limits = [[k, v] for k, v in db_info["worker_limits"].items()]
            lines.append(tabulate(w_limits, headers=["Setting", "Configured Limit"], tablefmt="simple"))
        if "thread_workers" in db_info:
            t_threads = [[k, v] for k, v in db_info["thread_workers"].items()]
            lines.append(tabulate(t_threads, headers=["Thread Metric", "Value"], tablefmt="simple"))

        # Postmaster / Startup settings
        if "startup_postmaster_settings" in db_info:
            lines.append("\n[+] 5. Startup Postmaster Settings (Parameters loaded at instance boot)")
            lines.append(tabulate(db_info["startup_postmaster_settings"][:25], headers="keys", tablefmt="simple"))
            if len(db_info["startup_postmaster_settings"]) > 25:
                lines.append(f"  (... total {len(db_info['startup_postmaster_settings'])} postmaster settings)")
    elif db_info and "error" in db_info:
        lines.append(f"\n[!] Database Engine Fetch Note: {db_info['error']}")

    lines.append("\n" + "=" * 80 + "\n")
    return "\n".join(lines)


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Inspect AWS RDS & Aurora infrastructure and internal database metrics across all databases."
    )
    # Target preset
    parser.add_argument("--target", choices=["market", "product", "both"], default="both", help="Target instance preset (market, product, or both)")

    # AWS Infra arguments
    parser.add_argument("--db-identifier", help="AWS RDS DB instance or cluster identifier")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-south-1"), help="AWS Region (default: ap-south-1)")
    parser.add_argument("--skip-aws", action="store_true", help="Skip AWS API calls and only inspect via direct DB connection")

    # DB Connection arguments
    parser.add_argument("--database-url", help="Full PostgreSQL / MySQL connection URI")
    parser.add_argument("--engine", choices=["postgres", "mysql"], default="postgres", help="DB engine type")
    parser.add_argument("--host", help="Database host / RDS endpoint")
    parser.add_argument("--port", type=int, default=0, help="Database port")
    parser.add_argument("--user", help="Database username")
    parser.add_argument("--password", help="Database password")
    parser.add_argument("--dbname", help="Database name")
    parser.add_argument("--skip-db", action="store_true", help="Skip direct DB connection and only inspect AWS infra")
    parser.add_argument("--no-all-db", action="store_true", help="Do not iterate across all other databases in instance")

    # Output options
    parser.add_argument("--json", action="store_true", help="Output full report as JSON")
    parser.add_argument("--output-log", default="audit_output.log", help="File to write formatted log output (default: audit_output.log)")

    args = parser.parse_args()

    # If --db-identifier or --database-url is explicitly passed, treat as single target
    if args.db_identifier or args.database_url or args.host:
        if args.target == "both":
            args.target = "custom"

    if args.target == "both":
        # Run dual instance audit
        from audit_both_instances import main as run_dual_audit
        run_dual_audit()
        return

    # Single instance target resolution
    if args.target == "product":
        default_url = os.getenv("PRODUCT_DATABASE_URL")
        default_user = os.getenv("PRODUCT_DB_USER", "bl_pg_admin")
        default_pwd = os.getenv("PRODUCT_DB_PWD") or os.getenv("PRODUCT_DB_PASSWORD")
        default_host = os.getenv("PRODUCT_DB_HOST", "bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com")
        default_port = int(os.getenv("PRODUCT_DB_PORT", "5432"))
        default_dbname = os.getenv("PRODUCT_DB_NAME", "ag4good_db")
        default_instance = os.getenv("PRODUCT_DB_INSTANCE_IDENTIFIER", "bettrlabsprod")
    elif args.target == "market":
        default_url = os.getenv("MARKET_DATABASE_URL") or os.getenv("DATABASE_URL")
        default_user = os.getenv("MARKET_DB_USER") or os.getenv("DB_USER", "postgres")
        default_pwd = os.getenv("MARKET_DB_PASSWORD") or os.getenv("DB_PASSWORD")
        default_host = os.getenv("MARKET_DB_HOST") or os.getenv("DB_HOST", "bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com")
        default_port = int(os.getenv("MARKET_DB_PORT", "0") or os.getenv("DB_PORT", "0") or "5432")
        default_dbname = os.getenv("MARKET_DB_NAME") or os.getenv("DB_NAME", "bettrlabs_market_prod")
        default_instance = os.getenv("MARKET_DB_INSTANCE_IDENTIFIER") or os.getenv("DB_INSTANCE_IDENTIFIER", "bettrlabs-mp-prod")
    else:
        default_url = os.getenv("DATABASE_URL")
        default_user = os.getenv("DB_USER")
        default_pwd = os.getenv("DB_PASSWORD")
        default_host = os.getenv("DB_HOST")
        default_port = int(os.getenv("DB_PORT", "0") or "0")
        default_dbname = os.getenv("DB_NAME")
        default_instance = os.getenv("DB_INSTANCE_IDENTIFIER")

    host = args.host or default_host
    port = args.port or default_port
    user = args.user or default_user
    password = args.password or default_pwd
    dbname = args.dbname or default_dbname

    db_url = args.database_url or default_url
    if db_url:
        clean_url = db_url
        if "+asyncpg" in clean_url:
            clean_url = clean_url.replace("+asyncpg", "")
        elif "+" in clean_url.split("://")[0]:
            s = clean_url.split("://")[0].split("+")[0]
            r = clean_url.split("://")[1]
            clean_url = f"{s}://{r}"

        parsed = urlparse(clean_url)
        if parsed.scheme in ("postgres", "postgresql"):
            args.engine = "postgres"
        elif parsed.scheme in ("mysql", "mariadb"):
            args.engine = "mysql"
        user = unquote(parsed.username) if parsed.username else user
        password = unquote(parsed.password) if parsed.password else password
        host = parsed.hostname or host
        port = parsed.port or (5432 if args.engine == "postgres" else 3306)
        if parsed.path and parsed.path.lstrip("/"):
            dbname = parsed.path.lstrip("/")

    if not dbname:
        dbname = "postgres" if args.engine == "postgres" else "mysql"

    aws_result = {}
    db_result = {}

    # 1. AWS API
    if not args.skip_aws:
        identifier = args.db_identifier or default_instance or os.getenv("DB_INSTANCE_IDENTIFIER")
        if not identifier and host and ".rds.amazonaws.com" in host:
            identifier = host.split(".")[0]

        if identifier:
            print(f"[*] Querying AWS RDS API for instance '{identifier}' in region '{args.region}'...")
            aws_result = audit_aws_rds_infra(db_identifier=identifier, region_name=args.region)
        else:
            aws_result = {"error": "No --db-identifier provided and DB_INSTANCE_IDENTIFIER not set."}

    # 2. Direct DB Connection
    if not args.skip_db:
        if not host:
            host = aws_result.get("network_and_ports", {}).get("Endpoint")
        if not port:
            port = aws_result.get("network_and_ports", {}).get("Port") or (5432 if args.engine == "postgres" else 3306)

        if host and user:
            print(f"[*] Connecting to {args.engine.upper()} at {host}:{port}/{dbname} as '{user}'...")
            if args.engine == "postgres":
                db_result = audit_postgresql(
                    host=host,
                    port=port,
                    user=user,
                    password=password or "",
                    dbname=dbname,
                    inspect_all_databases=not args.no_all_db
                )
            else:
                db_result = audit_mysql(
                    host=host,
                    port=port,
                    user=user,
                    password=password or "",
                    dbname=dbname
                )
        else:
            db_result = {"error": "Missing database connection credentials (provide --database-url or --host and --user)."}

    # Generate Output
    formatted_report = format_pretty_report(aws_result, db_result)
    print(formatted_report)

    # Save to log file
    if args.output_log:
        with open(args.output_log, "w", encoding="utf-8") as f:
            f.write(formatted_report)
        print(f"[✓] Log output saved to: {args.output_log}")

    if args.json:
        json_path = args.output_log.replace(".log", ".json") if args.output_log.endswith(".log") else "audit_output.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"aws_infra": aws_result, "db_engine": db_result}, f, indent=2, default=str)
        print(f"[✓] JSON output saved to: {json_path}")


if __name__ == "__main__":
    main()
