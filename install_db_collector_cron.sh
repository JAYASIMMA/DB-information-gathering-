#!/usr/bin/env bash
# ==============================================================================
# Install / Replace Hourly Database Collector Cron Entry (Runs every 1 hour)
# Audits all 4 database clusters (UAT, Dev, Prod, Old Prod) and stores into e34data78
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${SCRIPT_DIR}/logs"

RUNNER="${SCRIPT_DIR}/audit_all_four_dbs.sh"
LOG_FILE="${SCRIPT_DIR}/logs/db-collector-cron.log"
CRON_MARKER="# db-information-gathering: 4-db hourly collector"

# Ensure script is executable
chmod +x "${SCRIPT_DIR}"/*.sh 2>/dev/null || true

# Cron schedule: '0 * * * *' executes at minute 0 of every hour
CRON_LINE="0 * * * * ${RUNNER} >> ${LOG_FILE} 2>&1 ${CRON_MARKER}"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -vF "db-information-gathering" || true)"
{
    printf '%s\n' "${FILTERED}"
    printf '%s\n' "${CRON_LINE}"
} | sed '/^[[:space:]]*$/d' | crontab -

printf '\n\033[1;32m[✓] Successfully installed 1-hour recurring crontab entry:\033[0m\n'
printf '    %s\n' "${CRON_LINE}"
printf '\nLog output will append to:\n    %s\n\n' "${LOG_FILE}"
