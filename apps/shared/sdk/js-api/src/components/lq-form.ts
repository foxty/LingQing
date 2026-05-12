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
  type?:
    | "text" | "number" | "email" | "tel" | "textarea"
    | "date" | "datetime" | "time"
    | "select" | "checkbox" | "hidden";
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
  options?: Array<{ value: string; label: string }>;
  /** SQL query to populate select options dynamically. */
  optionsSource?: string;
  /** Column name for option value (default: first column). */
  optionsValueKey?: string;
  /** Column name for option label (default: second column, or first if only one). */
  optionsLabelKey?: string;
}

type FieldErrors = Record<string, string>;

export class LQForm extends LQBaseElement {
  private _fields: LQFieldDef[] = [];
  private _table = "";
  private _recordId: string | null = null;
  private _formData: Record<string, unknown> = {};
  private _errors: FieldErrors = {};
  private _submitting = false;
  private _loading = false;
  private _dynamicOptions: Record<string, Array<{ value: string; label: string }>> = {};

  connectedCallback() {
    this._table = this.getAttribute("table") || "";
    this._recordId = this.getAttribute("record-id") || null;
    this._fields = this.parseJsonAttr<LQFieldDef[]>("fields", []);
    this._initDefaults();
    this._init();
  }

  private async _init() {
    this._loading = true;
    this._render();
    try {
      await this._loadDynamicOptions();
      if (this._recordId) await this._loadRecord();
    } catch (err: unknown) {
      this.toast((err as Error).message || "Failed to load form data", "error");
    } finally {
      this._loading = false;
      this._render();
      this._bindEvents();
    }
  }

  private _initDefaults() {
    for (const f of this._fields) {
      if (f.defaultValue !== undefined) {
        this._formData[f.key] = f.defaultValue;
      } else if (f.type === "checkbox") {
        this._formData[f.key] = false;
      } else {
        this._formData[f.key] = "";
      }
    }
  }

  private async _loadDynamicOptions() {
    const dynamicFields = this._fields.filter((f) => f.optionsSource);
    if (dynamicFields.length === 0) return;

    const results = await Promise.all(
      dynamicFields.map(async (f) => {
        const result = await this.client.query(f.optionsSource!);
        const valIdx = f.optionsValueKey ? result.columns.indexOf(f.optionsValueKey) : 0;
        const lblIdx = f.optionsLabelKey
          ? result.columns.indexOf(f.optionsLabelKey)
          : Math.min(1, result.columns.length - 1);
        return {
          key: f.key,
          options: result.rows.map((row) => ({
            value: String(row[valIdx >= 0 ? valIdx : 0] ?? ""),
            label: String(row[lblIdx >= 0 ? lblIdx : 0] ?? ""),
          })),
        };
      }),
    );
    for (const r of results) this._dynamicOptions[r.key] = r.options;
  }

  private async _loadRecord() {
    const result = await this.client.query(
      `SELECT * FROM ${this._table} WHERE id = ${this._recordId}`,
    );
    if (result.rows.length === 0) {
      this.toast("Record not found", "error");
      return;
    }
    const row = result.rows[0];
    for (const f of this._fields) {
      const colIdx = result.columns.indexOf(f.key);
      if (colIdx >= 0 && row[colIdx] !== null && row[colIdx] !== undefined) {
        this._formData[f.key] = row[colIdx];
      }
    }
  }

  private _getOptions(field: LQFieldDef): Array<{ value: string; label: string }> {
    return this._dynamicOptions[field.key] || field.options || [];
  }

  private _humanize(s: string): string {
    return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // --- Validation ---

  private _validate(): boolean {
    this._errors = {};
    for (const f of this._fields) {
      if (f.type === "hidden") continue;
      const val = this._formData[f.key];
      const strVal = String(val ?? "").trim();

      if (f.required && (val === "" || val === null || val === undefined)) {
        this._errors[f.key] = `${f.label || this._humanize(f.key)} is required`;
        continue;
      }
      if (!strVal) continue;

      if (f.pattern) {
        try {
          if (!new RegExp(f.pattern).test(strVal)) {
            this._errors[f.key] = `Invalid format`;
          }
        } catch { /* invalid regex, skip */ }
      }
      if (f.type === "number" && strVal) {
        const num = Number(val);
        if (isNaN(num)) {
          this._errors[f.key] = "Must be a number";
        } else {
          if (f.min !== undefined && num < Number(f.min)) this._errors[f.key] = `Minimum is ${f.min}`;
          if (f.max !== undefined && num > Number(f.max)) this._errors[f.key] = `Maximum is ${f.max}`;
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

  private async _handleSubmit() {
    this._syncFormInputs();
    if (!this._validate()) {
      this._renderForm();
      return;
    }

    this._submitting = true;
    this._renderForm();

    try {
      const data: Record<string, unknown> = {};
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
    } catch (err: unknown) {
      this.toast((err as Error).message || "Save failed", "error");
    } finally {
      this._submitting = false;
      this._renderForm();
    }
  }

  private _syncFormInputs() {
    for (const f of this._fields) {
      if (f.type === "hidden") continue;
      const input = this.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
        `[data-lq-field="${f.key}"]`,
      );
      if (!input) continue;
      if (f.type === "checkbox") {
        this._formData[f.key] = (input as HTMLInputElement).checked;
      } else {
        this._formData[f.key] = input.value;
      }
    }
  }

  // --- Rendering ---

  private _render() {
    if (this._loading) {
      this.innerHTML = this.renderLoading();
      return;
    }
    this.innerHTML = `<div class="bg-white rounded-lg border border-gray-200 shadow-sm" data-lq-form-root></div>`;
    this._renderForm();
  }

  private _renderForm() {
    const root = this.querySelector("[data-lq-form-root]");
    if (!root) return;

    const layout = this.getAttribute("layout") || "vertical";
    const submitLabel = this.getAttribute("submit-label") || "Save";

    const gridClass =
      layout === "grid-2" ? "grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-4"
      : layout === "grid-3" ? "grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-4"
      : "space-y-4";

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

  private _renderField(field: LQFieldDef, layout: string): string {
    const label = field.label || this._humanize(field.key);
    const error = this._errors[field.key];
    const errorClass = error ? "border-red-300 focus:ring-red-500 focus:border-red-500" : "border-gray-300 focus:ring-indigo-500 focus:border-indigo-500";
    const baseInputClass = `w-full px-3 py-2 text-sm rounded-md border ${errorClass} focus:outline-none focus:ring-2`;
    const val = this._formData[field.key];
    const isHoriz = layout === "horizontal";
    const reqMark = field.required ? `<span class="text-red-500 ml-0.5">*</span>` : "";

    let inputHtml: string;

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
        return isHoriz
          ? `<div class="flex items-center gap-4 py-1">${inputHtml}${this._errorHtml(error)}</div>`
          : `<div>${inputHtml}${this._errorHtml(error)}</div>`;

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

  private _attrConstraints(field: LQFieldDef): string {
    const parts: string[] = [];
    if (field.min !== undefined) parts.push(`min="${this._esc(String(field.min))}"`);
    if (field.max !== undefined) parts.push(`max="${this._esc(String(field.max))}"`);
    if (field.pattern) parts.push(`pattern="${this._esc(field.pattern)}"`);
    if (field.required) parts.push("required");
    return parts.join(" ");
  }

  private _errorHtml(error: string | undefined): string {
    if (!error) return "";
    return `<p class="mt-1 text-xs text-red-600">${this._esc(error)}</p>`;
  }

  private _esc(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  private _bindEvents() {
    this.querySelector("[data-lq-action='submit']")?.addEventListener("click", () => this._handleSubmit());
  }
}

if (!customElements.get("lq-form")) {
  customElements.define("lq-form", LQForm);
}
