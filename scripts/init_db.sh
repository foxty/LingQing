#!/bin/bash
set -e

# Usage function
usage() {
    cat << USAGE_TEXT
Usage: $0 [TENANT_APP_DB_PASSWORD] [MANAGER_DB_PASSWORD]

Parameters:
  TENANT_APP_DB_PASSWORD  App database password (required)
  MANAGER_DB_PASSWORD  Manager database password (required)

Examples:
  # Using parameters
  $0 secure_password secure_manager_password

Hardcoded values:
  TENANT_APP_DB_NAME=lq_tenant_app
  TENANT_APP_DB_USER=lq_tenant_app_db_user
  MANAGER_DB_NAME=lq_tenant_manager
  MANAGER_DB_USER=lq_tenant_manager_db_user

Environment Variables:
  POSTGRES_USER        PostgreSQL superuser (default: postgres)
  POSTGRES_HOST        PostgreSQL host (default: localhost)
  POSTGRES_PORT        PostgreSQL port (default: 5432)
  POSTGRES_CONTAINER   If set, execute psql inside this container (e.g. lingqing-postgres)

USAGE_TEXT
    exit 1
}

# Hardcoded DB and user naming standard
TENANT_APP_DB_NAME="lq_tenant_app"
TENANT_APP_DB_USER="lq_tenant_app_db_user"
MANAGER_DB_NAME="lq_tenant_manager"
MANAGER_DB_USER="lq_tenant_manager_db_user"

# Parse required positional parameters only
TENANT_APP_DB_PASSWORD="$1"
MANAGER_DB_PASSWORD="$2"

# Validate required parameters
if [ -z "$TENANT_APP_DB_PASSWORD" ]; then
    echo "ERROR: App database password is required (1st parameter)" >&2
    usage
fi

if [ -z "$MANAGER_DB_PASSWORD" ]; then
    echo "ERROR: Manager database password is required (2nd parameter)" >&2
    usage
fi

# Safety guards: keep app and manager resources isolated
if [ "$TENANT_APP_DB_NAME" = "$MANAGER_DB_NAME" ]; then
    echo "ERROR: TENANT_APP_DB_NAME and MANAGER_DB_NAME must be different" >&2
    exit 1
fi

if [ "$TENANT_APP_DB_USER" = "$MANAGER_DB_USER" ]; then
    echo "ERROR: TENANT_APP_DB_USER and MANAGER_DB_USER must be different" >&2
    exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

run_psql() {
    if [ -n "${POSTGRES_CONTAINER:-}" ]; then
        docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d postgres "$@"
        return
    fi
    
    if ! command -v psql >/dev/null 2>&1; then
        echo "ERROR: psql command not found. Install PostgreSQL client or set POSTGRES_CONTAINER." >&2
        exit 1
    fi
    
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres "$@"
}

echo "Initializing database..."
if [ -n "${POSTGRES_CONTAINER:-}" ]; then
    echo "  PostgreSQL Container: $POSTGRES_CONTAINER"
else
    echo "  PostgreSQL Host: $POSTGRES_HOST"
    echo "  PostgreSQL Port: $POSTGRES_PORT"
fi
echo "  App Database: $TENANT_APP_DB_NAME"
echo "  App User: $TENANT_APP_DB_USER"
echo "  Manager Database: $MANAGER_DB_NAME"
echo "  Manager User: $MANAGER_DB_USER"

# Execute SQL script with shell-provided variables
run_psql -v ON_ERROR_STOP=1 -v app_db_name="$TENANT_APP_DB_NAME" \
-v app_db_user="$TENANT_APP_DB_USER" \
-v app_db_password="$TENANT_APP_DB_PASSWORD" \
-v manager_db_name="$MANAGER_DB_NAME" \
-v manager_db_user="$MANAGER_DB_USER" \
  -v manager_db_password="$MANAGER_DB_PASSWORD" << 'EOF'
-- ============================================================================
-- Main Database Initialization Script
-- ============================================================================
-- Variables are passed from shell script

-- Create app database only when it does not already exist
SELECT format(
  'CREATE DATABASE %I',
  :'app_db_name'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'app_db_name'
)
\gexec
\echo 'App database ensured: ' :"app_db_name"

-- Create app user only when it does not already exist
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  :'app_db_user',
  :'app_db_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'app_db_user'
)
\gexec

-- Ensure app user credentials are up-to-date
ALTER ROLE :"app_db_user" WITH LOGIN PASSWORD :'app_db_password';
\echo 'App user ensured: ' :"app_db_user"

-- Connect to app database and grant privileges
\c :"app_db_name"

-- Database and schema privileges for app user
GRANT CONNECT ON DATABASE :"app_db_name" TO :"app_db_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_db_user";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"app_db_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"app_db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO :"app_db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO :"app_db_user";

\echo 'App user privileges granted: ' :"app_db_user"

-- Back to postgres database to continue setup
\c postgres

-- Create manager database only when it does not already exist
SELECT format(
  'CREATE DATABASE %I',
  :'manager_db_name'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = :'manager_db_name'
)
\gexec
\echo 'Manager database ensured: ' :"manager_db_name"

-- Create manager user only when it does not already exist
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  :'manager_db_user',
  :'manager_db_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'manager_db_user'
)
\gexec

-- Ensure manager user credentials and elevated capabilities are up-to-date
ALTER ROLE :"manager_db_user" WITH LOGIN PASSWORD :'manager_db_password' CREATEDB CREATEROLE;
\echo 'Manager user ensured: ' :"manager_db_user"

-- Connect to manager database and grant access privileges
\c :"manager_db_name"

GRANT CONNECT ON DATABASE :"manager_db_name" TO :"manager_db_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"manager_db_user";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"manager_db_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"manager_db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO :"manager_db_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO :"manager_db_user";

\echo 'Manager user privileges granted: ' :"manager_db_user"

\echo 'Privileges granted to app and manager users'
\echo ''
\echo '=========================================='
\echo ' Initialization completed!'
\echo '=========================================='
EOF

echo "Database initialization completed successfully!"
