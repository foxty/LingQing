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

const NAV_ICONS: Record<string, string> = {
  "chart-bar": `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z"/>`,
  users: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/>`,
  cog: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>`,
  package: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>`,
  table: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M12 10.875c-.621 0-1.125.504-1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0v-1.5"/>`,
  home: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/>`,
  upload: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>`,
  document: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>`,
};

function renderIcon(name: string | undefined): string {
  const paths = NAV_ICONS[name || "document"] || NAV_ICONS["document"];
  return `<svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">${paths}</svg>`;
}

export class LQPageShell extends LQBaseElement {
  private _navItems: LQNavItem[] = [];
  private _currentRoute: string = "";
  private _sidebarCollapsed: boolean = false;

  connectedCallback() {
    this.style.display = "block";
    // Hide raw children until shell is built
    Array.from(this.querySelectorAll<HTMLElement>("[data-route]")).forEach(
      (el) => (el.style.display = "none"),
    );
    const init = () => {
      this._navItems = this.parseJsonAttr<LQNavItem[]>("nav-items", []);
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

  private _onHashChange = () => {
    this._currentRoute = this._routeFromHash() || this._defaultRoute();
    this._showRoute(this._currentRoute);
    this._updateActiveNav();
  };

  private _routeFromHash(): string {
    const hash = window.location.hash.replace(/^#\/?/, "");
    return hash.split("?")[0] || "";
  }

  private _defaultRoute(): string {
    const def = this._navItems.find((n) => n.default);
    return def?.route || this._navItems[0]?.route || "";
  }

  private _showRoute(route: string) {
    const pages = this.querySelectorAll<HTMLElement>("[data-route]");
    pages.forEach((page) => {
      page.style.display = page.dataset.route === route ? "" : "none";
    });
  }

  private _updateActiveNav() {
    const links = this.querySelectorAll<HTMLElement>("[data-nav-route]");
    links.forEach((link) => {
      const isActive = link.dataset.navRoute === this._currentRoute;
      link.classList.toggle("bg-indigo-50", isActive);
      link.classList.toggle("text-indigo-700", isActive);
      link.classList.toggle("text-gray-700", !isActive);
    });
  }

  private _toggleSidebar = () => {
    this._sidebarCollapsed = !this._sidebarCollapsed;
    const sidebar = this.querySelector<HTMLElement>("#lq-sidebar");
    if (sidebar) {
      sidebar.classList.toggle("w-64", !this._sidebarCollapsed);
      sidebar.classList.toggle("w-16", this._sidebarCollapsed);
    }
    const labels = this.querySelectorAll<HTMLElement>(".lq-nav-label");
    labels.forEach((l) => (l.style.display = this._sidebarCollapsed ? "none" : ""));
    const title = this.querySelector<HTMLElement>("#lq-sidebar-title");
    if (title) title.style.display = this._sidebarCollapsed ? "none" : "";
  };

  private _render() {
    const appName = this.getAttribute("app-name") || "App";
    const navHtml = this._navItems
      .map(
        (item) => `
      <a href="#/${item.route}" data-nav-route="${item.route}"
         class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-gray-100 ${
           item.route === this._currentRoute ? "bg-indigo-50 text-indigo-700" : "text-gray-700"
         }">
        ${renderIcon(item.icon)}
        <span class="lq-nav-label">${item.label}</span>
      </a>`,
      )
      .join("\n");

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

    const contentSlot = shell.querySelector("#lq-page-content")!;
    const pages = Array.from(this.querySelectorAll<HTMLElement>("[data-route]"));
    pages.forEach((page) => contentSlot.appendChild(page));

    this.innerHTML = "";
    this.appendChild(shell);

    this.querySelector("#lq-sidebar-toggle")?.addEventListener("click", this._toggleSidebar);
  }
}

if (!customElements.get("lq-page-shell")) {
  customElements.define("lq-page-shell", LQPageShell);
}
