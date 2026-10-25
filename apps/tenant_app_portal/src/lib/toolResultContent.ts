export type ToolResultPanelFormat =
  | { kind: 'markdown'; markdown: string }
  | { kind: 'json'; json: string }
  | { kind: 'text'; text: string }

/** Choose markdown vs pretty JSON vs plain text for the tool detail panel. */
export function formatToolResultPanelDisplay(content: string): ToolResultPanelFormat {
  const trimmed = content.trim()
  if (trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed) as { markdown?: unknown }
      if (typeof parsed.markdown === 'string' && parsed.markdown.trim()) {
        return { kind: 'markdown', markdown: parsed.markdown }
      }
      return { kind: 'json', json: JSON.stringify(parsed, null, 2) }
    } catch {
      /* fall through */
    }
  }
  if (trimmed.startsWith('[')) {
    try {
      return { kind: 'json', json: JSON.stringify(JSON.parse(trimmed), null, 2) }
    } catch {
      /* fall through */
    }
  }
  return { kind: 'text', text: content }
}

/** Shared monospace block (parameters + JSON results). */
export const TOOL_PANEL_MONO_CLASS =
  'font-mono text-xs leading-relaxed overflow-x-auto whitespace-pre-wrap break-words text-foreground'

/** Compact markdown in tool panels — matches ``text-xs`` mono blocks. */
export const TOOL_PANEL_MARKDOWN_CLASS =
  'max-w-none text-xs leading-relaxed prose-sm prose-p:my-0.5 prose-p:text-xs prose-headings:text-xs prose-li:text-xs prose-pre:text-xs prose-pre:my-1'
