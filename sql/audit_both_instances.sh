#!/usr/bin/env bash
# ==============================================================================
# audit_both_instances.sh
# Production Hardware, Engine & State Audit for BOTH AWS RDS PostgreSQL Instances
#
# Audits:
#   1. Marketplace RDS (bettrlabs-mp-prod)
#   2. Production Core DB (bettrlabsprod)
#
# Generates comprehensive state metrics for both instances and writes output to:
#   sql/details.logs
#
# Usage:
#   chmod +x sql/audit_both_instances.sh
#   ./sql/audit_both_instances.sh
# ==============================================================================

set -u
set -o pipefail

# ------------------------------------------------------------------------------
# 0. Environment & Paths Configuration
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/details.logs"

# Ensure destination directory exists and initialize the log file
mkdir -p "${SCRIPT_DIR}"
> "${LOG_FILE}"

log_echo() {
    echo -e "$@" | tee -a "${LOG_FILE}"
}

# Safe .env loader that avoids asterisk globbing and CRLF carriage returns
load_env_file() {
    local env_path="$1"
    if [ -f "$env_path" ]; then
        log_echo "[*] Loading environment variables from ${env_path}..."
        while IFS= read -r line || [ -n "$line" ]; do
            # Strip carriage returns
            line="${line%$'\r'}"
            # Skip comments and blank lines
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
                local key="${BASH_REMATCH[1]}"
                local val="${BASH_REMATCH[2]}"
                # Strip wrapping quotes if present
                val="${val%\"}"
                val="${val#\"}"
                val="${val%\'}"
                val="${val#\'}"
                export "$key"="$val"
            fi
        done < "$env_path"
    fi
}

# Look for .env in current directory, script directory, or workspace root
if [ -f ".env" ]; then
    load_env_file ".env"
elif [ -f "${SCRIPT_DIR}/../.env" ]; then
    load_env_file "${SCRIPT_DIR}/../.env"
elif [ -f "${SCRIPT_DIR}/.env" ]; then
    load_env_file "${SCRIPT_DIR}/.env"
fi

# Verify psql is installed
if ! command -v psql &> /dev/null; then
    log_echo "[-] ERROR: 'psql' command not found."
    log_echo "    Please install PostgreSQL client: sudo apt update && sudo apt install -y postgresql-client"
    exit 1
fi

log_echo "================================================================================"
log_echo " AWS RDS DUAL INSTANCE FULL STATE & HARDWARE AUDIT "
log_echo " Started at: $(date)"
log_echo " Target Log File: ${LOG_FILE}"
log_echo "================================================================================"

# ------------------------------------------------------------------------------
# Function: Audit All States of a PostgreSQL Instance
# ------------------------------------------------------------------------------
audit_instance() {
    local INSTANCE_LABEL="$1"
    local DB_HOST="$2"
    local DB_PORT="$3"
    local DB_USER="$4"
    local DB_PWD="$5"
    local DB_NAME="$6"

    log_echo "\n================================================================================"
    log_echo " [+] AUDITING INSTANCE: ${INSTANCE_LABEL} "
    log_echo "     Endpoint: ${DB_HOST}:${DB_PORT} | DB: ${DB_NAME} | User: ${DB_USER}"
    log_echo "================================================================================"

    export PGPASSWORD="$DB_PWD"

    # Test connection first
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
        log_echo "[-] ERROR: Could not connect to ${INSTANCE_LABEL} at ${DB_HOST}:${DB_PORT}."
        log_echo "    Please verify host, credentials, VPC route, and AWS Security Group ingress rules."
        unset PGPASSWORD
        return 1
    fi

    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" << 'EOF' | tee -a "${LOG_FILE}"
\timing off
\x off

\echo '================================================================================'
\echo ' [1] ENGINE STORAGE & DATABASE INVENTORY (All Non-Template Databases)'
\echo '================================================================================'
SELECT 
    count(*) AS total_databases,
    pg_size_pretty(sum(pg_database_size(datname))) AS total_engine_storage_used
FROM pg_database
WHERE datistemplate = false;

SELECT 
    datname AS database_name,
    pg_size_pretty(pg_database_size(datname)) AS database_size,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate AS collation
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC;

\echo '--- Tablespace Allocation ---'
SELECT 
    spcname AS tablespace_name,
    pg_size_pretty(pg_tablespace_size(spcname)) AS allocated_size
FROM pg_tablespace;

\echo '================================================================================'
\echo ' [2] RAM MEMORY SETTINGS & BUFFER CACHE EFFICIENCY'
\echo '================================================================================'
SELECT 
    name AS memory_parameter,
    setting || ' ' || COALESCE(unit, '') AS allocated_value,
    short_desc AS description
FROM pg_settings 
WHERE name IN (
    'shared_buffers', 
    'work_mem', 
    'maintenance_work_mem', 
    'effective_cache_size', 
    'temp_buffers',
    'wal_buffers'
)
ORDER BY name;

SELECT 
    round(sum(blks_hit) * 100.0 / nullif(sum(blks_hit + blks_read), 0), 2) AS global_cache_hit_ratio_percent
FROM pg_stat_database;

\echo '--- Cache Hit Ratio by Database ---'
SELECT 
    datname AS database_name,
    numbackends AS active_connections,
    xact_commit,
    xact_rollback,
    round(blks_hit * 100.0 / nullif(blks_hit + blks_read, 0), 2) AS db_cache_hit_ratio_percent
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY numbackends DESC;

\echo '================================================================================'
\echo ' [3] CPU ACTIVITY, COMPUTING LOAD & BACKEND RUNTIME STATES'
\echo '================================================================================'
SELECT 
    count(*) AS total_backends,
    count(*) FILTER (WHERE state = 'active' AND pid != pg_backend_pid()) AS cpu_computing_queries,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction,
    count(*) FILTER (WHERE wait_event_type = 'IO') AS io_waiting,
    count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting,
    count(*) FILTER (WHERE wait_event_type = 'LWLock') AS lwlock_waiting
FROM pg_stat_activity;

\echo '--- Active / Running Queries (Top 5 Duration) ---'
SELECT 
    pid,
    usename,
    client_addr,
    now() - query_start AS query_duration,
    state,
    wait_event_type,
    wait_event,
    left(query, 100) AS running_query
FROM pg_stat_activity
WHERE state = 'active' AND pid != pg_backend_pid()
ORDER BY query_start ASC
LIMIT 5;

\echo '================================================================================'
\echo ' [4] CONNECTION UTILIZATION & BREAKDOWN'
\echo '================================================================================'
SELECT 
    (SELECT count(*) FROM pg_stat_activity) AS current_connections,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed_connections,
    ROUND(
        ((SELECT count(*)::numeric FROM pg_stat_activity) / 
         (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2
    ) AS connection_usage_percent;

\echo '--- Connections Grouped by Database ---'
SELECT 
    COALESCE(datname, '[Cluster Worker / Background]') AS database_name,
    count(*) AS total_connections,
    count(*) FILTER (WHERE state = 'active') AS active_queries,
    count(*) FILTER (WHERE state = 'idle') AS idle_connections,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
FROM pg_stat_activity
GROUP BY datname
ORDER BY total_connections DESC;

\echo '--- Connections Grouped by User Role ---'
SELECT 
    COALESCE(usename, '[Internal Background]') AS username,
    count(*) AS total_connections,
    count(*) FILTER (WHERE state = 'active') AS active,
    count(*) FILTER (WHERE state = 'idle') AS idle
FROM pg_stat_activity
GROUP BY usename
ORDER BY total_connections DESC;

\echo '--- Connections Grouped by Client IP Host ---'
SELECT 
    COALESCE(client_addr::text, 'localhost / internal') AS client_ip,
    count(*) AS connections_from_ip
FROM pg_stat_activity
GROUP BY client_addr
ORDER BY connections_from_ip DESC
LIMIT 10;

\echo '================================================================================'
\echo ' [5] DATABASE USERS, ROLES & SECURITY PERMISSIONS'
\echo '================================================================================'
SELECT 
    r.rolname AS username,
    r.rolsuper AS is_superuser,
    r.rolinherit AS inherits_privileges,
    r.rolcreaterole AS can_create_roles,
    r.rolcreatedb AS can_create_db,
    r.rolcanlogin AS can_login,
    r.rolconnlimit AS conn_limit,
    ARRAY(
        SELECT b.rolname 
        FROM pg_auth_members m 
        JOIN pg_roles b ON (m.roleid = b.oid) 
        WHERE m.member = r.oid
    ) AS member_of_roles
FROM pg_roles r
ORDER BY r.rolcanlogin DESC, r.rolname ASC;

\echo '================================================================================'
\echo ' [6] RUNNING WORKER PROCESSES & CAPACITY LIMITS'
\echo '================================================================================'
\echo '--- Active Background Workers by Type ---'
SELECT 
    backend_type,
    count(*) AS running_workers
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY running_workers DESC;

\echo '--- Configured Worker Capacities ---'
SELECT 
    name AS worker_setting,
    setting AS configured_value,
    unit,
    short_desc AS description
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_parallel_maintenance_workers',
    'autovacuum_max_workers',
    'max_logical_replication_workers'
)
ORDER BY name;

\echo '================================================================================'
\echo ' [7] OS BUILD, ENGINE VERSION & POSTMASTER UPTIME'
\echo '================================================================================'
SELECT 
    version() AS full_version_string,
    pg_postmaster_start_time() AS postmaster_start_time,
    now() - pg_postmaster_start_time() AS total_instance_uptime;

\echo '================================================================================'
\echo ' [8] NETWORK PORTS & SSL RUNTIME SETTINGS'
\echo '================================================================================'
SELECT 
    name AS network_setting,
    setting AS active_value,
    short_desc AS description
FROM pg_settings 
WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers', 'ssl_min_protocol_version')
ORDER BY name;

\echo '================================================================================'
\echo ' [9] STARTUP PARAMETERS & CUSTOM RDS PARAMETER GROUP OVERRIDES'
\echo '================================================================================'
SELECT 
    name AS parameter_name,
    setting AS active_value,
    unit,
    context,
    source AS parameter_source
FROM pg_settings
WHERE context = 'postmaster'
   OR source NOT IN ('default', 'client')
ORDER BY context, name
LIMIT 30;

\echo '================================================================================'
\echo ' [10] TOP 10 LARGEST TABLES IN CONNECTED DATABASE'
\echo '================================================================================'
SELECT 
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_data_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_and_toast_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

\echo '================================================================================'
\echo ' [11] CURRENT DATABASE LOCKS & BLOCKS'
\echo '================================================================================'
SELECT 
    locktype,
    mode,
    granted,
    count(*) AS lock_count
FROM pg_locks
GROUP BY locktype, mode, granted
ORDER BY count(*) DESC;

EOF

    unset PGPASSWORD
    log_echo "\n[✓] Completed audit for ${INSTANCE_LABEL}."
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

# ------------------------------------------------------------------------------
# Completion Notice
# ------------------------------------------------------------------------------
log_echo "\n================================================================================"
log_echo " [✓] Dual Instance Audit Finished."
log_echo " Detailed log successfully written to: ${LOG_FILE}"
log_echo "================================================================================"
