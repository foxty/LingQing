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
  getAccessToken?: () =>
    | string
    | null
    | undefined
    | Promise<string | null | undefined>;
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
  mutateInsert(
    table: string,
    data: Record<string, unknown> | Array<Record<string, unknown>>,
  ): Promise<LiveAppMutateResult>;
  mutateUpdateById(
    table: string,
    id: string | number,
    data: Record<string, unknown>,
  ): Promise<LiveAppMutateResult>;
  mutateUpdateRows(
    table: string,
    data: Record<string, unknown>,
    where: Record<string, unknown>,
  ): Promise<LiveAppMutateResult>;
  mutateDeleteById(
    table: string,
    id: string | number,
  ): Promise<LiveAppMutateResult>;
  importCsv(
    table: string,
    file: File | Blob,
    mode?: string,
  ): Promise<LiveAppImportResult>;
  /**
   * Call external API through connector (app-scoped).
   * Authentication managed by platform - no credentials in code.
   * @param operationUid Stable operation identifier (not DB primary key)
   * @param parameters Optional query/path/body parameters
   */
  callApiConnector(
    operationUid: string,
    parameters?: ApiOperationCallParameters,
  ): Promise<ApiExecutionResult>;
}

type LQRuntime = {
  liveApp?: LiveAppClient;
  createLiveAppClient?: (options?: LiveAppClientOptions) => LiveAppClient;
};

function parseContextFromPath(location?: Location): {
  appId: number | null;
  environment: string | null;
  basePrefix: string;
} {
  const match = (location?.pathname || "").match(
    /(\/api)?\/apps\/(\d+)\/([A-Za-z0-9_-]+)\/(entry|embed)$/,
  );
  if (!match) return { appId: null, environment: null, basePrefix: "" };
  const value = Number(match[2]);
  if (!Number.isFinite(value)) {
    return { appId: null, environment: null, basePrefix: "" };
  }
  return {
    appId: value,
    environment: match[3] || null,
    basePrefix: match[1] || "",
  };
}

const LQ_ENV_BADGE_STYLE_ID = "lq-env-badge-styles";

function ensureLiveAppEnvBadgeStyles(): void {
  if (
    typeof document === "undefined" ||
    document.getElementById(LQ_ENV_BADGE_STYLE_ID)
  )
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

/**
 * Fixed bottom-center one-line badge for dev/test only (prod: none). Pure overlay — no layout impact.
 */
function scheduleLiveAppEnvironmentBanner(rawEnv: string | null): void {
  if (typeof document === "undefined") return;
  const normalized = (rawEnv || "").trim().toLowerCase();
  if (normalized !== "dev" && normalized !== "test") return;

  const inject = (): void => {
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
    banner.setAttribute("aria-label", `Environment: ${label} — not production`);
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
      border: border,
      boxShadow: "0 4px 14px rgba(0,0,0,0.1)",
      pointerEvents: "none",
      userSelect: "none",
    });

    const dot = document.createElement("span");
    dot.className = "lq-env-dot";
    dot.setAttribute("aria-hidden", "true");
    Object.assign(dot.style, {
      width: "8px",
      height: "8px",
      borderRadius: "50%",
      background: dotColor,
      flexShrink: "0",
    });

    const text = document.createElement("span");
    text.textContent = `${label} · Not Production`;

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

function createRuntimeError(
  status: number,
  payload: {
    message?: string;
    detail?: string;
    code?: string;
    details?: Record<string, unknown>;
    request_id?: string;
  } | null,
): LiveAppRuntimeError {
  const message = payload?.message || payload?.detail || "Request failed";
  const error = new Error(message) as LiveAppRuntimeError;
  error.status = status;
  error.code = payload?.code || "UNKNOWN_ERROR";
  error.details = payload?.details || {};
  error.requestId = payload?.request_id || "";
  return error;
}

/**
 * Create one live app SDK client.
 */
export function createLiveAppClient(
  options?: LiveAppClientOptions,
): LiveAppClient {
  const parsedContext = parseContextFromPath(
    typeof window !== "undefined" ? window.location : undefined,
  );
  let appId = options?.appId ?? parsedContext?.appId ?? null;
  let environment = options?.environment ?? parsedContext?.environment ?? null;
  const baseUrl = options?.baseUrl ?? parsedContext?.basePrefix ?? "";
  const getAccessToken = options?.getAccessToken;

  async function request(path: string, init: RequestInit): Promise<unknown> {
    const headers = new Headers(init.headers || undefined);
    if (getAccessToken) {
      const token = await getAccessToken();
      if (token && token.trim()) {
        headers.set("Authorization", `Bearer ${token.trim()}`);
      }
    }
    const resp = await fetch(baseUrl + path, {
      ...init,
      headers,
      credentials: "same-origin",
    });
    let payload: unknown = null;
    try {
      payload = await resp.json();
    } catch (_e) {
      payload = null;
    }
    if (!resp.ok) {
      throw createRuntimeError(
        resp.status,
        payload as {
          message?: string;
          detail?: string;
          code?: string;
          details?: Record<string, unknown>;
          request_id?: string;
        } | null,
      );
    }
    if (payload && typeof payload === "object" && "data" in payload) {
      return (payload as { data: unknown }).data;
    }
    return payload;
  }

  function requireAppId(): number {
    if (!appId)
      throw new Error(
        "Live app id is required. Pass appId explicitly when creating sdk client.",
      );
    return appId;
  }

  function requireEnvironment(): string {
    if (!environment || !environment.trim()) {
      throw new Error(
        "Live app environment is required. Pass environment explicitly when creating sdk client.",
      );
    }
    return environment.trim();
  }

  scheduleLiveAppEnvironmentBanner(environment);

  return {
    setAppId(value: number): void {
      appId = Number(value);
    },
    setEnvironment(value: string): void {
      environment = value;
    },
    query(sql: string): Promise<LiveAppQueryResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sql }),
        },
      ) as Promise<LiveAppQueryResult>;
    },
    mutateInsert(
      table: string,
      data: Record<string, unknown> | Array<Record<string, unknown>>,
    ): Promise<LiveAppMutateResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation: "insert", table, data }),
        },
      ) as Promise<LiveAppMutateResult>;
    },
    mutateUpdateById(
      table: string,
      id: string | number,
      data: Record<string, unknown>,
    ): Promise<LiveAppMutateResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation: "update_by_id", table, id, data }),
        },
      ) as Promise<LiveAppMutateResult>;
    },
    mutateUpdateRows(
      table: string,
      data: Record<string, unknown>,
      where: Record<string, unknown>,
    ): Promise<LiveAppMutateResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation: "update", table, data, where }),
        },
      ) as Promise<LiveAppMutateResult>;
    },
    mutateDeleteById(
      table: string,
      id: string | number,
    ): Promise<LiveAppMutateResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/mutate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation: "delete_by_id", table, id }),
        },
      ) as Promise<LiveAppMutateResult>;
    },
    importCsv(
      table: string,
      file: File | Blob,
      mode?: string,
    ): Promise<LiveAppImportResult> {
      const form = new FormData();
      form.append("table", table);
      form.append("mode", mode || "append");
      form.append("file", file);
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/data/import`,
        {
          method: "POST",
          body: form,
        },
      ) as Promise<LiveAppImportResult>;
    },
    callApiConnector(
      operationUid: string,
      parameters?: ApiOperationCallParameters,
    ): Promise<ApiExecutionResult> {
      return request(
        `/apps/v1/${requireAppId()}/${requireEnvironment()}/api-connectors/${operationUid}/call`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ parameters: parameters || {} }),
        },
      ) as Promise<ApiExecutionResult>;
    },
  };
}

if (typeof window !== "undefined") {
  const runtime = window as Window & { LQ?: LQRuntime };
  runtime.LQ = runtime.LQ || {};
  runtime.LQ.createLiveAppClient =
    runtime.LQ.createLiveAppClient || createLiveAppClient;
}

// ---------------------------------------------------------------------------
// Built-in components — registered as custom elements on import.
// Styling: use Tailwind CSS utility classes (auto-injected).
// Reactivity: use Alpine.js v3 x-data/x-init/x-for/x-text/x-show/@click (auto-injected).
// ---------------------------------------------------------------------------
import "./components/lq-toast";
import "./components/lq-page-shell";
import "./components/lq-data-table";
import "./components/lq-form";
import "./components/lq-stat-card";
import "./components/lq-import";

/** Show a toast notification. Types: "success", "error", "info", "warning". Auto-dismisses after ~4s. */
export { showToast } from "./components/lq-toast";
export type { LQNavItem } from "./components/lq-page-shell";
export type { LQColumnDef } from "./components/lq-data-table";
export type { LQFieldDef } from "./components/lq-form";
