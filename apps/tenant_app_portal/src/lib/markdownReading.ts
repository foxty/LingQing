/** Markdown helpers shared by table rendering. */

const GFM_TABLE_DIVIDER = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/

export function hasMarkdownTable(content: string): boolean {
  const lines = content.split('\n')
  for (let i = 0; i < lines.length - 1; i += 1) {
    const line = lines[i]
    const next = lines[i + 1]
    if (!line.includes('|')) continue
    if (GFM_TABLE_DIVIDER.test(next)) return true
  }
  return false
}

export function isNumericMarkdownCell(text: string): boolean {
  const value = text.trim()
  if (!value) return false
  return /^[$€£¥]?\s*[\d,.\s%-]+$/.test(value) || /^[+-]?\d[\d,.\s]*%?$/.test(value)
}
