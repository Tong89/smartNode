#!/bin/bash
# =============================================================================
# SmartNode — Docker entrypoint script
#
# Responsibilities:
#   1. Validate mandatory environment variables for production mode
#   2. Initialise the simulation engine (via gunicorn's preload_app mechanism)
#   3. Launch gunicorn with sensible production defaults that can be overridden
#      by environment variables.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[entrypoint] $*"; }
die() { echo "[entrypoint] FATAL: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Determine gunicorn worker count
# Default: 2 * CPU cores + 1 (gunicorn recommendation for sync workers)
# Override: GUNICORN_WORKERS env var
# ---------------------------------------------------------------------------
default_workers() {
    local cpus
    cpus=$(nproc 2>/dev/null || echo 2)
    echo $(( cpus * 2 + 1 ))
}

WORKERS="${GUNICORN_WORKERS:-$(default_workers)}"
BIND_HOST="${SMARTNODE_HOST:-0.0.0.0}"
BIND_PORT="${SMARTNODE_PORT:-5000}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"
LOG_LEVEL_GUNICORN="${GUNICORN_LOG_LEVEL:-info}"

# ---------------------------------------------------------------------------
# Validate production configuration
# ---------------------------------------------------------------------------
SMARTNODE_ENV="${SMARTNODE_ENV:-development}"
if [ "$SMARTNODE_ENV" = "production" ]; then
    log "Running in PRODUCTION mode — validating required secrets..."
    [ -n "${SMARTNODE_JWT_SECRET:-}" ] || die "SMARTNODE_JWT_SECRET must be set in production"
    [ -n "${SMARTNODE_API_KEY:-}" ]    || die "SMARTNODE_API_KEY must be set in production"
    log "Secrets validated OK."
else
    log "Running in DEVELOPMENT mode (set SMARTNODE_ENV=production for stricter checks)"
fi

# ---------------------------------------------------------------------------
# Launch gunicorn
# ---------------------------------------------------------------------------
log "Starting gunicorn — workers=${WORKERS} bind=${BIND_HOST}:${BIND_PORT}"
log "WSGI app: backend.api:app"

exec gunicorn \
    --workers "${WORKERS}" \
    --threads 1 \
    --worker-class sync \
    --bind "${BIND_HOST}:${BIND_PORT}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --log-level "${LOG_LEVEL_GUNICORN}" \
    --preload \
    "backend.api:app"
