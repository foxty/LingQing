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

type ImportState = "idle" | "uploading" | "success" | "error";

export class LQImport extends LQBaseElement {
  private _state: ImportState = "idle";
  private _file: File | null = null;
  private _resultMessage = "";

  connectedCallback() {
    this._render();
  }

  private get _table(): string {
    return this.getAttribute("table") || "";
  }

  private get _mode(): string {
    return this.getAttribute("mode") || "append";
  }

  private get _accept(): string {
    return this.getAttribute("accept") || ".csv";
  }

  private get _label(): string {
    return this.getAttribute("label") || "Import CSV";
  }

  private _formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private async _handleUpload() {
    if (!this._file || !this._table) return;

    this._state = "uploading";
    this._render();

    try {
      const result = await this.client.importCsv(this._table, this._file, this._mode);
      this._resultMessage = `Imported ${result.imported_rows} rows into "${result.table}"`;
      this._state = "success";
      this.toast(this._resultMessage, "success");

      this.dispatchEvent(new CustomEvent("lq-import-complete", {
        detail: { table: result.table, file_name: result.file_name, imported_rows: result.imported_rows, mode: this._mode },
      }));

      const onSuccess = this.getAttribute("on-success");
      if (onSuccess) {
        const [eventName, targetId] = onSuccess.split(":");
        if (eventName && targetId) {
          document.getElementById(targetId)?.dispatchEvent(new Event(eventName));
        }
      }
    } catch (err: unknown) {
      this._resultMessage = (err as Error).message || "Import failed";
      this._state = "error";
      this.toast(this._resultMessage, "error");
    } finally {
      this._render();
    }
  }

  private _reset() {
    this._state = "idle";
    this._file = null;
    this._resultMessage = "";
    this._render();
  }

  private _onFileSelected(file: File | null) {
    if (!file) return;
    this._file = file;
    this._state = "idle";
    this._render();
  }

  private _render() {
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
                  <p class="text-sm font-medium text-gray-900">${this._file!.name}</p>
                  <p class="text-xs text-gray-500">${this._formatSize(this._file!.size)}</p>
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

  private _renderResult(): string {
    const isSuccess = this._state === "success";
    const bgColor = isSuccess ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200";
    const iconColor = isSuccess ? "text-green-500" : "text-red-500";
    const icon = isSuccess
      ? `<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/>`
      : `<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/>`;

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

  private _bindEvents() {
    const dropzone = this.querySelector<HTMLElement>("[data-lq-dropzone]");
    const fileInput = this.querySelector<HTMLInputElement>("[data-lq-file-input]");

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
        const file = (e as DragEvent).dataTransfer?.files[0] || null;
        this._onFileSelected(file);
      });
    }

    fileInput?.addEventListener("change", () => {
      this._onFileSelected(fileInput.files?.[0] || null);
    });

    const modeSelect = this.querySelector<HTMLSelectElement>("[data-lq-mode]");
    modeSelect?.addEventListener("change", () => {
      this.setAttribute("mode", modeSelect.value);
    });

    this.querySelector("[data-lq-action='upload']")?.addEventListener("click", () => this._handleUpload());
    this.querySelector("[data-lq-action='clear']")?.addEventListener("click", () => this._reset());
    this.querySelector("[data-lq-action='reset']")?.addEventListener("click", () => this._reset());
  }
}

if (!customElements.get("lq-import")) {
  customElements.define("lq-import", LQImport);
}
