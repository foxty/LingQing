/**
 * Base class for all LQ web components.
 * Provides SDK access, permission checks, and shared rendering helpers.
 */

import type { LiveAppClient } from "../lq-sdk.v1.0";

type LQRuntime = {
  liveApp?: LiveAppClient;
  toast?: (msg: string, type?: string) => void;
};

export abstract class LQBaseElement extends HTMLElement {
  protected _client: LiveAppClient | null = null;

  get client(): LiveAppClient {
    if (!this._client) {
      const lq = (window as Window & { LQ?: LQRuntime }).LQ;
      if (lq?.liveApp) this._client = lq.liveApp;
      else throw new Error("LQ SDK not available. Ensure lq-sdk is loaded before lq-components.");
    }
    return this._client;
  }

  protected parseJsonAttr<T>(name: string, fallback: T): T {
    const raw = this.getAttribute(name);
    if (!raw) return fallback;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return fallback;
    }
  }

  protected toast(message: string, type: string = "info") {
    const lq = (window as Window & { LQ?: LQRuntime }).LQ;
    if (lq?.toast) {
      lq.toast(message, type);
    }
  }

  protected renderLoading(): string {
    return `<div class="flex items-center justify-center py-12">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
    </div>`;
  }

  protected renderError(message: string): string {
    return `<div class="rounded-md bg-red-50 p-4">
      <div class="flex">
        <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/>
        </svg>
        <p class="ml-3 text-sm text-red-800">${message}</p>
      </div>
    </div>`;
  }

  protected renderEmpty(message: string = "No data"): string {
    return `<div class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>
      </svg>
      <p class="mt-2 text-sm text-gray-500">${message}</p>
    </div>`;
  }
}
