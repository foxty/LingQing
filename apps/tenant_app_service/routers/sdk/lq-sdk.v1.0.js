"use strict";
(() => {
  // src/components/lq-toast.ts
  var TOAST_ICONS = {
    success: `<svg class="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/></svg>`,
    error: `<svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/></svg>`,
    warning: `<svg class="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>`,
    info: `<svg class="h-5 w-5 text-blue-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/></svg>`
  };
  var BG_CLASSES = {
    success: "bg-green-50 border-green-200",
    error: "bg-red-50 border-red-200",
    warning: "bg-yellow-50 border-yellow-200",
    info: "bg-blue-50 border-blue-200"
  };
  var containerEl = null;
  function ensureContainer() {
    if (containerEl && document.body.contains(containerEl)) return containerEl;
    containerEl = document.createElement("div");
    containerEl.id = "lq-toast-container";
    containerEl.className = "fixed top-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm";
    document.body.appendChild(containerEl);
    return containerEl;
  }
  function showToast(message, type = "info", durationMs = 4e3) {
    const container = ensureContainer();
    const normalizedType = BG_CLASSES[type] ? type : "info";
    const icon = TOAST_ICONS[normalizedType];
    const bg = BG_CLASSES[normalizedType];
    const el = document.createElement("div");
    el.className = `${bg} border rounded-lg shadow-lg p-4 flex items-start gap-3 transition-all duration-300 opacity-0 translate-x-4`;
    el.innerHTML = `
    ${icon}
    <p class="text-sm text-gray-800 flex-1">${message}</p>
    <button class="text-gray-400 hover:text-gray-600 ml-2" aria-label="Close">
      <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"/></svg>
    </button>
  `;
    const dismiss = () => {
      el.classList.add("opacity-0", "translate-x-4");
      setTimeout(() => el.remove(), 300);
    };
    el.querySelector("button")?.addEventListener("click", dismiss);
    container.appendChild(el);
    requestAnimationFrame(() => {
      el.classList.remove("opacity-0", "translate-x-4");
    });
    if (durationMs > 0) setTimeout(dismiss, durationMs);
  }
  var win = window;
  win.LQ = win.LQ || {};
  win.LQ.toast = showToast;

  // src/components/lq-base-element.ts
  var LQBaseElement = class extends HTMLElement {
    constructor() {
      super(...arguments);
      this._client = null;
    }
    get client() {
      if (!this._client) {
        const lq = window.LQ;
        if (lq?.liveApp) this._client = lq.liveApp;
        else throw new Error("LQ SDK not available. Ensure lq-sdk is loaded before lq-components.");
      }
      return this._client;
    }
    parseJsonAttr(name, fallback) {
      const raw = this.getAttribute(name);
      if (!raw) return fallback;
      try {
        return JSON.parse(raw);
      } catch {
        return fallback;
      }
    }
    toast(message, type = "info") {
      const lq = window.LQ;
      if (lq?.toast) {
        lq.toast(message, type);
      }
    }
    renderLoading() {
      return `<div class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
    </div>`;
    }
    renderError(message) {
      return `<div class="rounded-md bg-red-50 p-4">
      <div class="flex">
        <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/>
        </svg>
        <p class="ml-3 text-sm text-red-800">${message}</p>
      </div>
    </div>`;
    }
    renderEmpty(message = "No data") {
      return `<div class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>
      </svg>
      <p class="mt-2 text-sm text-gray-500">${message}</p>
    </div>`;
    }
  };

  // src/components/lq-page-shell.ts
  var NAV_ICONS = {
    "chart-bar": `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z"/>`,
    users: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>`,
    cog: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>`,
    package: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>`,
    table: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M12 10.875c-.621 0-1.125.504-1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0v-1.5"/>`,
    home: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/>`,
    upload: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>`,
    document: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>`
  };
  function renderIcon(name) {
    const paths = NAV_ICONS[name || "document"] || NAV_ICONS["document"];
    return `<svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">${paths}</svg>`;
  }
  var LQPageShell = class extends LQBaseElement {
    constructor() {
      super(...arguments);
      this._navItems = [];
      this._currentRoute = "";
      this._sidebarCollapsed = false;
      this._onHashChange = () => {
        this._currentRoute = this._routeFromHash() || this._defaultRoute();
        this._showRoute(this._currentRoute);
        this._updateActiveNav();
      };
      this._toggleSidebar = () => {
        this._sidebarCollapsed = !this._sidebarCollapsed;
        const sidebar = this.querySelector("#lq-sidebar");
        if (sidebar) {
          sidebar.classList.toggle("w-64", !this._sidebarCollapsed);
          sidebar.classList.toggle("w-16", this._sidebarCollapsed);
        }
        const labels = this.querySelectorAll(".lq-nav-label");
        labels.forEach((l) => l.style.display = this._sidebarCollapsed ? "none" : "");
        const title = this.querySelector("#lq-sidebar-title");
        if (title) title.style.display = this._sidebarCollapsed ? "none" : "";
      };
    }
    connectedCallback() {
      this.style.display = "block";
      Array.from(this.querySelectorAll("[data-route]")).forEach(
        (el) => el.style.display = "none"
      );
      const init = () => {
        this._navItems = this.parseJsonAttr("nav-items", []);
        this._sidebarCollapsed = this.hasAttribute("collapsed");
        this._currentRoute = this._routeFromHash() || this._defaultRoute();
        this._render();
        this._showRoute(this._currentRoute);
        window.addEventListener("hashchange", this._onHashChange);
      };
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
      } else {
        init();
      }
    }
    disconnectedCallback() {
      window.removeEventListener("hashchange", this._onHashChange);
    }
    _routeFromHash() {
      const hash = window.location.hash.replace(/^#\/?/, "");
      return hash.split("?")[0] || "";
    }
    _defaultRoute() {
      const def = this._navItems.find((n) => n.default);
      return def?.route || this._navItems[0]?.route || "";
    }
    _showRoute(route) {
      const pages = this.querySelectorAll("[data-route]");
      pages.forEach((page) => {
        page.style.display = page.dataset.route === route ? "" : "none";
      });
    }
    _updateActiveNav() {
      const links = this.querySelectorAll("[data-nav-route]");
      links.forEach((link) => {
        const isActive = link.dataset.navRoute === this._currentRoute;
        link.classList.toggle("bg-indigo-50", isActive);
        link.classList.toggle("text-indigo-700", isActive);
        link.classList.toggle("text-gray-700", !isActive);
      });
    }
    _render() {
      const appName = this.getAttribute("app-name") || "App";
      const navHtml = this._navItems.map(
        (item) => `
      <a href="#/${item.route}" data-nav-route="${item.route}"
         class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-gray-100 ${item.route === this._currentRoute ? "bg-indigo-50 text-indigo-700" : "text-gray-700"}">
        ${renderIcon(item.icon)}
        <span class="lq-nav-label">${item.label}</span>
      </a>`
      ).join("\n");
      const shell = document.createElement("div");
      shell.className = "flex h-screen bg-gray-50";
      shell.innerHTML = `
      <aside id="lq-sidebar" class="w-64 bg-white border-r border-gray-200 flex flex-col transition-all duration-200 shrink-0">
        <div class="flex items-center gap-2 px-4 h-14 border-b border-gray-200">
          <button id="lq-sidebar-toggle" class="p-1 rounded-md hover:bg-gray-100 text-gray-500">
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>
            </svg>
          </button>
          <span id="lq-sidebar-title" class="font-semibold text-gray-900 text-sm truncate">${appName}</span>
        </div>
        <nav class="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          ${navHtml}
        </nav>
      </aside>
      <main class="flex-1 overflow-auto">
        <div id="lq-page-content" class="p-6"></div>
      </main>
    `;
      const contentSlot = shell.querySelector("#lq-page-content");
      const pages = Array.from(this.querySelectorAll("[data-route]"));
      pages.forEach((page) => contentSlot.appendChild(page));
      this.innerHTML = "";
      this.appendChild(shell);
      this.querySelector("#lq-sidebar-toggle")?.addEventListener("click", this._toggleSidebar);
    }
  };
  if (!customElements.get("lq-page-shell")) {
    customElements.define("lq-page-shell", LQPageShell);
  }

  // src/components/lq-data-table.ts
  var LQDataTable = class extends LQBaseElement {
    constructor() {
      super(...arguments);
      this._state = {
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
        createFormData: {}
      };
      this._columnDefs = [];
      this._actions = [];
      this._table = "";
      this._source = "";
    }
    connectedCallback() {
      this._source = this.getAttribute("source") || "";
      this._table = this.getAttribute("table") || "";
      this._columnDefs = this.parseJsonAttr("columns", []);
      this._actions = this.parseJsonAttr("actions", []);
      this._state.pageSize = parseInt(this.getAttribute("page-size") || "20", 10);
      this.addEventListener("lq-refresh", () => this._fetchData());
      this._render();
      this._fetchData();
    }
    async _fetchData() {
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
        if (result.rows.length === this._state.pageSize) {
          try {
            const countResult = await this.client.query(
              `SELECT COUNT(*) as cnt FROM (${this._source.replace(/;\s*$/, "")}) _cnt`
            );
            this._state.totalCount = Number(countResult.rows[0]?.[0]) || result.rows.length;
          } catch {
            this._state.totalCount = offset + result.rows.length + 1;
          }
        } else {
          this._state.totalCount = offset + result.rows.length;
        }
      } catch (err) {
        this._state.error = err.message || "Query failed";
      } finally {
        this._state.loading = false;
        this._renderBody();
      }
    }
    _humanize(s) {
      return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    }
    _getColIndex(key) {
      return this._state.columns.indexOf(key);
    }
    _getCellValue(row, key) {
      const idx = this._getColIndex(key);
      return idx >= 0 ? row[idx] : null;
    }
    _formatValue(value, format) {
      if (value === null || value === void 0) return "";
      if (format === "date") return new Date(String(value)).toLocaleDateString();
      if (format === "datetime") return new Date(String(value)).toLocaleString();
      if (format === "number") return Number(value).toLocaleString();
      if (format === "currency") return `$${Number(value).toLocaleString(void 0, { minimumFractionDigits: 2 })}`;
      return String(value);
    }
    _filteredRows() {
      if (!this._state.searchText) return this._state.rows;
      const q = this._state.searchText.toLowerCase();
      return this._state.rows.filter((row) => row.some((cell) => String(cell ?? "").toLowerCase().includes(q)));
    }
    // --- Mutation handlers ---
    async _handleDelete(row) {
      const idIdx = this._getColIndex("id");
      if (idIdx < 0 || !this._table) {
        this.toast("Cannot delete: missing 'id' column or 'table' attribute", "error");
        return;
      }
      const id = row[idIdx];
      if (!confirm(`Delete record #${id}?`)) return;
      try {
        await this.client.mutateDeleteById(this._table, id);
        this.toast("Record deleted", "success");
        await this._fetchData();
      } catch (err) {
        this.toast(err.message || "Delete failed", "error");
      }
    }
    _startEdit(row) {
      const idIdx = this._getColIndex("id");
      if (idIdx < 0) return;
      this._state.editingRowId = row[idIdx];
      this._state.editFormData = {};
      this._columnDefs.forEach((col) => {
        this._state.editFormData[col.key] = this._getCellValue(row, col.key);
      });
      this._renderBody();
    }
    _cancelEdit() {
      this._state.editingRowId = null;
      this._state.editFormData = {};
      this._renderBody();
    }
    async _saveEdit() {
      if (!this._table || this._state.editingRowId === null) return;
      try {
        const { id: _ignored, ...data } = this._state.editFormData;
        await this.client.mutateUpdateById(this._table, this._state.editingRowId, data);
        this.toast("Record updated", "success");
        this._state.editingRowId = null;
        await this._fetchData();
      } catch (err) {
        this.toast(err.message || "Update failed", "error");
      }
    }
    _openCreate() {
      this._state.createFormOpen = true;
      this._state.createFormData = {};
      this._renderBody();
    }
    _cancelCreate() {
      this._state.createFormOpen = false;
      this._state.createFormData = {};
      this._renderBody();
    }
    async _saveCreate() {
      if (!this._table) return;
      try {
        await this.client.mutateInsert(this._table, this._state.createFormData);
        this.toast("Record created", "success");
        this._state.createFormOpen = false;
        this._state.createFormData = {};
        await this._fetchData();
      } catch (err) {
        this.toast(err.message || "Create failed", "error");
      }
    }
    _handleSort(colKey) {
      if (this._state.sortColumn === colKey) {
        this._state.sortDir = this._state.sortDir === "asc" ? "desc" : "asc";
      } else {
        this._state.sortColumn = colKey;
        this._state.sortDir = "asc";
      }
      this._state.page = 1;
      this._fetchData();
    }
    _handlePageChange(newPage) {
      this._state.page = newPage;
      this._fetchData();
    }
    // --- Rendering ---
    _render() {
      const hasSearch = this.hasAttribute("searchable");
      const hasCreate = this._actions.includes("create");
      this.innerHTML = `
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
        ${hasSearch || hasCreate ? `<div class="flex items-center justify-between gap-4 px-4 py-3 border-b border-gray-200">
            <div class="flex items-center gap-2">
              ${hasSearch ? `<div class="relative">
                <svg class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                <input type="text" placeholder="Search..." class="pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500" data-lq-search />
              </div>` : ""}
            </div>
            <div>
              ${hasCreate ? `<button data-lq-action="create" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                Add
              </button>` : ""}
            </div>
          </div>` : ""}
        <div data-lq-body></div>
      </div>
    `;
      this.querySelector("[data-lq-search]")?.addEventListener("input", (e) => {
        this._state.searchText = e.target.value;
        this._renderBody();
      });
      this.querySelector("[data-lq-action='create']")?.addEventListener("click", () => this._openCreate());
    }
    _renderBody() {
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
      const sortIcon = (col) => {
        if (!col.sortable) return "";
        if (this._state.sortColumn !== col.key) {
          return `<svg class="h-4 w-4 text-gray-300 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 3a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 4.852 7.3 7.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 3zm-3.76 9.2a.75.75 0 011.06.04l2.7 2.908 2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5a.75.75 0 01-1.1 0l-3.25-3.5a.75.75 0 01.04-1.06z" clip-rule="evenodd"/></svg>`;
        }
        return this._state.sortDir === "asc" ? `<svg class="h-4 w-4 text-indigo-600 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 15a.75.75 0 01-.55-.24l-3.25-3.5a.75.75 0 111.1-1.02L10 13.148l2.7-2.908a.75.75 0 111.1 1.02l-3.25 3.5A.75.75 0 0110 15z" clip-rule="evenodd"/></svg>` : `<svg class="h-4 w-4 text-indigo-600 ml-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 5a.75.75 0 01.55.24l3.25 3.5a.75.75 0 11-1.1 1.02L10 6.852 7.3 9.76a.75.75 0 01-1.1-1.02l3.25-3.5A.75.75 0 0110 5z" clip-rule="evenodd"/></svg>`;
      };
      const createFormHtml = this._state.createFormOpen ? `<tr class="bg-green-50">
        ${this._columnDefs.map(
        (col) => col.key === "id" ? `<td class="px-4 py-2 text-xs text-gray-400 italic">auto</td>` : `<td class="px-4 py-2"><input data-lq-create-field="${col.key}" value="" class="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-indigo-500" placeholder="${col.label || col.key}" /></td>`
      ).join("")}
        ${hasActions ? `<td class="px-4 py-2 text-right whitespace-nowrap">
            <button data-lq-action="save-create" class="text-sm text-green-700 hover:text-green-900 font-medium mr-2">Save</button>
            <button data-lq-action="cancel-create" class="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
          </td>` : ""}
      </tr>` : "";
      body.innerHTML = `
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              ${this._columnDefs.map(
        (col) => `
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ${col.sortable ? "cursor-pointer select-none" : ""}" ${col.sortable ? `data-lq-sort="${col.key}"` : ""}>
                  <div class="flex items-center">${col.label || col.key}${sortIcon(col)}</div>
                </th>`
      ).join("")}
              ${hasActions ? `<th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">Actions</th>` : ""}
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            ${createFormHtml}
            ${rows.map((row) => {
        const rowId = idIdx >= 0 ? row[idIdx] : null;
        const isEditing = this._state.editingRowId !== null && rowId === this._state.editingRowId;
        if (isEditing) {
          return `<tr class="bg-yellow-50">
                  ${this._columnDefs.map(
            (col) => col.key === "id" ? `<td class="px-4 py-2 text-sm text-gray-500">${this._formatValue(this._getCellValue(row, col.key), col.format)}</td>` : `<td class="px-4 py-2"><input data-lq-edit-field="${col.key}" value="${this._formatValue(this._state.editFormData[col.key])}" class="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:ring-1 focus:ring-indigo-500" /></td>`
          ).join("")}
                  ${hasActions ? `<td class="px-4 py-2 text-right whitespace-nowrap">
                      <button data-lq-action="save-edit" class="text-sm text-indigo-700 hover:text-indigo-900 font-medium mr-2">Save</button>
                      <button data-lq-action="cancel-edit" class="text-sm text-gray-500 hover:text-gray-700">Cancel</button>
                    </td>` : ""}
                </tr>`;
        }
        return `<tr class="hover:bg-gray-50">
                ${this._columnDefs.map((col) => `<td class="px-4 py-3 text-sm text-gray-900">${this._formatValue(this._getCellValue(row, col.key), col.format)}</td>`).join("")}
                ${hasActions ? `<td class="px-4 py-3 text-right whitespace-nowrap text-sm">
                    ${hasEdit && rowId !== null ? `<button data-lq-action="edit" data-lq-row-idx="${rows.indexOf(row)}" class="text-indigo-600 hover:text-indigo-900 mr-2">Edit</button>` : ""}
                    ${hasDelete && rowId !== null ? `<button data-lq-action="delete" data-lq-row-idx="${rows.indexOf(row)}" class="text-red-600 hover:text-red-900">Delete</button>` : ""}
                  </td>` : ""}
              </tr>`;
      }).join("")}
          </tbody>
        </table>
      </div>
      ${this._renderPagination()}
    `;
      this._bindBodyEvents(rows);
    }
    _renderPagination() {
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
    _bindBodyEvents(rows) {
      this.querySelectorAll("[data-lq-sort]").forEach((th) => {
        th.addEventListener("click", () => this._handleSort(th.dataset.lqSort));
      });
      this.querySelectorAll("[data-lq-page]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const p = parseInt(btn.dataset.lqPage, 10);
          if (p > 0) this._handlePageChange(p);
        });
      });
      this.querySelectorAll("[data-lq-action='edit']").forEach((btn) => {
        btn.addEventListener("click", () => {
          const idx = parseInt(btn.dataset.lqRowIdx, 10);
          if (rows[idx]) this._startEdit(rows[idx]);
        });
      });
      this.querySelectorAll("[data-lq-action='delete']").forEach((btn) => {
        btn.addEventListener("click", () => {
          const idx = parseInt(btn.dataset.lqRowIdx, 10);
          if (rows[idx]) this._handleDelete(rows[idx]);
        });
      });
      this.querySelector("[data-lq-action='save-edit']")?.addEventListener("click", () => {
        this._syncEditFormInputs();
        this._saveEdit();
      });
      this.querySelector("[data-lq-action='cancel-edit']")?.addEventListener("click", () => this._cancelEdit());
      this.querySelector("[data-lq-action='save-create']")?.addEventListener("click", () => {
        this._syncCreateFormInputs();
        this._saveCreate();
      });
      this.querySelector("[data-lq-action='cancel-create']")?.addEventListener("click", () => this._cancelCreate());
    }
    _syncEditFormInputs() {
      this.querySelectorAll("[data-lq-edit-field]").forEach((input) => {
        this._state.editFormData[input.dataset.lqEditField] = input.value;
      });
    }
    _syncCreateFormInputs() {
      this.querySelectorAll("[data-lq-create-field]").forEach((input) => {
        if (input.value.trim()) {
          this._state.createFormData[input.dataset.lqCreateField] = input.value;
        }
      });
    }
  };
  if (!customElements.get("lq-data-table")) {
    customElements.define("lq-data-table", LQDataTable);
  }

  // src/components/lq-form.ts
  var LQForm = class extends LQBaseElement {
    constructor() {
      super(...arguments);
      this._fields = [];
      this._table = "";
      this._recordId = null;
      this._formData = {};
      this._errors = {};
      this._submitting = false;
      this._loading = false;
      this._dynamicOptions = {};
    }
    connectedCallback() {
      this._table = this.getAttribute("table") || "";
      this._recordId = this.getAttribute("record-id") || null;
      this._fields = this.parseJsonAttr("fields", []);
      this._initDefaults();
      this._init();
    }
    async _init() {
      this._loading = true;
      this._render();
      try {
        await this._loadDynamicOptions();
        if (this._recordId) await this._loadRecord();
      } catch (err) {
        this.toast(err.message || "Failed to load form data", "error");
      } finally {
        this._loading = false;
        this._render();
        this._bindEvents();
      }
    }
    _initDefaults() {
      for (const f of this._fields) {
        if (f.defaultValue !== void 0) {
          this._formData[f.key] = f.defaultValue;
        } else if (f.type === "checkbox") {
          this._formData[f.key] = false;
        } else {
          this._formData[f.key] = "";
        }
      }
    }
    async _loadDynamicOptions() {
      const dynamicFields = this._fields.filter((f) => f.optionsSource);
      if (dynamicFields.length === 0) return;
      const results = await Promise.all(
        dynamicFields.map(async (f) => {
          const result = await this.client.query(f.optionsSource);
          const valIdx = f.optionsValueKey ? result.columns.indexOf(f.optionsValueKey) : 0;
          const lblIdx = f.optionsLabelKey ? result.columns.indexOf(f.optionsLabelKey) : Math.min(1, result.columns.length - 1);
          return {
            key: f.key,
            options: result.rows.map((row) => ({
              value: String(row[valIdx >= 0 ? valIdx : 0] ?? ""),
              label: String(row[lblIdx >= 0 ? lblIdx : 0] ?? "")
            }))
          };
        })
      );
      for (const r of results) this._dynamicOptions[r.key] = r.options;
    }
    async _loadRecord() {
      const result = await this.client.query(
        `SELECT * FROM ${this._table} WHERE id = ${this._recordId}`
      );
      if (result.rows.length === 0) {
        this.toast("Record not found", "error");
        return;
      }
      const row = result.rows[0];
      for (const f of this._fields) {
        const colIdx = result.columns.indexOf(f.key);
        if (colIdx >= 0 && row[colIdx] !== null && row[colIdx] !== void 0) {
          this._formData[f.key] = row[colIdx];
        }
      }
    }
    _getOptions(field) {
      return this._dynamicOptions[field.key] || field.options || [];
    }
    _humanize(s) {
      return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    }
    // --- Validation ---
    _validate() {
      this._errors = {};
      for (const f of this._fields) {
        if (f.type === "hidden") continue;
        const val = this._formData[f.key];
        const strVal = String(val ?? "").trim();
        if (f.required && (val === "" || val === null || val === void 0)) {
          this._errors[f.key] = `${f.label || this._humanize(f.key)} is required`;
          continue;
        }
        if (!strVal) continue;
        if (f.pattern) {
          try {
            if (!new RegExp(f.pattern).test(strVal)) {
              this._errors[f.key] = `Invalid format`;
            }
          } catch {
          }
        }
        if (f.type === "number" && strVal) {
          const num = Number(val);
          if (isNaN(num)) {
            this._errors[f.key] = "Must be a number";
          } else {
            if (f.min !== void 0 && num < Number(f.min)) this._errors[f.key] = `Minimum is ${f.min}`;
            if (f.max !== void 0 && num > Number(f.max)) this._errors[f.key] = `Maximum is ${f.max}`;
          }
        }
        if ((f.type === "date" || f.type === "datetime" || f.type === "time") && strVal) {
          if (f.min && strVal < String(f.min)) this._errors[f.key] = `Must be on or after ${f.min}`;
          if (f.max && strVal > String(f.max)) this._errors[f.key] = `Must be on or before ${f.max}`;
        }
      }
      return Object.keys(this._errors).length === 0;
    }
    // --- Submit ---
    async _handleSubmit() {
      this._syncFormInputs();
      if (!this._validate()) {
        this._renderForm();
        return;
      }
      this._submitting = true;
      this._renderForm();
      try {
        const data = {};
        for (const f of this._fields) {
          if (f.key === "id") continue;
          const val = this._formData[f.key];
          if (f.type === "number" && val !== "" && val !== null) {
            data[f.key] = Number(val);
          } else if (f.type === "checkbox") {
            data[f.key] = Boolean(val);
          } else {
            data[f.key] = val;
          }
        }
        const mode = this._recordId ? "edit" : "create";
        if (this._recordId) {
          await this.client.mutateUpdateById(this._table, this._recordId, data);
        } else {
          await this.client.mutateInsert(this._table, data);
        }
        this.toast(this._recordId ? "Record updated" : "Record created", "success");
        this.dispatchEvent(new CustomEvent("lq-form-submit", { detail: { table: this._table, data, mode } }));
        const onSuccess = this.getAttribute("on-success");
        if (onSuccess) {
          const [eventName, targetId] = onSuccess.split(":");
          if (eventName && targetId) {
            document.getElementById(targetId)?.dispatchEvent(new Event(eventName));
          }
        }
        if (!this._recordId) {
          this._initDefaults();
          this._renderForm();
        }
      } catch (err) {
        this.toast(err.message || "Save failed", "error");
      } finally {
        this._submitting = false;
        this._renderForm();
      }
    }
    _syncFormInputs() {
      for (const f of this._fields) {
        if (f.type === "hidden") continue;
        const input = this.querySelector(
          `[data-lq-field="${f.key}"]`
        );
        if (!input) continue;
        if (f.type === "checkbox") {
          this._formData[f.key] = input.checked;
        } else {
          this._formData[f.key] = input.value;
        }
      }
    }
    // --- Rendering ---
    _render() {
      if (this._loading) {
        this.innerHTML = this.renderLoading();
        return;
      }
      this.innerHTML = `<div class="bg-white rounded-lg border border-gray-200 shadow-sm" data-lq-form-root></div>`;
      this._renderForm();
    }
    _renderForm() {
      const root = this.querySelector("[data-lq-form-root]");
      if (!root) return;
      const layout = this.getAttribute("layout") || "vertical";
      const submitLabel = this.getAttribute("submit-label") || "Save";
      const gridClass = layout === "grid-2" ? "grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-4" : layout === "grid-3" ? "grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-4" : "space-y-4";
      const visibleFields = this._fields.filter((f) => f.type !== "hidden");
      const hiddenFields = this._fields.filter((f) => f.type === "hidden");
      root.innerHTML = `
      <div class="px-5 py-4">
        <div class="${gridClass}">
          ${visibleFields.map((f) => this._renderField(f, layout)).join("")}
        </div>
        ${hiddenFields.map((f) => `<input type="hidden" data-lq-field="${f.key}" value="${this._esc(String(this._formData[f.key] ?? ""))}" />`).join("")}
        <div class="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-gray-200">
          <button data-lq-action="submit" ${this._submitting ? "disabled" : ""}
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed">
            ${this._submitting ? `<div class="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>` : ""}
            ${submitLabel}
          </button>
        </div>
      </div>
    `;
      this._bindEvents();
    }
    _renderField(field, layout) {
      const label = field.label || this._humanize(field.key);
      const error = this._errors[field.key];
      const errorClass = error ? "border-red-300 focus:ring-red-500 focus:border-red-500" : "border-gray-300 focus:ring-indigo-500 focus:border-indigo-500";
      const baseInputClass = `w-full px-3 py-2 text-sm rounded-md border ${errorClass} focus:outline-none focus:ring-2`;
      const val = this._formData[field.key];
      const isHoriz = layout === "horizontal";
      const reqMark = field.required ? `<span class="text-red-500 ml-0.5">*</span>` : "";
      let inputHtml;
      switch (field.type) {
        case "textarea":
          inputHtml = `<textarea data-lq-field="${field.key}" rows="3" placeholder="${this._esc(field.placeholder || "")}" class="${baseInputClass}">${this._esc(String(val ?? ""))}</textarea>`;
          break;
        case "select": {
          const options = this._getOptions(field);
          inputHtml = `<select data-lq-field="${field.key}" class="${baseInputClass}">
          <option value="">${field.placeholder || `Select ${label}...`}</option>
          ${options.map((o) => `<option value="${this._esc(o.value)}" ${String(val) === o.value ? "selected" : ""}>${this._esc(o.label)}</option>`).join("")}
        </select>`;
          break;
        }
        case "checkbox":
          inputHtml = `
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" data-lq-field="${field.key}" ${val ? "checked" : ""}
              class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
            <span class="text-sm text-gray-700">${label}</span>
          </label>`;
          return isHoriz ? `<div class="flex items-center gap-4 py-1">${inputHtml}${this._errorHtml(error)}</div>` : `<div>${inputHtml}${this._errorHtml(error)}</div>`;
        case "datetime":
          inputHtml = `<input type="datetime-local" data-lq-field="${field.key}" value="${this._esc(String(val ?? ""))}" ${this._attrConstraints(field)} placeholder="${this._esc(field.placeholder || "")}" class="${baseInputClass}" />`;
          break;
        default: {
          const inputType = field.type || "text";
          inputHtml = `<input type="${inputType}" data-lq-field="${field.key}" value="${this._esc(String(val ?? ""))}" ${this._attrConstraints(field)} placeholder="${this._esc(field.placeholder || "")}" class="${baseInputClass}" />`;
          break;
        }
      }
      if (isHoriz) {
        return `<div class="flex items-start gap-4">
        <label class="w-1/3 text-sm font-medium text-gray-700 pt-2 text-right">${label}${reqMark}</label>
        <div class="w-2/3">${inputHtml}${this._errorHtml(error)}</div>
      </div>`;
      }
      return `<div>
      <label class="block text-sm font-medium text-gray-700 mb-1">${label}${reqMark}</label>
      ${inputHtml}${this._errorHtml(error)}
    </div>`;
    }
    _attrConstraints(field) {
      const parts = [];
      if (field.min !== void 0) parts.push(`min="${this._esc(String(field.min))}"`);
      if (field.max !== void 0) parts.push(`max="${this._esc(String(field.max))}"`);
      if (field.pattern) parts.push(`pattern="${this._esc(field.pattern)}"`);
      if (field.required) parts.push("required");
      return parts.join(" ");
    }
    _errorHtml(error) {
      if (!error) return "";
      return `<p class="mt-1 text-xs text-red-600">${this._esc(error)}</p>`;
    }
    _esc(s) {
      return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    _bindEvents() {
      this.querySelector("[data-lq-action='submit']")?.addEventListener("click", () => this._handleSubmit());
    }
  };
  if (!customElements.get("lq-form")) {
    customElements.define("lq-form", LQForm);
  }

  // src/components/lq-stat-card.ts
  var STAT_ICONS = {
    "chart-bar": `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z"/>`,
    users: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>`,
    home: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/>`,
    cog: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>`,
    package: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>`,
    table: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M12 10.875c-.621 0-1.125.504-1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0v-1.5"/>`,
    upload: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>`,
    document: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>`
  };
  var TREND_UP = `<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L11 10.586 14.586 7H12z" clip-rule="evenodd"/></svg>`;
  var TREND_DOWN = `<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12 13a1 1 0 100 2h5a1 1 0 001-1V9a1 1 0 10-2 0v2.586l-4.293-4.293a1 1 0 00-1.414 0L8 9.586 3.707 5.293a1 1 0 00-1.414 1.414l5 5a1 1 0 001.414 0L11 9.414 14.586 13H12z" clip-rule="evenodd"/></svg>`;
  var LQStatCard = class extends LQBaseElement {
    constructor() {
      super(...arguments);
      this._value = null;
      this._trend = null;
      this._loading = true;
      this._error = null;
      this._intervalId = null;
    }
    connectedCallback() {
      this.addEventListener("lq-refresh", () => this._fetchData());
      this._fetchData();
      const interval = parseInt(this.getAttribute("refresh-interval") || "0", 10);
      if (interval > 0) {
        this._intervalId = setInterval(() => this._fetchData(), interval * 1e3);
      }
    }
    disconnectedCallback() {
      if (this._intervalId) {
        clearInterval(this._intervalId);
        this._intervalId = null;
      }
    }
    async _fetchData() {
      const source = this.getAttribute("source");
      if (!source) {
        this._error = "Missing 'source' attribute";
        this._loading = false;
        this._render();
        return;
      }
      this._loading = true;
      this._error = null;
      this._render();
      try {
        const trendSource = this.getAttribute("trend-source");
        const [result, trendResult] = await Promise.all([
          this.client.query(source),
          trendSource ? this.client.query(trendSource) : Promise.resolve(null)
        ]);
        this._value = result.rows[0]?.[0] ?? null;
        if (trendResult && trendResult.rows[0]?.[0] !== null && trendResult.rows[0]?.[0] !== void 0) {
          const prev = Number(trendResult.rows[0][0]);
          const curr = Number(this._value);
          if (prev !== 0 && !isNaN(prev) && !isNaN(curr)) {
            this._trend = (curr - prev) / Math.abs(prev) * 100;
          }
        }
      } catch (err) {
        this._error = err.message || "Query failed";
      } finally {
        this._loading = false;
        this._render();
      }
    }
    _formatValue(raw) {
      if (raw === null || raw === void 0) return "\u2014";
      const format = this.getAttribute("format");
      const num = Number(raw);
      if (format === "number" && !isNaN(num)) return num.toLocaleString();
      if (format === "currency" && !isNaN(num)) return num.toLocaleString(void 0, { minimumFractionDigits: 2 });
      if (format === "percent" && !isNaN(num)) return `${num.toLocaleString(void 0, { minimumFractionDigits: 1 })}%`;
      return String(raw);
    }
    _renderIcon() {
      const icon = this.getAttribute("icon");
      const paths = STAT_ICONS[icon || ""] || "";
      if (!paths) return "";
      return `<div class="p-2 bg-indigo-50 rounded-lg">
      <svg class="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">${paths}</svg>
    </div>`;
    }
    _renderTrend() {
      if (this._trend === null) return "";
      const isUp = this._trend >= 0;
      const colorClass = isUp ? "text-green-600 bg-green-50" : "text-red-600 bg-red-50";
      const arrow = isUp ? TREND_UP : TREND_DOWN;
      return `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium ${colorClass}">
      ${arrow}${Math.abs(this._trend).toFixed(1)}%
    </span>`;
    }
    _render() {
      if (this._loading && this._value === null) {
        this.innerHTML = `<div class="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
        ${this.renderLoading()}
      </div>`;
        return;
      }
      if (this._error) {
        this.innerHTML = `<div class="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
        ${this.renderError(this._error)}
      </div>`;
        return;
      }
      const label = this.getAttribute("label") || "";
      const prefix = this.getAttribute("prefix") || "";
      const suffix = this.getAttribute("suffix") || "";
      const formatted = `${prefix}${this._formatValue(this._value)}${suffix}`;
      this.innerHTML = `
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm p-5">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm font-medium text-gray-500">${label}</p>
            <p class="mt-1 text-2xl font-bold text-gray-900">${formatted}</p>
            ${this._trend !== null ? `<div class="mt-1">${this._renderTrend()}</div>` : ""}
          </div>
          ${this._renderIcon()}
        </div>
      </div>
    `;
    }
  };
  if (!customElements.get("lq-stat-card")) {
    customElements.define("lq-stat-card", LQStatCard);
  }

  // src/components/lq-import.ts
  var LQImport = class extends LQBaseElement {
    constructor() {
      super(...arguments);
      this._state = "idle";
      this._file = null;
      this._resultMessage = "";
    }
    connectedCallback() {
      this._render();
    }
    get _table() {
      return this.getAttribute("table") || "";
    }
    get _mode() {
      return this.getAttribute("mode") || "append";
    }
    get _accept() {
      return this.getAttribute("accept") || ".csv";
    }
    get _label() {
      return this.getAttribute("label") || "Import CSV";
    }
    _formatSize(bytes) {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    async _handleUpload() {
      if (!this._file || !this._table) return;
      this._state = "uploading";
      this._render();
      try {
        const result = await this.client.importCsv(this._table, this._file, this._mode);
        this._resultMessage = `Imported ${result.imported_rows} rows into "${result.table}"`;
        this._state = "success";
        this.toast(this._resultMessage, "success");
        this.dispatchEvent(new CustomEvent("lq-import-complete", {
          detail: { table: result.table, file_name: result.file_name, imported_rows: result.imported_rows, mode: this._mode }
        }));
        const onSuccess = this.getAttribute("on-success");
        if (onSuccess) {
          const [eventName, targetId] = onSuccess.split(":");
          if (eventName && targetId) {
            document.getElementById(targetId)?.dispatchEvent(new Event(eventName));
          }
        }
      } catch (err) {
        this._resultMessage = err.message || "Import failed";
        this._state = "error";
        this.toast(this._resultMessage, "error");
      } finally {
        this._render();
      }
    }
    _reset() {
      this._state = "idle";
      this._file = null;
      this._resultMessage = "";
      this._render();
    }
    _onFileSelected(file) {
      if (!file) return;
      this._file = file;
      this._state = "idle";
      this._render();
    }
    _render() {
      if (!this._table) {
        this.innerHTML = this.renderError("Missing 'table' attribute");
        return;
      }
      const hasFile = !!this._file;
      const isUploading = this._state === "uploading";
      const isDone = this._state === "success" || this._state === "error";
      this.innerHTML = `
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div class="px-5 py-4">
          <h3 class="text-sm font-medium text-gray-900 mb-3">${this._label}</h3>

          ${isDone ? this._renderResult() : ""}

          ${!isDone ? `
          <div data-lq-dropzone class="relative border-2 border-dashed rounded-lg p-6 text-center transition-colors ${hasFile ? "border-indigo-300 bg-indigo-50" : "border-gray-300 hover:border-gray-400"}">
            <input type="file" data-lq-file-input accept="${this._accept}" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            ${hasFile ? `
              <div class="flex items-center justify-center gap-3">
                <svg class="h-8 w-8 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>
                </svg>
                <div class="text-left">
                  <p class="text-sm font-medium text-gray-900">${this._file.name}</p>
                  <p class="text-xs text-gray-500">${this._formatSize(this._file.size)}</p>
                </div>
              </div>
            ` : `
              <svg class="mx-auto h-10 w-10 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>
              </svg>
              <p class="mt-2 text-sm text-gray-600">Drag and drop a file here, or <span class="text-indigo-600 font-medium">browse</span></p>
              <p class="mt-1 text-xs text-gray-400">Accepted: ${this._accept}</p>
            `}
          </div>
          ` : ""}

          ${hasFile && !isDone ? `
          <div class="flex items-center justify-between mt-4">
            <div class="flex items-center gap-2 text-sm text-gray-600">
              <span>Mode:</span>
              <select data-lq-mode class="px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="append" ${this._mode === "append" ? "selected" : ""}>Append</option>
                <option value="replace" ${this._mode === "replace" ? "selected" : ""}>Replace</option>
              </select>
            </div>
            <div class="flex items-center gap-2">
              <button data-lq-action="clear" class="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">
                Clear
              </button>
              <button data-lq-action="upload" ${isUploading ? "disabled" : ""}
                class="inline-flex items-center gap-2 px-4 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed">
                ${isUploading ? `<div class="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full"></div>` : `
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/></svg>
                `}
                ${isUploading ? "Uploading..." : "Upload"}
              </button>
            </div>
          </div>
          ` : ""}
        </div>
      </div>
    `;
      this._bindEvents();
    }
    _renderResult() {
      const isSuccess = this._state === "success";
      const bgColor = isSuccess ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200";
      const iconColor = isSuccess ? "text-green-500" : "text-red-500";
      const icon = isSuccess ? `<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/>` : `<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/>`;
      return `
      <div class="${bgColor} border rounded-lg p-4 mb-3">
        <div class="flex items-start gap-3">
          <svg class="h-5 w-5 ${iconColor} shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">${icon}</svg>
          <p class="text-sm text-gray-800">${this._resultMessage}</p>
        </div>
      </div>
      <button data-lq-action="reset" class="text-sm text-indigo-600 hover:text-indigo-800 font-medium">
        Import another file
      </button>
    `;
    }
    _bindEvents() {
      const dropzone = this.querySelector("[data-lq-dropzone]");
      const fileInput = this.querySelector("[data-lq-file-input]");
      if (dropzone) {
        dropzone.addEventListener("dragover", (e) => {
          e.preventDefault();
          dropzone.classList.add("border-indigo-400", "bg-indigo-50");
          dropzone.classList.remove("border-gray-300");
        });
        dropzone.addEventListener("dragleave", () => {
          if (!this._file) {
            dropzone.classList.remove("border-indigo-400", "bg-indigo-50");
            dropzone.classList.add("border-gray-300");
          }
        });
        dropzone.addEventListener("drop", (e) => {
          e.preventDefault();
          const file = e.dataTransfer?.files[0] || null;
          this._onFileSelected(file);
        });
      }
      fileInput?.addEventListener("change", () => {
        this._onFileSelected(fileInput.files?.[0] || null);
      });
      const modeSelect = this.querySelector("[data-lq-mode]");
      modeSelect?.addEventListener("change", () => {
        this.setAttribute("mode", modeSelect.value);
      });
      this.querySelector("[data-lq-action='upload']")?.addEventListener("click", () => this._handleUpload());
      this.querySelector("[data-lq-action='clear']")?.addEventListener("click", () => this._reset());
      this.querySelector("[data-lq-action='reset']")?.addEventListener("click", () => this._reset());
    }
  };
  if (!customElements.get("lq-import")) {
    customElements.define("lq-import", LQImport);
  }

  // src/lq-sdk.v1.0.ts
  function parseContextFromPath(location) {
    const match = (location?.pathname || "").match(
      /(\/api)?\/apps\/(\d+)\/([A-Za-z0-9_-]+)\/(entry|embed)$/
    );
    if (!match) return { appId: null, environment: null, basePrefix: "" };
    const value = Number(match[2]);
    if (!Number.isFinite(value)) {
      return { appId: null, environment: null, basePrefix: "" };
    }
    return {
      appId: value,
      environment: match[3] || null,
      basePrefix: match[1] || ""
    };
  }
  var LQ_ENV_BADGE_STYLE_ID = "lq-env-badge-styles";
  function ensureLiveAppEnvBadgeStyles() {
    if (typeof document === "undefined" || document.getElementById(LQ_ENV_BADGE_STYLE_ID))
      return;
    const style = document.createElement("style");
    style.id = LQ_ENV_BADGE_STYLE_ID;
    style.textContent = `
@keyframes lqEnvDotPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
#lq-env-banner .lq-env-dot {
  animation: lqEnvDotPulse 2s ease-in-out infinite;
}
`;
    document.head.appendChild(style);
  }
  function scheduleLiveAppEnvironmentBanner(rawEnv) {
    if (typeof document === "undefined") return;
    const normalized = (rawEnv || "").trim().toLowerCase();
    if (normalized !== "dev" && normalized !== "test") return;
    const inject = () => {
      if (document.getElementById("lq-env-banner")) return;
      if (!document.body) return;
      ensureLiveAppEnvBadgeStyles();
      const isDev = normalized === "dev";
      const label = isDev ? "Development" : "Test";
      const fg = isDev ? "#92400e" : "#1e3a8a";
      const bg = isDev ? "#fef3c7" : "#dbeafe";
      const dotColor = isDev ? "#ea580c" : "#2563eb";
      const border = isDev ? "1px solid #f59e0b" : "1px solid #60a5fa";
      const banner = document.createElement("div");
      banner.id = "lq-env-banner";
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-label", `Environment: ${label} \u2014 not production`);
      Object.assign(banner.style, {
        position: "fixed",
        bottom: "16px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: "2147483647",
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        padding: "6px 16px",
        borderRadius: "999px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        fontSize: "12px",
        fontWeight: "600",
        whiteSpace: "nowrap",
        color: fg,
        background: bg,
        border,
        boxShadow: "0 4px 14px rgba(0,0,0,0.1)",
        pointerEvents: "none",
        userSelect: "none"
      });
      const dot = document.createElement("span");
      dot.className = "lq-env-dot";
      dot.setAttribute("aria-hidden", "true");
      Object.assign(dot.style, {
        width: "8px",
        height: "8px",
        borderRadius: "50%",
        background: dotColor,
        flexShrink: "0"
      });
      const text = document.createElement("span");
      text.textContent = `${label} \xB7 Not Production`;
      banner.appendChild(dot);
      banner.appendChild(text);
      document.body.appendChild(banner);
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", inject, { once: true });
    } else {
      inject();
    }
  }
  function createRuntimeError(status, payload) {
    const message = payload?.message || payload?.detail || "Request failed";
    const error = new Error(message);
    error.status = status;
    error.code = payload?.code || "UNKNOWN_ERROR";
    error.details = payload?.details || {};
    error.requestId = payload?.request_id || "";
    return error;
  }
  function createLiveAppClient(options) {
    const parsedContext = parseContextFromPath(
      typeof window !== "undefined" ? window.location : void 0
    );
    let appId = options?.appId ?? parsedContext?.appId ?? null;
    let environment = options?.environment ?? parsedContext?.environment ?? null;
    const baseUrl = options?.baseUrl ?? parsedContext?.basePrefix ?? "";
    const getAccessToken = options?.getAccessToken;
    async function request(path, init) {
      const headers = new Headers(init.headers || void 0);
      if (getAccessToken) {
        const token = await getAccessToken();
        if (token && token.trim()) {
          headers.set("Authorization", `Bearer ${token.trim()}`);
        }
      }
      const resp = await fetch(baseUrl + path, {
        ...init,
        headers,
        credentials: "same-origin"
      });
      let payload = null;
      try {
        payload = await resp.json();
      } catch (_e) {
        payload = null;
      }
      if (!resp.ok) {
        throw createRuntimeError(
          resp.status,
          payload
        );
      }
      if (payload && typeof payload === "object" && "data" in payload) {
        return payload.data;
      }
      return payload;
    }
    function requireAppId() {
      if (!appId)
        throw new Error(
          "Live app id is required. Pass appId explicitly when creating sdk client."
        );
      return appId;
    }
    function requireEnvironment() {
      if (!environment || !environment.trim()) {
        throw new Error(
          "Live app environment is required. Pass environment explicitly when creating sdk client."
        );
      }
      return environment.trim();
    }
    scheduleLiveAppEnvironmentBanner(environment);
    return {
      setAppId(value) {
        appId = Number(value);
      },
      setEnvironment(value) {
        environment = value;
      },
      query(sql) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/query`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql })
          }
        );
      },
      mutateInsert(table, data) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation: "insert", table, data })
          }
        );
      },
      mutateUpdateById(table, id, data) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation: "update_by_id", table, id, data })
          }
        );
      },
      mutateUpdateRows(table, data, where) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation: "update", table, data, where })
          }
        );
      },
      mutateDeleteById(table, id) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation: "delete_by_id", table, id })
          }
        );
      },
      importCsv(table, file, mode) {
        const form = new FormData();
        form.append("table", table);
        form.append("mode", mode || "append");
        form.append("file", file);
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/import`,
          {
            method: "POST",
            body: form
          }
        );
      },
      callApiConnector(operationUid, parameters) {
        return request(
          `/apps/v1/${requireAppId()}/${requireEnvironment()}/api-connectors/${operationUid}/call`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ parameters: parameters || {} })
          }
        );
      }
    };
  }
  if (typeof window !== "undefined") {
    const runtime = window;
    runtime.LQ = runtime.LQ || {};
    runtime.LQ.createLiveAppClient = runtime.LQ.createLiveAppClient || createLiveAppClient;
  }
})();
