# AWS RDS & Aurora Infrastructure Inspector

Tool to audit and inspect configuration, operating system/engine patch levels, open ports, workers, and startup settings across AWS RDS and Aurora instances (PostgreSQL & MySQL).

## Quickstart with `uv`

Ensure `uv` is installed, then run:

```bash
# 1. Copy environment variables template
cp .env.example .env

# 2. View help options
uv run main.py --help

# 3. Inspect an AWS RDS / Aurora instance (AWS API + Direct DB)
uv run main.py --db-identifier my-db-instance --region us-east-1 --engine postgres --user postgres

# 4. Or inspect using only AWS APIs (no direct DB connection needed)
uv run main.py --db-identifier my-db-instance --region us-east-1 --skip-db

# 5. Or inspect directly via SQL connection (no AWS credentials needed)
uv run main.py --skip-aws --engine postgres --host <endpoint> --port 5432 --user postgres --password <secret>
```

## Standalone SQL Scripts
If you prefer running queries directly in `psql`, `mysql`, DBeaver, or pgAdmin:
- [sql/postgres_audit.sql](file:///d:/DB%20information/sql/postgres_audit.sql)
- [sql/mysql_audit.sql](file:///d:/DB%20information/sql/mysql_audit.sql)

For agent conventions and details, see [AGENTS.md](file:///d:/DB%20information/AGENTS.md).
