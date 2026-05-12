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

const STAT_ICONS: Record<string, string> = {
  "chart-bar": `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z"/>`,
  users: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>`,
  home: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/>`,
  cog: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>`,
  package: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>`,
  table: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M12 10.875c-.621 0-1.125.504-1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0v-1.5"/>`,
  upload: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>`,
  document: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>`,
};

const TREND_UP = `<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L11 10.586 14.586 7H12z" clip-rule="evenodd"/></svg>`;
const TREND_DOWN = `<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M12 13a1 1 0 100 2h5a1 1 0 001-1V9a1 1 0 10-2 0v2.586l-4.293-4.293a1 1 0 00-1.414 0L8 9.586 3.707 5.293a1 1 0 00-1.414 1.414l5 5a1 1 0 001.414 0L11 9.414 14.586 13H12z" clip-rule="evenodd"/></svg>`;

export class LQStatCard extends LQBaseElement {
  private _value: unknown = null;
  private _trend: number | null = null;
  private _loading = true;
  private _error: string | null = null;
  private _intervalId: ReturnType<typeof setInterval> | null = null;

  connectedCallback() {
    this.addEventListener("lq-refresh", () => this._fetchData());
    this._fetchData();
    const interval = parseInt(this.getAttribute("refresh-interval") || "0", 10);
    if (interval > 0) {
      this._intervalId = setInterval(() => this._fetchData(), interval * 1000);
    }
  }

  disconnectedCallback() {
    if (this._intervalId) {
      clearInterval(this._intervalId);
      this._intervalId = null;
    }
  }

  private async _fetchData() {
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
        trendSource ? this.client.query(trendSource) : Promise.resolve(null),
      ]);

      this._value = result.rows[0]?.[0] ?? null;

      if (trendResult && trendResult.rows[0]?.[0] !== null && trendResult.rows[0]?.[0] !== undefined) {
        const prev = Number(trendResult.rows[0][0]);
        const curr = Number(this._value);
        if (prev !== 0 && !isNaN(prev) && !isNaN(curr)) {
          this._trend = ((curr - prev) / Math.abs(prev)) * 100;
        }
      }
    } catch (err: unknown) {
      this._error = (err as Error).message || "Query failed";
    } finally {
      this._loading = false;
      this._render();
    }
  }

  private _formatValue(raw: unknown): string {
    if (raw === null || raw === undefined) return "—";
    const format = this.getAttribute("format");
    const num = Number(raw);
    if (format === "number" && !isNaN(num)) return num.toLocaleString();
    if (format === "currency" && !isNaN(num)) return num.toLocaleString(undefined, { minimumFractionDigits: 2 });
    if (format === "percent" && !isNaN(num)) return `${num.toLocaleString(undefined, { minimumFractionDigits: 1 })}%`;
    return String(raw);
  }

  private _renderIcon(): string {
    const icon = this.getAttribute("icon");
    const paths = STAT_ICONS[icon || ""] || "";
    if (!paths) return "";
    return `<div class="p-2 bg-indigo-50 rounded-lg">
      <svg class="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">${paths}</svg>
    </div>`;
  }

  private _renderTrend(): string {
    if (this._trend === null) return "";
    const isUp = this._trend >= 0;
    const colorClass = isUp ? "text-green-600 bg-green-50" : "text-red-600 bg-red-50";
    const arrow = isUp ? TREND_UP : TREND_DOWN;
    return `<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium ${colorClass}">
      ${arrow}${Math.abs(this._trend).toFixed(1)}%
    </span>`;
  }

  private _render() {
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
}

if (!customElements.get("lq-stat-card")) {
  customElements.define("lq-stat-card", LQStatCard);
}
