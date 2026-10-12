-- ============================================================================
-- AWS RDS & Aurora MySQL Infrastructure & Database Audit Script
-- Collects the 5 key configuration areas:
-- 1. Database counts, connections, and user roles
-- 2. Engine and OS compile versions
-- 3. Listening port and connection settings
-- 4. Active worker threads and process list
-- 5. Startup configurations and global variables
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. DATABASE CONFIGURATION: Databases, Total Connections, and Users
-- ----------------------------------------------------------------------------

-- 1.1 Total Databases & Sizes
SELECT 
    'DATABASE_SUMMARY' AS section,
    table_schema AS database_name,
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS total_size_mb,
    COUNT(table_name) AS table_count
FROM information_schema.tables
GROUP BY table_schema
ORDER BY total_size_mb DESC;

-- 1.2 Total Database Count
SELECT 
    'DATABASE_COUNT' AS section,
    COUNT(schema_name) AS total_databases
FROM information_schema.schemata;

-- 1.3 Total Connections (Current Active vs Configured Max)
SELECT 
    'CONNECTION_SUMMARY' AS section,
    (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Threads_connected') AS current_connections,
    (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Threads_running') AS active_connections,
    (SELECT VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Max_used_connections') AS max_historical_connections,
    (SELECT VARIABLE_VALUE FROM performance_schema.global_variables WHERE VARIABLE_NAME = 'max_connections') AS max_allowed_connections;

-- 1.4 Database Users
SELECT 
    'DATABASE_USERS' AS section,
    user AS username,
    host AS allowed_host,
    account_locked,
    password_expired,
    plugin AS auth_plugin
FROM mysql.user
ORDER BY user ASC;

-- ----------------------------------------------------------------------------
-- 2. OS & ENGINE VERSIONS / PATCH DETAILS
-- ----------------------------------------------------------------------------
SELECT 
    'VERSION_INFO' AS section,
    VERSION() AS engine_version,
    @@version_comment AS version_comment,
    @@version_compile_os AS compiled_os,
    @@version_compile_machine AS architecture;

-- Aurora Version (returns empty/error if standard RDS MySQL):
-- SELECT AURORA_VERSION();

-- ----------------------------------------------------------------------------
-- 3. NETWORK PORTS & RUNTIME LISTEN ADDRESSES
-- ----------------------------------------------------------------------------
SHOW VARIABLES WHERE Variable_name IN ('port', 'bind_address', 'have_ssl', 'tls_version');

-- ----------------------------------------------------------------------------
-- 4. WORKER THREADS (Active Process Threads & Thread Pool)
-- ----------------------------------------------------------------------------

-- 4.1 Global Thread Status
SHOW GLOBAL STATUS LIKE 'Threads_%';

-- 4.2 Running Commands / Workers Breakdown
SELECT 
    'ACTIVE_WORKERS' AS section,
    command,
    COUNT(*) AS worker_count
FROM information_schema.processlist
GROUP BY command
ORDER BY worker_count DESC;

-- ----------------------------------------------------------------------------
-- 5. STARTUP COMMAND & PARAMETER CONFIGURATION
-- ----------------------------------------------------------------------------
-- Variables that were set via command-line / configuration file rather than default
SELECT 
    'STARTUP_SETTINGS' AS section,
    VARIABLE_NAME,
    VARIABLE_VALUE,
    VARIABLE_SOURCE
FROM performance_schema.variables_info
WHERE VARIABLE_SOURCE NOT IN ('COMPILED', 'DYNAMIC')
ORDER BY VARIABLE_NAME;
