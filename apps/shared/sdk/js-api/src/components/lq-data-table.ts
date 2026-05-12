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

interface TableState {
  loading: boolean;
  error: string | null;
  rows: unknown[][];
  columns: string[];
  totalCount: number;
  page: number;
  pageSize: number;
  sortColumn: string | null;
  sortDir: "asc" | "desc";
  searchText: string;
  editingRowId: unknown | null;
  editFormData: Record<string, unknown>;
  createFormOpen: boolean;
  createFormData: Record<string, unknown>;
}

export class LQDataTable extends LQBaseElement {
  private _state: TableState = {
    loading: false,
    error: null,
    rows: [],
    columns: [],
    totalCount: 0,
    page: 1,
    pageSize: 20,
    sortColumn: null,
    sortDir: "asc",
    searchText: "",
    editingRowId: null,
    editFormData: {},
    createFormOpen: false,
    createFormData: {},
  };
  private _columnDefs: LQColumnDef[] = [];
  private _actions: string[] = [];
  private _table: string = "";
  private _source: string = "";

  connectedCallback() {
    this._source = this.getAttribute("source") || "";
    this._table = this.getAttribute("table") || "";
    this._columnDefs = this.parseJsonAttr<LQColumnDef[]>("columns", []);
    this._actions = this.parseJsonAttr<string[]>("actions", []);
    this._state.pageSize = parseInt(this.getAttribute("page-size") || "20", 10);

    this.addEventListener("lq-refresh", () => this._fetchData());
    this._render();
    this._fetchData();
  }

  private async _fetchData() {
    if (!this._source) {
      this._state.error = "Missing 'source' attribute (SQL query)";
      this._renderBody();
      return;
    }
    this._state.loading = true;
    this._state.error = null;
    this._renderBody();

    try {
      const offset = (this._state.page - 1) * this._state.pageSize;
      let sql = this._source.replace(/;\s*$/, "");

      if (this._state.sortColumn) {
        sql = `SELECT * FROM (${sql}) _t ORDER BY ${this._state.sortColumn} ${this._state.sortDir}`;
      }
      sql += ` LIMIT ${this._state.pageSize} OFFSET ${offset}`;

      const result = await this.client.query(sql);
      this._state.rows = result.rows;
      this._state.columns = result.columns;
      this._state.totalCount = result.row_count;

      if (this._columnDefs.length === 0) {
        this._columnDefs = result.columns.map((c) => ({ key: c, label: this._humanize(c) }));
      }

      // Fetch total count for pagination if result is exactly page size
      if (result.rows.length === this._state.pageSize) {
        try {
          const countResult = await this.client.query(
            `SELECT COUNT(*) as cnt FROM (${this._source.replace(/;\s*$/, "")}) _cnt`,
          );
          this._state.totalCount = Number(countResult.rows[0]?.[0]) || result.rows.length;
        } catch {
          this._state.totalCount = offset + result.rows.length + 1;
        }
      } else {
        this._state.totalCount = offset + result.rows.length;
      }
    } catch (err: unknown) {
      this._state.error = (err as Error).message || "Query failed";
    } finally {
      this._state.loading = false;
      this._renderBody();
    }
  }

  private _humanize(s: string): string {
    return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  private _getColIndex(key: string): number {
    return this._state.columns.indexOf(key);
  }

  private _getCellValue(row: unknown[], key: string): unknown {
    const idx = this._getColIndex(key);
    return idx >= 0 ? row[idx] : null;
  }

  private _formatValue(value: unknown, format?: string): string {
    if (value === null || value === undefined) return "";
    if (format === "date") return new Date(String(value)).toLocaleDateString();
    if (format === "datetime") return new Date(String(value)).toLocaleString();
    if (format === "number") return Number(value).toLocaleString();
    if (format === "currency") return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
    return String(value);
  }

  private _filteredRows(): unknown[][] {
    if (!this._state.searchText) return this._state.rows;
    const q = this._state.searchText.toLowerCase();
    return this._state.rows.filter((row) => row.some((cell) => String(cell ?? "").toLowerCase().includes(q)));
  }

  // --- Mutation handlers ---

  private async _handleDelete(row: unknown[]) {
    const idIdx = this._getColIndex("id");
    if (idIdx < 0 || !this._table) {
      this.toast("Cannot delete: missing 'id' column or 'table' attribute", "error");
      return;
    }
    const id = row[idIdx];
    if (!confirm(`Delete record #${id}?`)) return;
    try {
      await this.client.mutateDeleteById(this._table, id as string | number);
      this.toast("Record deleted", "success");
      await this._fetchData();
    } catch (err: unknown) {
      this.toast((err as Error).message || "Delete failed", "error");
    }
  }

  private _startEdit(row: unknown[]) {
    const idIdx = this._getColIndex("id");
    if (idIdx < 0) return;
    this._state.editingRowId = row[idIdx];
    this._state.editFormData = {};
    this._columnDefs.forEach((col) => {
      this._state.editFormData[col.key] = this._getCellValue(row, col.key);
    });
    this._renderBody();
  }

  private _cancelEdit() {
    this._state.editingRowId = null;
    this._state.editFormData = {};
    this._renderBody();
  }

  private async _saveEdit() {
    if (!this._table || this._state.editingRowId === null) return;
    try {
      const { id: _ignored, ...data } = this._state.editFormData;
      await this.client.mutateUpdateById(this._table, this._state.editingRowId as string | number, data);
      this.toast("Record updated", "success");
      this._state.editingRowId = null;
      await this._fetchData();
    } catch (err: unknown) {
      this.toast((err as Error).message || "Update failed", "error");
    }
  }

  private _openCreate() {
    this._state.createFormOpen = true;
    this._state.createFormData = {};
    this._renderBody();
  }

  private _cancelCreate() {
    this._state.createFormOpen = false;
    this._state.createFormData = {};
    this._renderBody();
  }

  private async _saveCreate() {
    if (!this._table) return;
    try {
      await this.client.mutateInsert(this._table, this._state.createFormData);
      this.toast("Record created", "success");
      this._state.createFormOpen = false;
      this._state.createFormData = {};
      await this._fetchData();
    } catch (err: unknown) {
      this.toast((err as Error).message || "Create failed", "error");
    }
  }

  private _handleSort(colKey: string) {
    if (this._state.sortColumn === colKey) {
      this._state.sortDir = this._state.sortDir === "asc" ? "desc" : "asc";
    } else {
      this._state.sortColumn = colKey;
      this._state.sortDir = "asc";
    }
    this._state.page = 1;
    this._fetchData();
  }

  private _handlePageChange(newPage: number) {
    this._state.page = newPage;
    this._fetchData();
  }

  // --- Rendering ---

  private _render() {
    const hasSearch = this.hasAttribute("searchable");
    const hasCreate = this._actions.includes("create");

    this.innerHTML = `
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
        ${
          hasSearch || hasCreate
            ? `<div class="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200">
            <div class="flex items-center gap-2">
              ${
                hasSearch
                  ? `<div class="relative">
                <svg class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                <input type="text" placeholder="Search..." class="pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500" data-lq-search />
              </div>`
                  : ""
              }
            </div>
            <div>
              ${
                hasCreate
                  ? `<button data-lq-action="create" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                Add
              </button>`
                  : ""
              }
            </div>
          </div>`
            : ""
        }
        <div data-lq-body></div>
      </div>
    `;

    // Bind events
    this.querySelector("[data-lq-search]")?.addEventListener("input", (e) => {
      this._state.searchText = (e.target as HTMLInputElement).value;
      this._renderBody();
    });
    this.querySelector("[data-lq-action='create']")?.addEventListener("click", () => this._openCreate());
  }

  private _renderBody() {
    const body = this.querySelector("[data-lq-body]");
    if (!body) return;

    if (this._state.loading) {
      body.innerHTML = this.renderLoading();
      return;
    }
    if (this._state.error) {
      body.innerHTML = this.renderError(this._state.error);
      return;
    }

    const rows = this._filteredRows();
    if (rows.length === 0 && !this._state.createFormOpen) {
      body.innerHTML = this.renderEmpty("No records found");
      return;
    }

    const hasEdit = this._actions.includes("edit");
    const hasDelete = this._actions.includes("delete");
    const hasActions = hasEdit || hasDelete;
    const idIdx = this._getColIndex("id");

    const sortIcon = (col: LQColumnDef) => {
      if (!col.sortable) return "";
      if (this._state.sortColumn !== col.key) {
        return `<svg class="h-4 w-4 text-gray-300 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3zm-3.76 9.2a.75.75 0 011.06.04l2.7 2.908 2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5a.75.75 0 01-1.1 0l-3.25-3.5a.75.75 0 01.04-1.06z" clip-rule="evenodd"/></svg>`;
      }
      return this._state.sortDir === "asc"
        ? `<svg class="h-4 w-4 text-indigo-600 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 15a.75.75 0 01-.55-.24l-3.25-3.5a.75.75 0 111.1-1.02L10 13.148l2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5A.75.75 0 0110 15z" clip-rule="evenodd"/></svg>`
        : `<svg class="h-4 w-4 text-indigo-600 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 5a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 6.852 7.3 9.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 5z" clip-rule="evenodd"/></svg>`;
    };

    // --- Create form row ---
    const createFormHtml = this._state.createFormOpen
      ? `<tr class="bg-green-50">
        ${this._columnDefs
          .map(
            (col) =>
              col.key === "id"
                ? `<td class="px-4 py-2 text-xs text-gray-400 italic">auto</td>`
                : `<td class="px-4 py-2"><input data-lq-create-field="${col.key}" value="" class="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-indigo-500" placeholder="${col.label || col.key}" /></td>`,
          )
          .join("")}
        ${
          hasActions
            ? `<td class="px-4 py-2 text-right whitespace-nowrap">
            <button data-lq-action="save-create" class="text-sm text-green-700 hover:text-green-900 font-medium mr-2">Save</button>
            <button data-lq-action="cancel-create" class="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
          </td>`
            : ""
        }
      </tr>`
      : "";

    body.innerHTML = `
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              ${this._columnDefs
                .map(
                  (col) => `
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ${col.sortable ? "cursor-pointer select-none" : ""}" ${col.sortable ? `data-lq-sort="${col.key}"` : ""}>
                  <div class="flex items-center">${col.label || col.key}${sortIcon(col)}</div>
                </th>`,
                )
                .join("")}
              ${hasActions ? `<th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Actions</th>` : ""}
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            ${createFormHtml}
            ${rows
              .map((row) => {
                const rowId = idIdx >= 0 ? row[idIdx] : null;
                const isEditing = this._state.editingRowId !== null && rowId === this._state.editingRowId;

                if (isEditing) {
                  return `<tr class="bg-yellow-50">
                  ${this._columnDefs
                    .map(
                      (col) =>
                        col.key === "id"
                          ? `<td class="px-4 py-2 text-sm text-gray-500">${this._formatValue(this._getCellValue(row, col.key), col.format)}</td>`
                          : `<td class="px-4 py-2"><input data-lq-edit-field="${col.key}" value="${this._formatValue(this._state.editFormData[col.key])}" class="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-indigo-500" /></td>`,
                    )
                    .join("")}
                  ${
                    hasActions
                      ? `<td class="px-4 py-2 text-right whitespace-nowrap">
                      <button data-lq-action="save-edit" class="text-sm text-indigo-700 hover:text-indigo-900 font-medium mr-2">Save</button>
                      <button data-lq-action="cancel-edit" class="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
                    </td>`
                      : ""
                  }
                </tr>`;
                }

                return `<tr class="hover:bg-gray-50">
                ${this._columnDefs.map((col) => `<td class="px-4 py-3 text-sm text-gray-900">${this._formatValue(this._getCellValue(row, col.key), col.format)}</td>`).join("")}
                ${
                  hasActions
                    ? `<td class="px-4 py-3 text-right whitespace-nowrap text-sm">
                    ${hasEdit && rowId !== null ? `<button data-lq-action="edit" data-lq-row-idx="${rows.indexOf(row)}" class="text-indigo-600 hover:text-indigo-900 mr-2">Edit</button>` : ""}
                    ${hasDelete && rowId !== null ? `<button data-lq-action="delete" data-lq-row-idx="${rows.indexOf(row)}" class="text-red-600 hover:text-red-900">Delete</button>` : ""}
                  </td>`
                    : ""
                }
              </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
      ${this._renderPagination()}
    `;

    this._bindBodyEvents(rows);
  }

  private _renderPagination(): string {
    const totalPages = Math.max(1, Math.ceil(this._state.totalCount / this._state.pageSize));
    if (totalPages <= 1) return "";

    return `
      <div class="flex items-center justify-between px-4 py-3 border-t border-gray-200">
        <p class="text-sm text-gray-700">
          Showing <span class="font-medium">${(this._state.page - 1) * this._state.pageSize + 1}</span>
          to <span class="font-medium">${Math.min(this._state.page * this._state.pageSize, this._state.totalCount)}</span>
          of <span class="font-medium">${this._state.totalCount}</span>
        </p>
        <div class="flex gap-1">
          <button data-lq-page="${this._state.page - 1}" ${this._state.page <= 1 ? "disabled" : ""}
            class="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed">
            Prev
          </button>
          <button data-lq-page="${this._state.page + 1}" ${this._state.page >= totalPages ? "disabled" : ""}
            class="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed">
            Next
          </button>
        </div>
      </div>`;
  }

  private _bindBodyEvents(rows: unknown[][]) {
    // Sort
    this.querySelectorAll<HTMLElement>("[data-lq-sort]").forEach((th) => {
      th.addEventListener("click", () => this._handleSort(th.dataset.lqSort!));
    });
    // Pagination
    this.querySelectorAll<HTMLElement>("[data-lq-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = parseInt(btn.dataset.lqPage!, 10);
        if (p > 0) this._handlePageChange(p);
      });
    });
    // Row actions
    this.querySelectorAll<HTMLElement>("[data-lq-action='edit']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.lqRowIdx!, 10);
        if (rows[idx]) this._startEdit(rows[idx]);
      });
    });
    this.querySelectorAll<HTMLElement>("[data-lq-action='delete']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.lqRowIdx!, 10);
        if (rows[idx]) this._handleDelete(rows[idx]);
      });
    });
    // Edit form
    this.querySelector("[data-lq-action='save-edit']")?.addEventListener("click", () => {
      this._syncEditFormInputs();
      this._saveEdit();
    });
    this.querySelector("[data-lq-action='cancel-edit']")?.addEventListener("click", () => this._cancelEdit());
    // Create form
    this.querySelector("[data-lq-action='save-create']")?.addEventListener("click", () => {
      this._syncCreateFormInputs();
      this._saveCreate();
    });
    this.querySelector("[data-lq-action='cancel-create']")?.addEventListener("click", () => this._cancelCreate());
  }

  private _syncEditFormInputs() {
    this.querySelectorAll<HTMLInputElement>("[data-lq-edit-field]").forEach((input) => {
      this._state.editFormData[input.dataset.lqEditField!] = input.value;
    });
  }

  private _syncCreateFormInputs() {
    this.querySelectorAll<HTMLInputElement>("[data-lq-create-field]").forEach((input) => {
      if (input.value.trim()) {
        this._state.createFormData[input.dataset.lqCreateField!] = input.value;
      }
    });
  }
}

if (!customElements.get("lq-data-table")) {
  customElements.define("lq-data-table", LQDataTable);
}
