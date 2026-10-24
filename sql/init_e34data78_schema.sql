-- ==============================================================================
-- Schema for e34data78: Database Cluster & Multi-DB Information Repository
-- ==============================================================================

-- 1. Cluster Instance Audits Master Table
CREATE TABLE IF NOT EXISTS db_instance_audits (
    id SERIAL PRIMARY KEY,
    audit_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    engine_version VARCHAR(64),
    full_version TEXT,
    postmaster_started_at TIMESTAMPTZ,
    uptime VARCHAR(64),
    total_databases_count INT DEFAULT 0,
    total_cluster_storage_pretty VARCHAR(64),
    total_cluster_storage_bytes BIGINT DEFAULT 0,
    cache_hit_ratio_pct NUMERIC(5, 2),
    current_connections INT DEFAULT 0,
    active_connections INT DEFAULT 0,
    idle_connections INT DEFAULT 0,
    idle_in_transaction INT DEFAULT 0,
    max_connections INT DEFAULT 0,
    connection_usage_pct NUMERIC(5, 2),
    cpu_computing_queries INT DEFAULT 0,
    io_waiting_queries INT DEFAULT 0,
    lock_waiting_queries INT DEFAULT 0,
    raw_json_summary JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_instance_audits_ts ON db_instance_audits (audit_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_instance_audits_host ON db_instance_audits (host, port);

-- 2. Cluster Roles and Users
CREATE TABLE IF NOT EXISTS db_cluster_users (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    username VARCHAR(128) NOT NULL,
    is_superuser BOOLEAN DEFAULT FALSE,
    can_login BOOLEAN DEFAULT TRUE,
    conn_limit INT DEFAULT -1,
    granted_roles TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_users_audit_id ON db_cluster_users (audit_id);
CREATE INDEX IF NOT EXISTS idx_cluster_users_username ON db_cluster_users (username);

-- 3. Cluster Settings & Postmaster Parameters
CREATE TABLE IF NOT EXISTS db_cluster_settings (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL, -- 'memory', 'network', 'worker_limit', 'postmaster'
    setting_name VARCHAR(128) NOT NULL,
    setting_value TEXT,
    unit VARCHAR(32),
    source VARCHAR(64),
    short_desc TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_settings_audit_id ON db_cluster_settings (audit_id);
CREATE INDEX IF NOT EXISTS idx_cluster_settings_name ON db_cluster_settings (setting_name);

-- 4. Discovered Databases Catalog
CREATE TABLE IF NOT EXISTS db_database_catalog (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128) NOT NULL,
    is_template BOOLEAN DEFAULT FALSE,
    disk_size_pretty VARCHAR(64),
    disk_size_bytes BIGINT DEFAULT 0,
    encoding VARCHAR(32),
    db_collation VARCHAR(64),
    total_connections INT DEFAULT 0,
    active_connections INT DEFAULT 0,
    idle_connections INT DEFAULT 0,
    idle_in_transaction INT DEFAULT 0,
    user_tables_count INT DEFAULT 0,
    user_views_count INT DEFAULT 0,
    user_indexes_count INT DEFAULT 0,
    inspection_status VARCHAR(64) NOT NULL DEFAULT 'PENDING', -- 'SUCCESS', 'ACCESS_DENIED', 'ERROR', 'SKIPPED_TEMPLATE'
    inspection_error TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_db_catalog_audit_id ON db_database_catalog (audit_id);
CREATE INDEX IF NOT EXISTS idx_db_catalog_name ON db_database_catalog (database_name);

-- 5. Individual Tables across all Databases
CREATE TABLE IF NOT EXISTS db_database_tables (
    id SERIAL PRIMARY KEY,
    database_catalog_id INT NOT NULL REFERENCES db_database_catalog(id) ON DELETE CASCADE,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128) NOT NULL,
    schema_name VARCHAR(128) NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    full_table_name VARCHAR(256) NOT NULL,
    total_size_pretty VARCHAR(64),
    total_size_bytes BIGINT DEFAULT 0,
    table_size_pretty VARCHAR(64),
    table_size_bytes BIGINT DEFAULT 0,
    index_size_pretty VARCHAR(64),
    index_size_bytes BIGINT DEFAULT 0,
    estimated_rows BIGINT DEFAULT 0,
    seq_scan BIGINT DEFAULT 0,
    idx_scan BIGINT DEFAULT 0,
    n_dead_tup BIGINT DEFAULT 0,
    last_vacuum TIMESTAMPTZ,
    last_autovacuum TIMESTAMPTZ,
    last_analyze TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_db_tables_catalog_id ON db_database_tables (database_catalog_id);
CREATE INDEX IF NOT EXISTS idx_db_tables_audit_id ON db_database_tables (audit_id);
CREATE INDEX IF NOT EXISTS idx_db_tables_dbname ON db_database_tables (database_name);
CREATE INDEX IF NOT EXISTS idx_db_tables_size_bytes ON db_database_tables (total_size_bytes DESC);

-- 6. Active In-flight Queries Across Databases
CREATE TABLE IF NOT EXISTS db_database_active_queries (
    id SERIAL PRIMARY KEY,
    audit_id INT NOT NULL REFERENCES db_instance_audits(id) ON DELETE CASCADE,
    database_name VARCHAR(128),
    pid INT,
    username VARCHAR(128),
    client_addr VARCHAR(64),
    state VARCHAR(64),
    duration_seconds NUMERIC(10, 2),
    duration_formatted VARCHAR(64),
    wait_event_type VARCHAR(64),
    wait_event VARCHAR(64),
    query_preview TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_active_queries_audit_id ON db_database_active_queries (audit_id);
CREATE INDEX IF NOT EXISTS idx_active_queries_dbname ON db_database_active_queries (database_name);

ALTER TABLE db_instance_audits ADD COLUMN IF NOT EXISTS environment_profile VARCHAR(64);
ALTER TABLE db_instance_audits ADD COLUMN IF NOT EXISTS instance_name VARCHAR(128);

-- 7. Analytical Convenience Views
DROP VIEW IF EXISTS v_all_databases_summary CASCADE;
CREATE OR REPLACE VIEW v_all_databases_summary AS
SELECT 
    a.id AS audit_id,
    a.audit_timestamp,
    c.database_name,
    c.disk_size_pretty,
    c.disk_size_bytes,
    c.encoding,
    c.db_collation,
    c.user_tables_count,
    c.user_views_count,
    c.user_indexes_count,
    c.total_connections,
    c.inspection_status
FROM db_database_catalog c
JOIN db_instance_audits a ON c.audit_id = a.id
ORDER BY a.audit_timestamp DESC, c.disk_size_bytes DESC;

CREATE OR REPLACE VIEW v_largest_tables_cross_db AS
SELECT 
    t.audit_id,
    t.database_name,
    t.full_table_name,
    t.total_size_pretty,
    t.total_size_bytes,
    t.table_size_pretty,
    t.index_size_pretty,
    t.estimated_rows,
    t.n_dead_tup,
    t.recorded_at
FROM db_database_tables t
ORDER BY t.audit_id DESC, t.total_size_bytes DESC;

-- 7. Aggregated Snapshot Table for Frontend API & Rust Backend
CREATE TABLE IF NOT EXISTS infra_instances (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('ec2', 'rds')),
    payload      JSONB NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS infra_instances_kind_idx
    ON infra_instances (kind);

-- ==============================================================================
-- 8. Automatic 10-Day Retention Policy Cleanup Procedure
-- ==============================================================================
CREATE OR REPLACE PROCEDURE prune_audit_logs_older_than(retention_days INT DEFAULT 10)
LANGUAGE plpgsql
AS $$
DECLARE
    ec2_deleted INT := 0;
    db_deleted INT := 0;
BEGIN
    -- Delete EC2 infrastructure audits older than retention_days (cascades to all 7 child tables)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'infrastructure_audit_logs') THEN
        DELETE FROM infrastructure_audit_logs
        WHERE timestamp < NOW() - make_interval(days => retention_days)
           OR created_at < NOW() - make_interval(days => retention_days);
        GET DIAGNOSTICS ec2_deleted = ROW_COUNT;
        RAISE NOTICE 'Pruned % infrastructure audit session(s) older than % days', ec2_deleted, retention_days;
    END IF;

    -- Delete Database audits older than retention_days (cascades to all 5 child tables)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'db_instance_audits') THEN
        DELETE FROM db_instance_audits
        WHERE audit_timestamp < NOW() - make_interval(days => retention_days)
           OR created_at < NOW() - make_interval(days => retention_days);
        GET DIAGNOSTICS db_deleted = ROW_COUNT;
        RAISE NOTICE 'Pruned % database cluster audit session(s) older than % days', db_deleted, retention_days;
    END IF;
END;
$$;

