# AWS RDS & Aurora Infrastructure Inspector

Tool to audit and inspect configuration, operating system/engine patch levels, open ports, workers, and startup settings across AWS RDS and Aurora instances (PostgreSQL & MySQL).

## Quickstart with `uv`

Ensure `uv` is installed, then run:

```bash
# 1. Copy environment variables template
cp .env.example .env

# 2. View help options
uv run main.py --help

# 3. Audit BOTH instances side-by-side (Total Storage, Instance Class, CPU & RAM Usage)
uv run audit_both_instances.py
# Or:
uv run main.py --target both

# 4. Inspect an individual AWS RDS / Aurora instance
uv run main.py --target market
uv run main.py --target product

# 5. Inspect an AWS RDS / Aurora instance by identifier (AWS API + Direct DB)
uv run main.py --db-identifier my-db-instance --region ap-south-1 --engine postgres --user postgres
```

## Multi-Database Ingestion into PostgreSQL (`e34data78`)

The canonical collector audits both the Dev and UAT PostgreSQL clusters, discovers every non-template database from `pg_database`, collects cluster/database/table metadata, and stores a timestamped snapshot in the central `e34data78` database. Configure `DEV_DATABASE_URL`, `UAT_DATABASE_URL`, and `STORAGE_DATABASE_URL` in a local `.env` file using `.env.example` as the template.

```bash
# Validate configuration without opening database connections
uv run collect_dev_uat_db_info.py --dry-run

# Run both environments once
uv run collect_dev_uat_db_info.py

# Compatibility entry point
uv run audit_both_dbs.py
```

The runner continues with Dev if UAT fails (and vice versa), returns exit code `1` when either environment fails, and prevents overlapping executions with a lock file. It does not accept passwords as command-line arguments.

### Cron scheduling

On a Linux host, make the wrappers executable and install the nightly 02:00 UTC job. The installer replaces only its own marked entry and preserves other user cron jobs:

```bash
chmod 700 audit_both_dbs.sh install_db_collector_cron.sh
./install_db_collector_cron.sh
crontab -l
```

Logs are written to `logs/db-collector-cron.log`; the machine-readable summary is written to `logs/db-collector-summary.json`. Keep `.env` readable only by the account running the job (`chmod 600 .env`).

### Central Schema in `e34data78`
- `db_instance_audits`: Master audit sessions, engine version, total storage, uptime, connections, CPU/cache hit load.
- `db_cluster_users`: Cluster roles and permissions.
- `db_cluster_settings`: Postmaster and runtime configuration settings.
- `db_database_catalog`: Catalog of all databases discovered, disk sizes, table counts.
- `db_database_tables`: Every table across every database with schema, total size, index size, estimated rows, and scan stats.
- `db_database_active_queries`: In-flight queries per database during audit.

### Analytical SQL Views in `e34data78`
- `v_all_databases_summary`: Summary of all databases, disk consumption, and table counts.
- `v_largest_tables_cross_db`: Top tables ranked by disk footprint across the entire PostgreSQL cluster.

## Standalone SQL Scripts
If you prefer running queries directly in `psql`, `mysql`, DBeaver, or pgAdmin:
- [sql/init_e34data78_schema.sql](file:///d:/Github/New%20folder/DB-information-gathering-/sql/init_e34data78_schema.sql)
- [sql/postgres_audit.sql](file:///d:/Github/New%20folder/DB-information-gathering-/sql/postgres_audit.sql)
- [sql/mysql_audit.sql](file:///d:/Github/New%20folder/DB-information-gathering-/sql/mysql_audit.sql)

For agent conventions and details, see [AGENTS.md](file:///d:/Github/New%20folder/DB-information-gathering-/AGENTS.md).
