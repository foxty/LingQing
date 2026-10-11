/** True when the browser or network dropped the SSE connection (not an app-level error payload). */
export function isStreamTransportError(message: string): boolean {
  const normalized = message.trim().toLowerCase()
  if (!normalized) {
    return true
  }
  return (
    normalized === 'network error' ||
    normalized.includes('failed to fetch') ||
    normalized.includes('networkerror') ||
    normalized.includes('err_network') ||
    normalized.includes('network_io_suspended')
  )
}
