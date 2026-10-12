#!/usr/bin/env bash
# ==============================================================================
# inspect_all_databases.sh
# Connects to AWS RDS PostgreSQL and runs audits across ALL databases in the instance.
# Usage:
#   chmod +x sql/inspect_all_databases.sh
#   ./sql/inspect_all_databases.sh "postgresql://postgres:9nj-Ahng5FCbdfjdsbcdggbj*7VGgbj@bettrlabs-mp-prod.cbke0k4kiq34.ap-south-1.rds.amazonaws.com/bettrlabs_market_prod"
# ==============================================================================

set -e

DATABASE_URL="${1:-$DATABASE_URL}"
OUTPUT_LOG="audit_output.log"

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not provided."
    echo "Usage: ./sql/inspect_all_databases.sh <DATABASE_URL>"
    exit 1
fi

echo "================================================================================" | tee "$OUTPUT_LOG"
echo " AWS RDS POSTGRESQL MULTI-DATABASE AUDIT REPORT " | tee -a "$OUTPUT_LOG"
echo " Date: $(date)" | tee -a "$OUTPUT_LOG"
echo "================================================================================" | tee -a "$OUTPUT_LOG"

echo -e "\n[+] 1. Running Global Cluster Audit via primary connection..." | tee -a "$OUTPUT_LOG"
psql "$DATABASE_URL" -f sql/postgres_audit.sql | tee -a "$OUTPUT_LOG"

echo -e "\n[+] 2. Fetching list of all non-template databases..." | tee -a "$OUTPUT_LOG"
DATABASES=$(psql "$DATABASE_URL" -t -A -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('template0', 'template1') ORDER BY datname;")

# Extract base connection URI without database name
BASE_URL=$(echo "$DATABASE_URL" | sed -E 's|/[^/]+$||')

echo "Discovered databases: $DATABASES" | tee -a "$OUTPUT_LOG"

for db in $DATABASES; do
    echo -e "\n--------------------------------------------------------------------------------" | tee -a "$OUTPUT_LOG"
    echo " >>> Auditing Database: $db <<<" | tee -a "$OUTPUT_LOG"
    echo "--------------------------------------------------------------------------------" | tee -a "$OUTPUT_LOG"
    TARGET_URL="${BASE_URL}/${db}"
    
    psql "$TARGET_URL" -c "
        SELECT 
            current_database() AS database_name,
            pg_size_pretty(pg_database_size(current_database())) AS database_size,
            (SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')) AS user_table_count;
        
        SELECT 
            schemaname, 
            count(*) AS table_count 
        FROM pg_tables 
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        GROUP BY schemaname;
    " | tee -a "$OUTPUT_LOG"
done

echo -e "\n[✓] Complete audit finished and written to $OUTPUT_LOG"
