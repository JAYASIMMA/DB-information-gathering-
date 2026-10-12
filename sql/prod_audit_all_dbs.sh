#!/usr/bin/env bash
# ==============================================================================
# prod_audit_all_dbs.sh
# Production Multi-Database Audit Script for AWS RDS PostgreSQL
#
# Requirements:
#   - psql (standard PostgreSQL client installed: apt install postgresql-client / yum install postgresql)
#
# Usage:
#   chmod +x sql/prod_audit_all_dbs.sh
#   ./sql/prod_audit_all_dbs.sh
#   # Or with explicit connection URL:
#   ./sql/prod_audit_all_dbs.sh "postgresql://postgres:password@host:5432/dbname"
# ==============================================================================

set -eo pipefail

# 1. Load credentials from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DATABASE_URL="${1:-$DATABASE_URL}"

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set."
    echo "Usage: $0 [DATABASE_URL]"
    exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="rds_production_audit_${TIMESTAMP}.log"

echo "================================================================================" | tee "$LOG_FILE"
echo " AWS RDS POSTGRESQL MULTI-DATABASE AUDIT " | tee -a "$LOG_FILE"
echo " Started at: $(date)" | tee -a "$LOG_FILE"
echo "================================================================================" | tee -a "$LOG_FILE"

# Extract base URI without the database path
BASE_URL=$(echo "$DATABASE_URL" | sed -E 's|/[^/]+$||')

echo -e "\n[*] 1. AUDITING INSTANCE-LEVEL METRICS..." | tee -a "$LOG_FILE"
psql "$DATABASE_URL" << 'EOF' | tee -a "$LOG_FILE"
\timing off
\x off

\echo '--- [1.1] Instance Connections Summary ---'
SELECT 
    (SELECT count(*) FROM pg_stat_activity) AS current_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle_connections,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed_connections,
    ROUND(((SELECT count(*)::numeric FROM pg_stat_activity) / (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2) AS usage_percent;

\echo '--- [1.2] Connection Distribution Per Database ---'
SELECT 
    COALESCE(datname, '[Cluster Worker]') AS database_name,
    count(*) AS total_conns,
    count(*) FILTER (WHERE state = 'active') AS active,
    count(*) FILTER (WHERE state = 'idle') AS idle
FROM pg_stat_activity
GROUP BY datname
ORDER BY total_conns DESC;

\echo '--- [1.3] Instance Users & Roles ---'
SELECT rolname, rolsuper, rolcanlogin, rolconnlimit FROM pg_roles ORDER BY rolcanlogin DESC, rolname;

\echo '--- [1.4] Engine Version & Uptime ---'
SELECT version(), pg_postmaster_start_time() AS instance_started;

\echo '--- [1.5] Listening Ports & SSL ---'
SELECT name, setting FROM pg_settings WHERE name IN ('port', 'listen_addresses', 'ssl');

\echo '--- [1.6] Active Worker Processes ---'
SELECT backend_type, count(*) FROM pg_stat_activity GROUP BY backend_type ORDER BY count(*) DESC;

\echo '--- [1.7] Startup Postmaster Parameters ---'
SELECT name, setting, source FROM pg_settings WHERE context = 'postmaster' LIMIT 20;
EOF

echo -e "\n[*] 2. DISCOVERING ALL DATABASES ON THE INSTANCE..." | tee -a "$LOG_FILE"
DATABASES=$(psql "$DATABASE_URL" -t -A -c "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY pg_database_size(datname) DESC;")

echo "Databases found: " | tee -a "$LOG_FILE"
echo "$DATABASES" | tee -a "$LOG_FILE"

echo -e "\n[*] 3. AUDITING EACH INDIVIDUAL DATABASE..." | tee -a "$LOG_FILE"

for DB in $DATABASES; do
    echo -e "\n================================================================================" | tee -a "$LOG_FILE"
    echo " >>> Auditing Database: $DB <<<" | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"

    TARGET_URL="${BASE_URL}/${DB}"

    psql "$TARGET_URL" << EOF | tee -a "$LOG_FILE" || echo "[!] Could not query database $DB" | tee -a "$LOG_FILE"
    \echo '--- Database Size & Table Count ---'
    SELECT 
        current_database() AS database_name,
        pg_size_pretty(pg_database_size(current_database())) AS total_size,
        (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_tables;

    \echo '--- Top Largest Tables in $DB ---'
    SELECT 
        schemaname || '.' || relname AS table_name,
        pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
        n_live_tup AS estimated_rows
    FROM pg_stat_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 10;
EOF
done

echo -e "\n================================================================================" | tee -a "$LOG_FILE"
echo " [✓] Multi-database audit completed successfully. " | tee -a "$LOG_FILE"
echo " Output saved to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "================================================================================" | tee -a "$LOG_FILE"
