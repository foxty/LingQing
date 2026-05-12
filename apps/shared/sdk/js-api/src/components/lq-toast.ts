/**
 * <lq-toast> — global toast notification system.
 *
 * Programmatic API: window.LQ.toast("Saved!", "success")
 * Types: success | error | info | warning
 *
 * Auto-creates a single container element on first use.
 */

const TOAST_ICONS: Record<string, string> = {
  success: `<svg class="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/></svg>`,
  error: `<svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/></svg>`,
  warning: `<svg class="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>`,
  info: `<svg class="h-5 w-5 text-blue-400" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/></svg>`,
};

const BG_CLASSES: Record<string, string> = {
  success: "bg-green-50 border-green-200",
  error: "bg-red-50 border-red-200",
  warning: "bg-yellow-50 border-yellow-200",
  info: "bg-blue-50 border-blue-200",
};

let containerEl: HTMLDivElement | null = null;

function ensureContainer(): HTMLDivElement {
  if (containerEl && document.body.contains(containerEl)) return containerEl;
  containerEl = document.createElement("div");
  containerEl.id = "lq-toast-container";
  containerEl.className = "fixed top-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm";
  document.body.appendChild(containerEl);
  return containerEl;
}

function showToast(message: string, type: string = "info", durationMs: number = 4000) {
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

// Register globally on LQ
const win = window as Window & { LQ?: Record<string, unknown> };
win.LQ = win.LQ || {};
win.LQ.toast = showToast;

export { showToast };
