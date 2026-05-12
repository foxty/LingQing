export interface ScrollAnchor {
  key: string
  offset: number
}

export function captureScrollAnchor(container: HTMLElement): ScrollAnchor | null {
  const containerTop = container.getBoundingClientRect().top

  for (const element of container.querySelectorAll<HTMLElement>('[data-message-key]')) {
    const key = element.dataset.messageKey
    if (!key) {
      continue
    }

    const rect = element.getBoundingClientRect()
    if (rect.bottom > containerTop) {
      return {
        key,
        offset: rect.top - containerTop,
      }
    }
  }

  return null
}

export function restoreScrollAnchor(container: HTMLElement, anchor: ScrollAnchor): boolean {
  const escapedKey =
    typeof CSS !== 'undefined' && 'escape' in CSS
      ? CSS.escape(anchor.key)
      : anchor.key.replace(/"/g, '\\"')
  const element = container.querySelector<HTMLElement>(`[data-message-key="${escapedKey}"]`)
  if (!element) {
    return false
  }

  const containerTop = container.getBoundingClientRect().top
  const delta = element.getBoundingClientRect().top - containerTop - anchor.offset
  container.scrollTop += delta
  return true
}
