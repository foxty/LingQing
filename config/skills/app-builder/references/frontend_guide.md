# Frontend Development Guide

## Overview

Build interactive web applications using plain HTML, JavaScript, and CSS. The platform auto-injects Tailwind CSS, Alpine.js, and the LingQing SDK.

## Contents

- [Technology Stack](#technology-stack)
- [SDK Usage](#sdk-usage)
- [Alpine.js Reactive Patterns](#alpinejs-reactive-patterns)
- [Built-in Components](#built-in-components)
- [Common Patterns](#common-patterns)
- [Troubleshooting](#troubleshooting)

---

## Technology Stack

### Auto-Injected Libraries

All three libraries are automatically available in `entry.html` — **do not add manual `<script>` tags**:

1. **Tailwind CSS v3** - Utility-first CSS framework
2. **Alpine.js v3** - Lightweight reactive framework (like Vue but simpler)
3. **LingQing SDK** - Platform API client as `window.LQ`

### Built-in Web Components

The SDK provides pre-built components for common UI patterns:

- `<lq-page-shell>` - Full-page layout with sidebar navigation
- `<lq-data-table>` - Paginated, sortable data table
- `<lq-form>` - Dynamic form builder
- `<lq-stat-card>` - Metric/statistic display card
- `<lq-toast>` - Toast notification system
- `<lq-import>` - CSV file import wizard

---

## SDK Usage

All SDK APIs are under `window.LQ.liveApp`. Key operations:

```javascript
// Query
const result = await window.LQ.liveApp.query("SELECT id, name FROM users");
// result.rows (array of arrays), result.columns, result.row_count

// Insert (single or batch)
await window.LQ.liveApp.mutateInsert("users", {
  name: "Alice",
  email: "alice@example.com",
});
await window.LQ.liveApp.mutateInsert("users", [
  { name: "Bob" },
  { name: "Charlie" },
]);

// Update / Delete
await window.LQ.liveApp.mutateUpdateById("users", 123, {
  email: "new@example.com",
});
await window.LQ.liveApp.mutateUpdateRows(
  "users",
  { active: false },
  { last_login_before: "2023-01-01" },
);
await window.LQ.liveApp.mutateDeleteById("users", 123);

// External API (auth managed by platform)
const weather = await window.LQ.liveApp.callApiConnector("weather-api-uid", {
  query: { city: "Shanghai", units: "metric" },
});
// weather.status_code, weather.body, weather.elapsed_ms

// Toast notifications
window.LQ.toast("Saved!", "success"); // types: success, error, info, warning
```

For full type declarations, see [`javascript_sdk_reference.md`](./javascript_sdk_reference.md).

---

## Alpine.js Reactive Patterns

### Basic Reactivity

```html
<div x-data="{ count: 0 }">
  <button @click="count++">Count: <span x-text="count"></span></button>
</div>
```

### Fetch Data on Load

```html
<div
  x-data="{ orders: [] }"
  x-init="orders = await window.LQ.liveApp.query('SELECT * FROM orders LIMIT 10')"
>
  <template x-for="order in orders" :key="order[0]">
    <div>
      Order #<span x-text="order[0]"></span>: $<span x-text="order[2]"></span>
    </div>
  </template>
</div>
```

### Form Handling

```html
<form
  x-data="{ name: '', email: '' }"
  @submit.prevent="
        await window.LQ.liveApp.mutateInsert('users', { name, email });
        name = ''; email = '';
        window.LQ.toast('User created!', 'success');
      "
>
  <input x-model="name" placeholder="Name" required />
  <input x-model="email" type="email" placeholder="Email" required />
  <button type="submit">Create User</button>
</form>
```

---

## Built-in Components

### lq-page-shell

Full-page layout with optional sidebar navigation:

```html
<lq-page-shell
  app-name="My Dashboard"
  :nav-items='[
    {"route": "dashboard", "label": "Dashboard", "icon": "chart-bar", "default": true},
    {"route": "orders", "label": "Orders", "icon": "table"}
  ]'
>
  <div data-route="dashboard">
    <h1>Welcome!</h1>
  </div>
  <div data-route="orders">
    <!-- Orders content -->
  </div>
</lq-page-shell>
```

### lq-data-table

Paginated, sortable table with search:

```html
<lq-data-table
  source="SELECT id, customer_name, total, status FROM orders"
  table="orders"
  :columns='[
    {"key": "id", "label": "ID", "sortable": true},
    {"key": "customer_name", "label": "Customer"},
    {"key": "total", "label": "Total", "format": "currency"},
    {"key": "status", "label": "Status"}
  ]'
  page-size="20"
  searchable
  :actions='["create","edit","delete"]'
>
</lq-data-table>
```

### lq-stat-card

Display metrics/KPIs:

```html
<lq-stat-card
  label="Total Revenue"
  source="SELECT SUM(total) FROM orders"
  format="currency"
  prefix="$"
  icon="chart-bar"
  trend-source="SELECT SUM(total) FROM orders WHERE created_at < CURRENT_DATE - INTERVAL '30 days'"
>
</lq-stat-card>
```

### lq-toast

Show notifications (programmatic API):

```javascript
// In JavaScript
window.LQ.toast("Saved successfully!", "success");
window.LQ.toast("Error occurred", "error");
window.LQ.toast("Loading...", "info");
```

---

## Complete Example: Orders Dashboard

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Orders Dashboard</title>
  </head>
  <body>
    <lq-page-shell app-name="Orders Dashboard">
      <!-- Stats Row -->
      <div class="grid grid-cols-3 gap-4 mb-6">
        <lq-stat-card
          label="Total Orders"
          source="SELECT COUNT(*) FROM orders"
          format="number"
        >
        </lq-stat-card>

        <lq-stat-card
          label="Revenue"
          source="SELECT SUM(total) FROM orders"
          format="currency"
          prefix="$"
          icon="chart-bar"
        >
        </lq-stat-card>

        <lq-stat-card
          label="Pending"
          source="SELECT COUNT(*) FROM orders WHERE status = 'pending'"
          format="number"
          icon="table"
        >
        </lq-stat-card>
      </div>

      <!-- Orders Table -->
      <lq-data-table
        source="SELECT id, customer_name, total, status, created_at FROM orders ORDER BY created_at DESC"
        table="orders"
        :columns='[
        {"key": "id", "label": "Order ID", "sortable": true},
        {"key": "customer_name", "label": "Customer"},
        {"key": "total", "label": "Total", "format": "currency"},
        {"key": "status", "label": "Status"},
        {"key": "created_at", "label": "Date", "format": "date"}
      ]'
        page-size="20"
      >
      </lq-data-table>
    </lq-page-shell>
  </body>
</html>
```

---

## Best Practices

1. **Use built-in components first** — `<lq-data-table>`, `<lq-form>`, `<lq-stat-card>` over manual HTML
2. **Handle errors gracefully** — wrap SDK calls in try/catch, show user-friendly messages via `window.LQ.toast()`
3. **Use API connectors** for external APIs — never hardcode credentials; the platform manages auth
4. **Keep entry.html clean** — split complex logic into separate JS files under `assets/`

---

## Common Patterns

### Loading Spinner

```html
<div
  x-data="{ loading: true, data: null }"
  x-init="
       loading = true;
       data = await window.LQ.liveApp.query('SELECT * FROM products');
       loading = false;
     "
>
  <template x-if="loading">
    <div class="animate-spin">Loading...</div>
  </template>

  <template x-if="!loading">
    <div x-text="JSON.stringify(data)"></div>
  </template>
</div>
```

### Conditional Rendering

```html
<div x-data="{ status: 'pending' }">
  <template x-if="status === 'pending'">
    <span class="badge-yellow">Pending</span>
  </template>

  <template x-if="status === 'completed'">
    <span class="badge-green">Completed</span>
  </template>
</div>
```

### Form Validation

```html
<form
  x-data="{ email: '', errors: [] }"
  @submit.prevent="
        errors = [];
        if (!email.includes('@')) {
          errors.push('Invalid email');
          return;
        }
        await window.LQ.liveApp.mutateInsert('subscribers', { email });
        window.LQ.toast('Subscribed!', 'success');
      "
>
  <input x-model="email" type="email" required />

  <template x-for="error in errors">
    <p class="text-red-500" x-text="error"></p>
  </template>

  <button type="submit">Subscribe</button>
</form>
```

---

## Troubleshooting

### SDK Not Available

**Problem**: `window.LQ is undefined`

**Solution**: Ensure you're running in the platform's live app environment. The SDK is auto-injected at runtime.

### CORS Errors

**Problem**: API calls fail with CORS errors

**Solution**: Always use `window.LQ.liveApp.callApiConnector()` instead of direct `fetch()` calls. The platform handles CORS.

### Alpine.js Not Working

**Problem**: `x-data`, `x-text` directives don't work

**Solution**: Alpine.js is auto-injected. Check browser console for syntax errors in your expressions.

### Table Not Rendering

**Problem**: `<lq-data-table>` shows empty

**Solution**:

1. Verify SQL query is valid
2. Check that columns array matches SQL result
3. Open browser DevTools to see component errors

---

## Next Steps

For Python scheduled jobs, see: [`python_jobs_guide.md`](./python_jobs_guide.md)

For database migrations, see: [`database_migrations.md`](./database_migrations.md)
