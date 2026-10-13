#!/usr/bin/env bash
# ==============================================================================
# audit_both_instances.sh
# Production Hardware & Resource Audit Script for BOTH AWS RDS PostgreSQL Instances
#
# Audits:
#   1. Marketplace RDS (bettrlabs-mp-prod)
#   2. Core Product DB (bettrlabsprod)
#
# Hardware metrics collected via direct SQL:
#   - Total Database Engine Storage Consumed (pg_database_size sum)
#   - Tablespace allocations (pg_tablespace_size)
#   - Database RAM Memory parameters (shared_buffers, work_mem, effective_cache_size)
#   - Buffer Cache Hit Ratio (RAM cache efficiency %)
#   - Active CPU computing queries vs IO waiting vs Idle backends
#   - Connection counts and limits
#
# Usage:
#   chmod +x sql/audit_both_instances.sh
#   ./sql/audit_both_instances.sh
# ==============================================================================

set -eo pipefail

# 1. Load credentials from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="dual_instance_audit_${TIMESTAMP}.log"

echo "================================================================================" | tee "$LOG_FILE"
echo " AWS RDS DUAL INSTANCE HARDWARE AUDIT (STORAGE, CPU LOAD & RAM SETTINGS) " | tee -a "$LOG_FILE"
echo " Started at: $(date)" | tee -a "$LOG_FILE"
echo "================================================================================" | tee -a "$LOG_FILE"

# Function to audit a single PostgreSQL instance
audit_instance() {
    local INSTANCE_NAME="$1"
    local DB_HOST="$2"
    local DB_PORT="$3"
    local DB_USER="$4"
    local DB_PWD="$5"
    local DB_NAME="$6"

    echo -e "\n================================================================================" | tee -a "$LOG_FILE"
    echo " [+] AUDITING INSTANCE: ${INSTANCE_NAME} (${DB_HOST}:${DB_PORT}/${DB_NAME}) " | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"

    export PGPASSWORD="$DB_PWD"

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << 'EOF' | tee -a "$LOG_FILE"
\timing off
\x off

\echo '--- [1] Engine Storage Allocation Across All Databases ---'
SELECT 
    pg_size_pretty(sum(pg_database_size(datname))) AS total_database_storage_used,
    count(*) AS database_count
FROM pg_database
WHERE datistemplate = false;

SELECT 
    datname AS database_name,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC
LIMIT 5;

\echo '--- [2] RAM Buffer Cache & Memory Settings ---'
SELECT 
    name AS memory_parameter,
    setting || ' ' || COALESCE(unit, '') AS allocated_ram,
    short_desc AS description
FROM pg_settings 
WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'temp_buffers');

SELECT 
    round(sum(blks_hit)*100.0/nullif(sum(blks_hit + blks_read),0), 2) AS cache_hit_ratio_percent
FROM pg_stat_database;

\echo '--- [3] CPU Computing Activity vs Waiting Backends ---'
SELECT 
    count(*) AS total_backends,
    count(*) FILTER (WHERE state = 'active' AND pid != pg_backend_pid()) AS cpu_computing_queries,
    count(*) FILTER (WHERE wait_event_type = 'IO') AS io_waiting_queries,
    count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting_queries,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions
FROM pg_stat_activity;

\echo '--- [4] Connection Usage vs Limits ---'
SELECT 
    (SELECT count(*) FROM pg_stat_activity) AS current_connections,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed_connections,
    ROUND(((SELECT count(*)::numeric FROM pg_stat_activity) / (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2) AS usage_percent;

\echo '--- [5] Engine Version & Postmaster Startup Uptime ---'
SELECT version(), pg_postmaster_start_time() AS instance_started;
EOF
}

# ------------------------------------------------------------------------------
# 1. Audit Marketplace RDS (bettrlabs-mp-prod)
# ------------------------------------------------------------------------------
MP_HOST="${MARKET_DB_HOST:-bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com}"
MP_PORT="${MARKET_DB_PORT:-5432}"
MP_USER="${MARKET_DB_USER:-postgres}"
MP_PWD="${MARKET_DB_PASSWORD:-9nj-Ahng5FCbdfjdsbcdggbj*7VGgbj}"
MP_NAME="${MARKET_DB_NAME:-bettrlabs_market_prod}"

audit_instance "Marketplace RDS (bettrlabs-mp-prod)" "$MP_HOST" "$MP_PORT" "$MP_USER" "$MP_PWD" "$MP_NAME"

# ------------------------------------------------------------------------------
# 2. Audit Production Core DB (bettrlabsprod)
# ------------------------------------------------------------------------------
PR_HOST="${PRODUCT_DB_HOST:-bettrlabsprod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com}"
PR_PORT="${PRODUCT_DB_PORT:-5432}"
PR_USER="${PRODUCT_DB_USER:-bl_pg_admin}"
PR_PWD="${PRODUCT_DB_PWD:-${PRODUCT_DB_PASSWORD:-7oRfnIND467GrxOIArQw}}"
PR_NAME="${PRODUCT_DB_NAME:-ag4good_db}"

audit_instance "Production Core DB (bettrlabsprod)" "$PR_HOST" "$PR_PORT" "$PR_USER" "$PR_PWD" "$PR_NAME"

echo -e "\n[✓] Both instances audited successfully. Output written to: ${LOG_FILE}"
