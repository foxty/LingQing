#!/bin/bash
set -e

# Backend Entrypoint Script
# Supports tenant_app_service, tenant_manager_service, scheduler_service applications

APP_MODULE="${APP_MODULE:-tenant_app_service}"

echo "==========================================="
echo " LingQing Backend Entrypoint"
echo "==========================================="
echo "Application: $APP_MODULE"
case "$APP_MODULE" in
    tenant_app_service)
        APP_PORT="8000"
    ;;
    tenant_manager_service)
        APP_PORT="8010"
    ;;
    *)
        APP_PORT="N/A"
    ;;
esac

echo "Port: $APP_PORT"
echo ""

# Function to run migrations only once (for tenant app service)
run_migrations() {
    if [ "$APP_MODULE" = "tenant_app_service" ]; then
        echo "Running database migrations..."
        if uv run --no-dev alembic -c apps/tenant_app_service/alembic.ini upgrade head; then
            echo "✓ Migrations completed"
        else
            echo "Warning: Migration failed, but continuing startup"
        fi
    elif [ "$APP_MODULE" = "tenant_manager_service" ]; then
        echo "Running tenant manager database migrations..."
        if uv run --no-dev alembic -c apps/tenant_manager_service/alembic.ini upgrade head; then
            echo "✓ Tenant manager migrations completed"
        else
            echo "Warning: Tenant manager migration failed, but continuing startup"
        fi
    fi
}

# Function to start the application
start_app() {
    case "$APP_MODULE" in
        tenant_app_service)
            echo "Starting Unified Backend..."
            exec uv run --no-dev uvicorn apps.tenant_app_service.server:app --host 0.0.0.0 --port 8000 --no-access-log
        ;;
        tenant_manager_service)
            echo "Starting Tenant Manager Service..."
            exec uv run --no-dev uvicorn apps.tenant_manager_service.server:app --host 0.0.0.0 --port 8010 --no-access-log
        ;;
        scheduler_service)
            echo "Starting Scheduler Service..."
            exec uv run --no-dev -m apps.scheduler_service.main
        ;;
        *)
            echo "Error: Unknown application: $APP_MODULE"
            echo "Supported applications: tenant_app_service, tenant_manager_service, scheduler_service"
            exit 1
        ;;
    esac
}

# Sync skills from code into DATA_ROOT_PATH/skills (only for tenant_app_service)
sync_skills() {
    if [ "$APP_MODULE" = "tenant_app_service" ]; then
        local src="/app/config/skills"
        local dst="${DATA_ROOT_PATH}/skills"
        local pkg_dst="${DATA_ROOT_PATH}/skill-packages"
        if [ -d "$src" ]; then
            mkdir -p "$dst"
            mkdir -p "$pkg_dst"
            cp -r "$src/." "$dst/"
            echo "✓ Skills synced to $dst"
            echo "✓ Skill package cache initialized at $pkg_dst"
        else
            echo "Warning: Skills source not found at $src, skipping sync"
        fi
        # Ensure base tenants directory exists for on-demand tenant/personal skill dirs
        mkdir -p "${DATA_ROOT_PATH}/tenants"
    fi
}

# Run migrations if needed
run_migrations

# Sync skills to data root
sync_skills

# Start the application
start_app
