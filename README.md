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

To audit all databases on a cluster (e.g. `34.100.237.205:5432`) and persist all instance metrics, configurations, database catalogs, and every individual table across all databases into `e34data78`:

```bash
# 1. Run using .env credentials
uv run store_all_dbs_to_e34data78.py

# 2. Or pass a custom database connection string (supports standard and postgresql+asyncpg://)
uv run store_all_dbs_to_e34data78.py --url "postgresql://postgres:gvufvjfvavVASVJVAHSVDhbbvjhdUAThbBEttr@34.100.237.205:5432" --target-db e34data78
```

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
