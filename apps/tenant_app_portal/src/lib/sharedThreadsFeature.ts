/** Feature flag for shared thread UI (defaults on unless explicitly disabled). */
export function isSharedThreadsUiEnabled(): boolean {
  return import.meta.env.VITE_SHARED_THREADS_ENABLED !== 'false'
}
