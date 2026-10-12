# AGENTS.md

## Repository Overview
Audit and inspection toolkit for **AWS Aurora** and **AWS RDS** managed database instances (PostgreSQL & MySQL). Collects infrastructure-level metrics (via AWS APIs) and engine internals (via direct SQL queries).

## Toolchain & Environment
- **Package Manager**: `uv` (do not use raw `pip install`).
- **Python**: `>=3.11` (managed virtualenv at `.venv`).
- **Dependencies**: `boto3`, `pg8000`, `pymysql`, `tabulate`, `python-dotenv`.
- **Run inspector**: `uv run main.py [options]`

```bash
# Add dependency
uv add <package_name>

# Run audit using full database URL (automatically inspects ALL non-template databases)
uv run main.py --database-url "$DATABASE_URL" --output-log audit_output.log

# Run audit with AWS infrastructure + DB connection
uv run main.py --db-identifier <instance_id> --region ap-south-1 --database-url "$DATABASE_URL"

# Run audit in JSON mode (machine-readable)
uv run main.py --database-url "$DATABASE_URL" --json
```

---

## Managed AWS Database Realities (Critical Agent Context)
In AWS RDS and Aurora, standard bare-metal Linux inspection does not apply:
1. **No OS Shell / SSH**: You cannot SSH into the EC2 host to run `uname -a`, `ps aux`, or `netstat`.
2. **OS & Patch Tracking**: OS updates and patch schedules are managed by AWS. They are inspected via `boto3:rds.describe_pending_maintenance_actions` and DB engine `version()`.
3. **Open Ports**: Open ports are dictated by AWS **VPC Security Group Ingress Rules** (`ec2.describe_security_groups`) and the RDS endpoint port, not host firewall commands.
4. **Startup Command**: The equivalent of the database startup command (`/usr/bin/postgres ...` or `mysqld ...`) is the AWS **DB Parameter Group**. Runtime startup flags map to PostgreSQL `postmaster` context parameters (`pg_settings`) and MySQL non-compiled system variables.
5. **Workers**: Worker threads/processes are inspected via SQL system views (`pg_stat_activity` backend types in Postgres, `Threads_%` in MySQL).

---

## The 5 Core Collection Vectors

### 1. Database Configuration (Count, Connections, Users)
- **Postgres DB Count & Sizes**:
  ```sql
  SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datistemplate = false;
  ```
- **Postgres Connections**:
  ```sql
  SELECT count(*) AS current_conn, 
         (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn 
  FROM pg_stat_activity;
  ```
- **Postgres Users**:
  ```sql
  SELECT rolname, rolsuper, rolcanlogin, rolconnlimit FROM pg_roles;
  ```
- **MySQL DB Count & Sizes**:
  ```sql
  SELECT table_schema, ROUND(SUM(data_length + index_length)/1024/1024, 2) AS mb FROM information_schema.tables GROUP BY table_schema;
  ```
- **MySQL Connections**:
  ```sql
  SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Max_used_connections');
  SHOW VARIABLES LIKE 'max_connections';
  ```
- **MySQL Users**:
  ```sql
  SELECT user, host, account_locked FROM mysql.user;
  ```

### 2. OS Version & Patch Update Details
- **AWS API**:
  - `rds.describe_db_instances`: Returns `EngineVersion`, `AutoMinorVersionUpgrade`, `PreferredMaintenanceWindow`, `PendingModifiedValues`.
  - `rds.describe_pending_maintenance_actions`: Returns pending OS maintenance (`SYSTEM_UPDATE`), hardware patches, and engine upgrades.
- **SQL Engine Version**:
  - Postgres: `SELECT version();` (contains OS build architecture e.g. `aarch64-unknown-linux-gnu`).
  - MySQL: `SELECT VERSION(), @@version_compile_os, @@version_compile_machine;` (Aurora: `SELECT AURORA_VERSION();`).

### 3. Open Ports & Network Access
- **AWS API**:
  - Endpoint and port from `DBInstance.Endpoint.Port`.
  - Open ingress ports/CIDRs from attached `VpcSecurityGroups` via `ec2.describe_security_groups`.
- **SQL Verification**:
  - Postgres: `SELECT setting FROM pg_settings WHERE name = 'port';`
  - MySQL: `SHOW VARIABLES LIKE 'port';`

### 4. Running Workers
- **Postgres (Process-based Workers)**:
  ```sql
  -- Active worker counts grouped by type (client, autovacuum, background, checkpointer, walwriter)
  SELECT backend_type, count(*) FROM pg_stat_activity GROUP BY backend_type;
  -- Worker capacity limits
  SELECT name, setting FROM pg_settings WHERE name IN ('max_worker_processes', 'max_parallel_workers', 'autovacuum_max_workers');
  ```
- **MySQL (Thread-based Workers)**:
  ```sql
  SHOW GLOBAL STATUS LIKE 'Threads_%'; -- Threads_running, Threads_connected
  SELECT command, count(*) FROM information_schema.processlist GROUP BY command;
  ```

### 5. Startup Commands & Parameter Configuration
- **AWS API**:
  - User-modified flags in parameter group: `rds.describe_db_parameters(DBParameterGroupName=..., Source='user')`.
- **SQL Level**:
  - Postgres parameters loaded at startup (equivalent to CLI startup flags):
    ```sql
    SELECT name, setting, source FROM pg_settings WHERE context = 'postmaster';
    ```
  - MySQL startup overrides:
    ```sql
    SELECT VARIABLE_NAME, VARIABLE_VALUE, VARIABLE_SOURCE FROM performance_schema.variables_info WHERE VARIABLE_SOURCE NOT IN ('COMPILED', 'DYNAMIC');
    ```

---

## Standalone Assets in Repo
- `prod_audit_all_dbs.py`: Production-ready script iterating through every database on the RDS instance.
- `sql/prod_audit_all_dbs.sh`: Zero-dependency bash/psql script for direct execution on EC2 / CloudShell.
- `src/inspector.py`: Unified Python inspector combining AWS Boto3 + SQL drivers.
- `sql/postgres_audit.sql`: Zero-dependency SQL script runnable via `psql`, DBeaver, or pgAdmin.
- `sql/mysql_audit.sql`: Zero-dependency SQL script runnable via MySQL client.
- `.env.example`: Configuration template for credentials.
