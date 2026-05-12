/**
 * LingQing Live App SDK.
 *
 * **Browser runtime (enforced / injected by the host entry route)**:
 *
 * - The platform injects `lq-sdk`, Tailwind, and Alpine into live app HTML. Tenant app files are plain script/HTML —
 *   do not `import` from the SDK package; there is no app-level bundler.
 * - All JavaScript APIs hang off **`window.LQ` only**. There is **no** global `createLiveAppClient` in app scripts.
 *   Use **`window.LQ.liveApp`** for all backend data operations.
 * - **Built-in Web components** (`<lq-page-shell>`, `<lq-data-table>`, `<lq-toast>`, etc.) are registered by the same injection;
 *   use them as normal tags in `entry.html` (see JSDoc blocks throughout the emitted declaration file).
 *
 */
export interface LiveAppClientOptions {
    appId?: number;
    environment?: string;
    baseUrl?: string;
    getAccessToken?: () => string | null | undefined | Promise<string | null | undefined>;
}
export interface LiveAppQueryResult {
    rows: unknown[][];
    columns: string[];
    row_count: number;
}
export interface LiveAppMutateResult {
    app_id: number;
    operation: string;
    table: string;
    affected_rows: number;
}
export interface LiveAppImportResult {
    app_id: number;
    table: string;
    file_name: string;
    mode: string;
    imported_rows: number;
}
export interface ApiOperationCallParameters {
    /** Query parameters for the API operation */
    query?: Record<string, unknown>;
    /** Path parameters for the API operation */
    path?: Record<string, unknown>;
    /** Request body for the API operation */
    body?: Record<string, unknown>;
    /** Headers to override (optional) */
    headers?: Record<string, string>;
}
export interface ApiExecutionResult {
    status_code: number;
    body: unknown;
    headers: Record<string, string>;
    elapsed_ms: number;
    error?: string | null;
}
export interface LiveAppRuntimeError extends Error {
    status: number;
    code: string;
    details: Record<string, unknown>;
    requestId: string;
}
export interface LiveAppClient {
    setAppId(value: number): void;
    setEnvironment(value: string): void;
    query(sql: string): Promise<LiveAppQueryResult>;
    mutateInsert(table: string, data: Record<string, unknown> | Array<Record<string, unknown>>): Promise<LiveAppMutateResult>;
    mutateUpdateById(table: string, id: string | number, data: Record<string, unknown>): Promise<LiveAppMutateResult>;
    mutateUpdateRows(table: string, data: Record<string, unknown>, where: Record<string, unknown>): Promise<LiveAppMutateResult>;
    mutateDeleteById(table: string, id: string | number): Promise<LiveAppMutateResult>;
    importCsv(table: string, file: File | Blob, mode?: string): Promise<LiveAppImportResult>;
    /**
     * Call external API through connector (app-scoped).
     * Authentication managed by platform - no credentials in code.
     * @param operationUid Stable operation identifier (not DB primary key)
     * @param parameters Optional query/path/body parameters
     */
    callApiConnector(operationUid: string, parameters?: ApiOperationCallParameters): Promise<ApiExecutionResult>;
}
/**
 * Create one live app SDK client.
 */
export declare function createLiveAppClient(options?: LiveAppClientOptions): LiveAppClient;
/** Show a toast notification. Types: "success", "error", "info", "warning". Auto-dismisses after ~4s. */

/**
 * Base class for all LQ web components.
 * Provides SDK access, permission checks, and shared rendering helpers.
 */
import type { LiveAppClient } from "../lq-sdk.v1.0";
export declare abstract class LQBaseElement extends HTMLElement {
    protected _client: LiveAppClient | null;
    get client(): LiveAppClient;
    protected parseJsonAttr<T>(name: string, fallback: T): T;
    protected toast(message: string, type?: string): void;
    protected renderLoading(): string;
    protected renderError(message: string): string;
    protected renderEmpty(message?: string): string;
}

/**
 * <lq-data-table> — Declarative CRUD data table backed by LQ SDK.
 *
 * Usage:
 *   <!-- Minimal: auto-infer columns from query result -->
 *   <lq-data-table source="SELECT * FROM employees" table="employees"></lq-data-table>
 *
 *   <!-- Full: explicit columns, CRUD, search, permissions -->
 *   <lq-data-table
 *     id="emp-table"
 *     source="SELECT id, name, email, dept FROM employees"
 *     table="employees"
 *     columns='[{"key":"name","label":"Name","sortable":true},{"key":"email","label":"Email"}]'
 *     page-size="20"
 *     searchable
 *     actions='["create","edit","delete"]'
 *     read-permission="employees.read"
 *     write-permission="employees.write"
 *   ></lq-data-table>
 *
 * Attributes:
 *   source          — SELECT SQL query for fetching data
 *   table           — Target table name for mutations (insert/update/delete)
 *   columns         — JSON array of column definitions
 *   page-size       — Rows per page (default 20)
 *   searchable      — Show search input (client-side filter)
 *   actions         — JSON array of enabled actions: "create", "edit", "delete"
 *   read-permission — Permission required to view (hides component if denied)
 *   write-permission— Permission required for mutation actions
 *
 * Events:
 *   lq-refresh      — Listen on this element to trigger external refresh
 *   lq-row-action   — Fired on custom row actions with detail { action, row }
 *
 * Cross-component refresh:
 *   document.querySelector('#emp-table').dispatchEvent(new Event('lq-refresh'))
 */
import { LQBaseElement } from "./lq-base-element";
/**
 * Column definition for `<lq-data-table>`.
 *
 * Usage:
 * ```html
 * <!-- Minimal: auto-infer columns from query result -->
 * <lq-data-table source="SELECT * FROM employees" table="employees"></lq-data-table>
 *
 * <!-- Full: explicit columns, CRUD actions, search -->
 * <lq-data-table
 *   id="emp-table"
 *   source="SELECT id, name, email, department FROM employees"
 *   table="employees"
 *   columns='[
 *     {"key":"name","label":"Name","sortable":true},
 *     {"key":"email","label":"Email"},
 *     {"key":"department","label":"Department"}
 *   ]'
 *   page-size="20"
 *   searchable
 *   actions='["create","edit","delete"]'
 * ></lq-data-table>
 * ```
 *
 * Data table attributes:
 * - `source` — SELECT SQL query for fetching data. Pagination (LIMIT/OFFSET) is appended automatically.
 * - `table` — Target table name for mutations (insert, update, delete via SDK). Requires an `id` column.
 * - `columns` — JSON array of `LQColumnDef`. If omitted, columns are auto-inferred from the query result.
 * - `page-size` — Rows per page. Default: 20.
 * - `searchable` — If present, shows a client-side search input.
 * - `actions` — JSON array: `"create"` (add row), `"edit"` (inline edit), `"delete"` (delete with confirm).
 *
 * Programmatic refresh: `element.dispatchEvent(new Event('lq-refresh'))`
 */
export interface LQColumnDef {
    /** Column key — must match a column name in the SQL query result. */
    key: string;
    /** Display header label. Defaults to humanized key (e.g. "created_at" → "Created At"). */
    label?: string;
    /** Enable click-to-sort on this column. Default: false. */
    sortable?: boolean;
    /** Display format. Default: plain text. */
    format?: "date" | "datetime" | "number" | "currency";
}
export declare class LQDataTable extends LQBaseElement {
    private _state;
    private _columnDefs;
    private _actions;
    private _table;
    private _source;
    connectedCallback(): void;
    private _fetchData;
    private _humanize;
    private _getColIndex;
    private _getCellValue;
    private _formatValue;
    private _filteredRows;
    private _handleDelete;
    private _startEdit;
    private _cancelEdit;
    private _saveEdit;
    private _openCreate;
    private _cancelCreate;
    private _saveCreate;
    private _handleSort;
    private _handlePageChange;
    private _render;
    private _renderBody;
    private _renderPagination;
    private _bindBodyEvents;
    private _syncEditFormInputs;
    private _syncCreateFormInputs;
}

/**
 * <lq-form> — Declarative record create/edit form backed by LQ SDK.
 *
 * Usage:
 *   <!-- Create mode -->
 *   <lq-form
 *     table="employees"
 *     fields='[
 *       {"key":"name","label":"Name","type":"text","required":true},
 *       {"key":"email","label":"Email","type":"email","required":true},
 *       {"key":"department","label":"Department","type":"select",
 *        "options":[{"value":"Engineering","label":"Engineering"},{"value":"Sales","label":"Sales"}]},
 *       {"key":"hire_date","label":"Hire Date","type":"date"},
 *       {"key":"notes","label":"Notes","type":"textarea"}
 *     ]'
 *     on-success="lq-refresh:emp-table"
 *   ></lq-form>
 *
 *   <!-- Edit mode (loads record by id, pre-fills) -->
 *   <lq-form table="employees" record-id="42" fields='[...]'></lq-form>
 *
 * Attributes:
 *   table          — Target table name for insert/update
 *   record-id      — If set, edit mode: loads record and pre-fills form
 *   fields         — JSON array of LQFieldDef
 *   submit-label   — Button text (default "Save")
 *   on-success     — Event dispatch pattern "lq-refresh:{elementId}" after save
 *   layout         — "vertical" (default), "horizontal", "grid-2", "grid-3"
 *
 * Events:
 *   lq-form-submit — Fired after successful save with detail { table, data, mode }
 */
import { LQBaseElement } from "./lq-base-element";
/**
 * Field definition for `<lq-form>`.
 *
 * Usage:
 * ```html
 * <lq-form table="employees" fields='[
 *   {"key":"name","label":"Name","type":"text","required":true},
 *   {"key":"email","label":"Email","type":"email","required":true},
 *   {"key":"hire_date","label":"Hire Date","type":"date"},
 *   {"key":"department","label":"Department","type":"select",
 *    "options":[{"value":"Engineering","label":"Engineering"},{"value":"Sales","label":"Sales"}]},
 *   {"key":"salary","label":"Salary","type":"number","min":0},
 *   {"key":"start_time","label":"Start Time","type":"time"},
 *   {"key":"onboarded_at","label":"Onboarded At","type":"datetime"},
 *   {"key":"active","label":"Active","type":"checkbox","defaultValue":true},
 *   {"key":"notes","label":"Notes","type":"textarea","placeholder":"Optional notes..."}
 * ]'></lq-form>
 * ```
 *
 * Form attributes:
 * - `table` — Target table name for SDK insert/update mutations.
 * - `record-id` — If set, enters edit mode: loads existing record by id and pre-fills fields.
 * - `fields` — JSON array of `LQFieldDef` objects defining form fields.
 * - `submit-label` — Submit button text. Default: "Save".
 * - `on-success` — After successful save, dispatches event. Format: `"lq-refresh:{elementId}"`.
 * - `layout` — Form layout: `"vertical"` (stacked, default), `"horizontal"`, `"grid-2"`, `"grid-3"`.
 */
export interface LQFieldDef {
    /** Field key — must match the target table column name. */
    key: string;
    /** Display label. Defaults to humanized key. */
    label?: string;
    /** Input type. Default: "text". */
    type?: "text" | "number" | "email" | "tel" | "textarea" | "date" | "datetime" | "time" | "select" | "checkbox" | "hidden";
    /** Mark field as required. */
    required?: boolean;
    /** Placeholder text for text-like inputs. */
    placeholder?: string;
    /** Default value for create mode. */
    defaultValue?: unknown;
    /** Min constraint (number min or date min string). */
    min?: number | string;
    /** Max constraint (number max or date max string). */
    max?: number | string;
    /** Regex pattern for text-like inputs. */
    pattern?: string;
    /** Static options for select fields. */
    options?: Array<{
        value: string;
        label: string;
    }>;
    /** SQL query to populate select options dynamically. */
    optionsSource?: string;
    /** Column name for option value (default: first column). */
    optionsValueKey?: string;
    /** Column name for option label (default: second column, or first if only one). */
    optionsLabelKey?: string;
}
export declare class LQForm extends LQBaseElement {
    private _fields;
    private _table;
    private _recordId;
    private _formData;
    private _errors;
    private _submitting;
    private _loading;
    private _dynamicOptions;
    connectedCallback(): void;
    private _init;
    private _initDefaults;
    private _loadDynamicOptions;
    private _loadRecord;
    private _getOptions;
    private _humanize;
    private _validate;
    private _handleSubmit;
    private _syncFormInputs;
    private _render;
    private _renderForm;
    private _renderField;
    private _attrConstraints;
    private _errorHtml;
    private _esc;
    private _bindEvents;
}

/**
 * <lq-import> — CSV upload widget with drag-drop, backed by LQ SDK.
 *
 * Usage:
 *   <!-- Minimal -->
 *   <lq-import table="employees"></lq-import>
 *
 *   <!-- Full options -->
 *   <lq-import
 *     table="employees"
 *     mode="append"
 *     accept=".csv,.tsv"
 *     on-success="lq-refresh:emp-table"
 *     label="Import Employees"
 *   ></lq-import>
 *
 * Attributes:
 *   table      — Target table name for importCsv()
 *   mode       — Import mode: "append" (default) or "replace"
 *   accept     — File input accept filter (default ".csv")
 *   label      — Header text (default "Import CSV")
 *   on-success — Event dispatch pattern after import: "lq-refresh:{elementId}"
 *
 * Events:
 *   lq-import-complete — Fired after successful import with detail { table, file_name, imported_rows, mode }
 */
import { LQBaseElement } from "./lq-base-element";
export declare class LQImport extends LQBaseElement {
    private _state;
    private _file;
    private _resultMessage;
    connectedCallback(): void;
    private get _table();
    private get _mode();
    private get _accept();
    private get _label();
    private _formatSize;
    private _handleUpload;
    private _reset;
    private _onFileSelected;
    private _render;
    private _renderResult;
    private _bindEvents;
}

/**
 * <lq-page-shell> — App layout with sidebar navigation and hash-based routing.
 *
 * Usage:
 *   <lq-page-shell app-name="My App" nav-items='[
 *     {"route":"dashboard","label":"Dashboard","icon":"chart-bar","default":true},
 *     {"route":"employees","label":"Employees","icon":"users"},
 *     {"route":"settings","label":"Settings","icon":"cog","permission":"settings.admin"}
 *   ]'>
 *     <div data-route="dashboard">...dashboard content...</div>
 *     <div data-route="employees">...employee content...</div>
 *     <div data-route="settings">...settings content...</div>
 *   </lq-page-shell>
 *
 * Attributes:
 *   app-name     — Display name in the sidebar header
 *   nav-items    — JSON array of navigation items
 *   collapsed    — If present, sidebar starts collapsed
 */
import { LQBaseElement } from "./lq-base-element";
/**
 * Navigation item for `<lq-page-shell>`.
 *
 * Usage:
 * ```html
 * <lq-page-shell app-name="My App" nav-items='[
 *   {"route":"dashboard","label":"Dashboard","icon":"chart-bar","default":true},
 *   {"route":"employees","label":"Employees","icon":"users"},
 *   {"route":"settings","label":"Settings","icon":"cog"}
 * ]'>
 *   <div data-route="dashboard">...dashboard content...</div>
 *   <div data-route="employees">...employees content...</div>
 * </lq-page-shell>
 * ```
 *
 * Routes use hash-based navigation: `#/dashboard`, `#/employees`, etc.
 * Child elements with `data-route="X"` are shown/hidden based on the current hash.
 *
 * Page shell attributes:
 * - `app-name` — Display name shown in the sidebar header.
 * - `nav-items` — JSON array of `LQNavItem` objects.
 * - `collapsed` — If present, sidebar starts in collapsed (icons-only) mode.
 */
export interface LQNavItem {
    /** Hash route segment (e.g. "employees" navigates to `#/employees`). */
    route: string;
    /** Display label in sidebar. */
    label: string;
    /** Icon name. Options: home, chart-bar, users, cog, package, table, upload, document. */
    icon?: string;
    /** If true, this route is the default when no hash is set. */
    default?: boolean;
    /** App-level permission key; hides this nav item if the user lacks the permission. */
    permission?: string;
}
export declare class LQPageShell extends LQBaseElement {
    private _navItems;
    private _currentRoute;
    private _sidebarCollapsed;
    connectedCallback(): void;
    disconnectedCallback(): void;
    private _onHashChange;
    private _routeFromHash;
    private _defaultRoute;
    private _showRoute;
    private _updateActiveNav;
    private _toggleSidebar;
    private _render;
}

/**
 * <lq-stat-card> — Single KPI display card backed by LQ SDK query.
 *
 * Usage:
 *   <lq-stat-card
 *     label="Total Employees"
 *     source="SELECT COUNT(*) FROM employees"
 *     icon="users"
 *     format="number"
 *   ></lq-stat-card>
 *
 *   <lq-stat-card
 *     label="Revenue"
 *     source="SELECT SUM(amount) FROM orders"
 *     icon="chart-bar"
 *     format="currency"
 *     prefix="$"
 *     refresh-interval="30"
 *     trend-source="SELECT SUM(amount) FROM orders WHERE date < '2026-04-01'"
 *   ></lq-stat-card>
 *
 * Attributes:
 *   label            — KPI label text
 *   source           — SQL query returning a single value (row[0][0])
 *   icon             — Icon name: home, chart-bar, users, cog, package, table, upload, document
 *   format           — "number", "currency", "percent", or raw (default)
 *   prefix           — Static text before value
 *   suffix           — Static text after value
 *   refresh-interval — Auto-refresh in seconds (0 = disabled, default)
 *   trend-source     — SQL returning a comparison value for trend arrow
 *
 * Events:
 *   lq-refresh       — Listen on this element to trigger manual refresh
 */
import { LQBaseElement } from "./lq-base-element";
export declare class LQStatCard extends LQBaseElement {
    private _value;
    private _trend;
    private _loading;
    private _error;
    private _intervalId;
    connectedCallback(): void;
    disconnectedCallback(): void;
    private _fetchData;
    private _formatValue;
    private _renderIcon;
    private _renderTrend;
    private _render;
}

/**
 * <lq-toast> — global toast notification system.
 *
 * Programmatic API: window.LQ.toast("Saved!", "success")
 * Types: success | error | info | warning
 *
 * Auto-creates a single container element on first use.
 */
declare function showToast(message: string, type?: string, durationMs?: number): void;
export { showToast };
