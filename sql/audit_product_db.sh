#!/usr/bin/env bash
# ==============================================================================
# audit_product_db.sh
# Production Multi-Database Audit Script for Product DB (bettrlabsprod)
#
# Designed for EC2 instance execution:
#   psql -h bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com -U bl_pg_admin -d ag4good_db
#
# Usage:
#   chmod +x sql/audit_product_db.sh
#   ./sql/audit_product_db.sh
# ==============================================================================

set -eo pipefail

# 1. Load credentials from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep 'PRODUCT_' | xargs)
fi

DB_HOST="${PRODUCT_DB_HOST:-bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com}"
DB_PORT="${PRODUCT_DB_PORT:-5432}"
DB_USER="${PRODUCT_DB_USER:-bl_pg_admin}"
DB_PWD="${PRODUCT_DB_PWD:-${PRODUCT_DB_PASSWORD:-7oRfnIND467GrxOIArQw}}"
DB_NAME="${PRODUCT_DB_NAME:-ag4good_db}"

export PGPASSWORD="$DB_PWD"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="product_db_audit_${TIMESTAMP}.log"

echo "================================================================================" | tee "$LOG_FILE"
echo " AWS RDS PRODUCT DB AUDIT (bettrlabsprod) " | tee -a "$LOG_FILE"
echo " Started at: $(date)" | tee -a "$LOG_FILE"
echo " Target: $DB_HOST:$DB_PORT | Database: $DB_NAME | User: $DB_USER" | tee -a "$LOG_FILE"
echo "================================================================================" | tee -a "$LOG_FILE"

echo -e "\n[*] 1. INSTANCE-LEVEL CONNECTIONS & ENGINE STATS..." | tee -a "$LOG_FILE"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << 'EOF' | tee -a "$LOG_FILE"
\timing off
\x off

\echo '--- [1.1] Instance Connections Summary ---'
SELECT 
    (SELECT count(*) FROM pg_stat_activity) AS current_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle_connections,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed_connections,
    ROUND(((SELECT count(*)::numeric FROM pg_stat_activity) / (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2) AS usage_percent;

\echo '--- [1.2] Connections Distribution Per Database ---'
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

echo -e "\n[*] 2. DISCOVERING ALL DATABASES ON bettrlabsprod..." | tee -a "$LOG_FILE"
DATABASES=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -A -c "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY pg_database_size(datname) DESC;")

echo "Databases discovered on instance: " | tee -a "$LOG_FILE"
echo "$DATABASES" | tee -a "$LOG_FILE"

echo -e "\n[*] 3. AUDITING EACH INDIVIDUAL DATABASE..." | tee -a "$LOG_FILE"
for DB in $DATABASES; do
    echo -e "\n================================================================================" | tee -a "$LOG_FILE"
    echo " >>> Auditing Database: $DB <<<" | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB" << EOF | tee -a "$LOG_FILE" || echo "[!] Could not query database $DB" | tee -a "$LOG_FILE"
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
echo " [✓] Product DB audit completed successfully. " | tee -a "$LOG_FILE"
echo " Log saved to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "================================================================================" | tee -a "$LOG_FILE"
