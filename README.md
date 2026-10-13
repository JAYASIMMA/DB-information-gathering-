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

## Standalone SQL Scripts
If you prefer running queries directly in `psql`, `mysql`, DBeaver, or pgAdmin:
- [sql/postgres_audit.sql](file:///d:/DB%20information/sql/postgres_audit.sql)
- [sql/mysql_audit.sql](file:///d:/DB%20information/sql/mysql_audit.sql)

For agent conventions and details, see [AGENTS.md](file:///d:/DB%20information/AGENTS.md).
