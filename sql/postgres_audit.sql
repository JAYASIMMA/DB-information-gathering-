-- ============================================================================
-- AWS RDS & Aurora PostgreSQL Infrastructure & Database Audit Script
-- Collects the 5 key configuration areas:
-- 1. Database counts, connections, and user roles
-- 2. Engine and OS compile versions
-- 3. Listening port and connection settings
-- 4. Active worker processes and thread limits
-- 5. Startup configurations and postmaster parameters
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. DATABASE CONFIGURATION: Databases, Total Connections, and Users
-- ----------------------------------------------------------------------------

-- 1.1 Total Databases & Individual Sizes
SELECT 
    'DATABASE_SUMMARY' AS section,
    datname AS database_name,
    pg_size_pretty(pg_database_size(datname)) AS total_size,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate AS collation
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC;

-- 1.2 Total Database Count
SELECT 
    'DATABASE_COUNT' AS section,
    count(*) AS total_databases 
FROM pg_database 
WHERE datistemplate = false;

-- 1.3 Total Connections (Current Active vs Configured Max)
SELECT 
    'CONNECTION_SUMMARY' AS section,
    (SELECT count(*) FROM pg_stat_activity) AS current_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle_connections,
    (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') AS idle_in_tx,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_allowed_connections,
    ROUND(
        ((SELECT count(*)::numeric FROM pg_stat_activity) / 
         (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections')) * 100, 2
    ) AS connection_usage_percent;

-- 1.3b Connections Breakdown by Individual Database
SELECT 
    'CONNECTIONS_BY_DATABASE' AS section,
    COALESCE(datname, '[Cluster Worker / Background]') AS database_name,
    count(*) AS total_connections,
    count(*) FILTER (WHERE state = 'active') AS active_connections,
    count(*) FILTER (WHERE state = 'idle') AS idle_connections,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx
FROM pg_stat_activity
GROUP BY datname
ORDER BY total_connections DESC;

-- 1.4 Database Users / Roles
SELECT 
    'DATABASE_USERS' AS section,
    r.rolname AS username,
    r.rolsuper AS is_superuser,
    r.rolinherit AS inherits_privileges,
    r.rolcreaterole AS can_create_roles,
    r.rolcreatedb AS can_create_db,
    r.rolcanlogin AS can_login,
    r.rolconnlimit AS connection_limit,
    r.rolvaliduntil AS valid_until,
    ARRAY(
        SELECT b.rolname 
        FROM pg_auth_members m 
        JOIN pg_roles b ON (m.roleid = b.oid) 
        WHERE m.member = r.oid
    ) AS member_of_roles
FROM pg_roles r
ORDER BY r.rolcanlogin DESC, r.rolname ASC;

-- ----------------------------------------------------------------------------
-- 2. OS & ENGINE VERSIONS / PATCH DETAILS
-- ----------------------------------------------------------------------------
-- Note: In AWS managed Aurora/RDS, raw host OS access is abstracted.
-- The compiled OS architecture and PostgreSQL patch version are retrieved here:
SELECT 
    'VERSION_INFO' AS section,
    version() AS full_version_string,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num;

-- Aurora-specific version check (Returns NULL if standard RDS):
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'aurora_version') THEN
        RAISE NOTICE 'Aurora Version: %', aurora_version();
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 3. NETWORK PORTS & RUNTIME LISTEN ADDRESSES
-- ----------------------------------------------------------------------------
SELECT 
    'NETWORK_PORT_INFO' AS section,
    name AS parameter_name,
    setting AS parameter_value,
    short_desc AS description
FROM pg_settings 
WHERE name IN ('port', 'listen_addresses', 'ssl', 'ssl_ciphers', 'ssl_min_protocol_version');

-- ----------------------------------------------------------------------------
-- 4. WORKER PROCESSES (Background Workers, Autovacuum, Parallel Workers)
-- ----------------------------------------------------------------------------

-- 4.1 Currently Running Workers by Backend Type
SELECT 
    'ACTIVE_WORKERS' AS section,
    backend_type,
    count(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY process_count DESC;

-- 4.2 Configured Worker Process Capacity
SELECT 
    'WORKER_LIMITS' AS section,
    name AS worker_setting,
    setting AS configured_value,
    unit,
    boot_val AS default_value,
    short_desc AS description
FROM pg_settings
WHERE name IN (
    'max_worker_processes',
    'max_parallel_workers',
    'max_parallel_workers_per_gather',
    'max_parallel_maintenance_workers',
    'autovacuum_max_workers',
    'max_logical_replication_workers',
    'max_sync_workers_per_subscription'
);

-- ----------------------------------------------------------------------------
-- 5. STARTUP COMMAND & PARAMETER CONFIGURATION (Postmaster Startup Flags)
-- ----------------------------------------------------------------------------
-- In AWS RDS / Aurora, startup command line arguments are translated into
-- postmaster-context settings derived from the RDS DB Parameter Group.
SELECT 
    'STARTUP_SETTINGS' AS section,
    name AS config_parameter,
    setting AS active_value,
    unit,
    context,
    source AS parameter_source,
    boot_val AS boot_default
FROM pg_settings
WHERE context = 'postmaster' -- Parameters set at instance startup
   OR source NOT IN ('default', 'client') -- Non-default custom configurations
ORDER BY context, name;
