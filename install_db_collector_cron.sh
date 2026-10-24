#!/usr/bin/env bash
# Install or replace the nightly Dev + UAT database collector cron entry.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/audit_both_dbs.sh"
LOG_FILE="${SCRIPT_DIR}/logs/db-collector-cron.log"
CRON_MARKER="# db-information-gathering: dev-uat collector"
CRON_LINE="0 2 * * * ${RUNNER} >> ${LOG_FILE} 2>&1 ${CRON_MARKER}"

if [[ ! -x "${RUNNER}" ]]; then
    echo "ERROR: make the runner executable first: chmod +x ${RUNNER}" >&2
    exit 1
fi

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "${EXISTING}" | grep -vF "${CRON_MARKER}" || true)"
{
    printf '%s\n' "${FILTERED}"
    printf '%s\n' "${CRON_LINE}"
} | sed '/^[[:space:]]*$/d' | crontab -

printf 'Installed nightly collector cron entry:\n%s\n' "${CRON_LINE}"
