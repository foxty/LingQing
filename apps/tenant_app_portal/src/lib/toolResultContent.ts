/** Normalize tool message content for markdown display (chat tool call panel). */

export function toolResultMarkdownForDisplay(content: string): string {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) {
    return content
  }
  try {
    const parsed = JSON.parse(trimmed) as { markdown?: unknown }
    if (typeof parsed.markdown === 'string' && parsed.markdown.trim()) {
      return parsed.markdown
    }
  } catch {
    /* keep original */
  }
  return content
}
