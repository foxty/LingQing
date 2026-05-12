# Database Migrations Guide

## Overview

Manage your app's PostgreSQL database schema using SQL migration files. Each migration represents a schema change (create table, add column, etc.).

## Contents

- [Migration File Structure](#migration-file-structure)
- [Migration File Format](#migration-file-format)
- [Common Migration Patterns](#common-migration-patterns)
- [Migration Workflow](#migration-workflow)
- [Best Practices](#best-practices)
- [Data Migrations](#data-migrations)
- [Troubleshooting](#troubleshooting)

---

## Migration File Structure

Migrations live in the `migrations/` directory under each environment:

```
env/{environment}/
└── migrations/
    ├── 001_create_users.sql
    ├── 002_create_orders.sql
    ├── 003_add_status_to_orders.sql
    └── 004_create_index_on_orders_status.sql
```

**Naming convention:** `{sequence}_{description}.sql`

- Use 3-digit sequence numbers (001, 002, 003...)
- Use lowercase with underscores
- Be descriptive about what the migration does

---

## Migration File Format

Each migration file must contain **both** `up_sql` and `down_sql`:

```sql
-- File: migrations/001_create_users.sql

-- up_sql: Apply this migration
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- down_sql: Rollback this migration
DROP TABLE IF EXISTS users;
```

### Why Both Up and Down?

- **up_sql**: Applied when migrating forward (dev → test → prod)
- **down_sql**: Applied when rolling back (prod → test → dev)

This ensures you can safely revert changes if needed.

---

## Common Migration Patterns

### Create Table

```sql
-- up_sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- down_sql
DROP TABLE IF EXISTS products;
```

### Add Column

```sql
-- up_sql
ALTER TABLE orders ADD COLUMN status VARCHAR(50) DEFAULT 'pending';

-- down_sql
ALTER TABLE orders DROP COLUMN IF EXISTS status;
```

### Create Index

```sql
-- up_sql
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- down_sql
DROP INDEX IF EXISTS idx_orders_status;
DROP INDEX IF EXISTS idx_orders_created_at;
```

### Add Foreign Key

```sql
-- up_sql
ALTER TABLE order_items
ADD CONSTRAINT fk_order_items_order
FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;

-- down_sql
ALTER TABLE order_items
DROP CONSTRAINT IF EXISTS fk_order_items_order;
```

### Modify Column Type

```sql
-- up_sql
ALTER TABLE products
ALTER COLUMN price TYPE DECIMAL(12, 2);

-- down_sql
ALTER TABLE products
ALTER COLUMN price TYPE DECIMAL(10, 2);
```

### Add Check Constraint

```sql
-- up_sql
ALTER TABLE products
ADD CONSTRAINT chk_price_positive CHECK (price > 0);

ALTER TABLE products
ADD CONSTRAINT chk_stock_non_negative CHECK (stock >= 0);

-- down_sql
ALTER TABLE products
DROP CONSTRAINT IF EXISTS chk_price_positive;
ALTER TABLE products
DROP CONSTRAINT IF EXISTS chk_stock_non_negative;
```

---

## Migration Workflow

1. **Create migration**: Use `create_db_migration()` to create a new migration file with `up_sql` and `down_sql` sections.
2. **Write SQL**: Add your schema changes (see patterns below). Always include both `up_sql` and `down_sql`.
3. **Apply to dev**: Use `apply_db_migration()` to apply to the dev environment.
4. **Verify**: Query the database to confirm schema changes are correct.
5. **Commit**: Use `commit_app_changes()` to version-control the migration file.
6. **Promote**: Use `promote_app_environment()` to push to test/prod — migrations apply automatically during promotion.

---

## Best Practices

### 1. One Change Per Migration

✅ Good:

```
001_create_users.sql
002_create_orders.sql
003_add_email_index.sql
```

❌ Bad:

```
001_create_everything.sql  # Creates all tables at once
```

### 2. Always Write Down SQL

✅ Good:

```sql
-- up_sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- down_sql
ALTER TABLE users DROP COLUMN IF EXISTS phone;
```

❌ Bad:

```sql
-- up_sql only, no down_sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
```

### 3. Use Descriptive Names

✅ Good:

```
003_add_status_to_orders.sql
004_create_index_orders_customer_id.sql
```

❌ Bad:

```
003_change.sql
004_fix.sql
```

### 4. Never Modify Committed Migrations

Once a migration is committed and applied, **never modify it**. Create a new migration instead:

❌ Bad (modifying existing):

```sql
-- Editing 001_create_users.sql after it's been applied
ALTER TABLE users ADD COLUMN phone VARCHAR(20);  # Don't do this!
```

✅ Good (creating new):

```sql
-- New file: 005_add_phone_to_users.sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
```

### 5. Test Down Migrations

Always verify that down migrations work in dev before promoting:

```python
# Test rollback
rollback_db_migration()

# Verify column is gone
result = await client.query("SELECT * FROM users LIMIT 1")
assert "phone" not in result.columns
```

### 6. Use Transactions for Complex Changes

For multi-step migrations, wrap in transaction:

```sql
-- up_sql
BEGIN;

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    price DECIMAL(10, 2) NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);

COMMIT;

-- down_sql
DROP TABLE IF EXISTS order_items;
```

---

## Data Migrations

Sometimes you need to migrate data, not just schema:

### Example: Populate Default Values

```sql
-- up_sql
-- Add new column
ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user';

-- Set existing users to 'admin' if they have admin flag
UPDATE users SET role = 'admin' WHERE is_admin = true;

-- Remove old column
ALTER TABLE users DROP COLUMN IF EXISTS is_admin;

-- down_sql
ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT false;
UPDATE users SET is_admin = true WHERE role = 'admin';
ALTER TABLE users DROP COLUMN IF EXISTS role;
```

### Example: Backfill Data

```sql
-- up_sql
-- Calculate and store order totals
UPDATE orders
SET total_amount = (
    SELECT COALESCE(SUM(quantity * price), 0)
    FROM order_items
    WHERE order_items.order_id = orders.id
);

-- down_sql
UPDATE orders SET total_amount = NULL;
```

---

## Troubleshooting

### Migration Fails with "Relation Already Exists"

**Problem**: `ERROR: relation "users" already exists`

**Solution**: You're trying to create a table that already exists. Either:

1. Drop the table first (in dev only)
2. Use `CREATE TABLE IF NOT EXISTS`
3. Create a new migration instead

### Migration Fails with "Column Does Not Exist"

**Problem**: `ERROR: column "status" does not exist`

**Solution**: The column hasn't been added yet. Ensure migrations run in sequence order.

### Can't Rollback Migration

**Problem**: Down migration fails

**Solution**:

1. Check that down SQL is correct
2. Verify no dependent objects exist
3. May need manual cleanup in dev

---

## Migration Tools

Use these platform tools instead of running raw SQL directly:

- `list_db_migrations()` — List all migrations and their status
- `create_db_migration()` — Create a new migration file
- `apply_db_migration()` — Apply migration to environment
- `rollback_db_migration()` — Rollback a migration
- `remove_db_migration()` — Remove a migration file

---

## Next Steps

For frontend development, see: [`frontend_guide.md`](./frontend_guide.md)

For Python scheduled jobs, see: [`python_jobs_guide.md`](./python_jobs_guide.md)
