import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const GFM_TABLE_LINE = /^\|[^\n]+\|\s*$/
const GFM_TABLE_DIVIDER = /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|\s*$/

function isGfmTableBlock(lines: string[], start: number): number | null {
  if (start + 1 >= lines.length) return null
  if (!GFM_TABLE_LINE.test(lines[start]) || !GFM_TABLE_DIVIDER.test(lines[start + 1])) {
    return null
  }
  let end = start + 2
  while (end < lines.length && GFM_TABLE_LINE.test(lines[end])) {
    end += 1
  }
  return end
}

function extractGfmTableBlocks(content: string): { body: string; tables: string[] } {
  const lines = content.split('\n')
  const tables: string[] = []
  const out: string[] = []
  let index = 0

  while (index < lines.length) {
    const blockEnd = isGfmTableBlock(lines, index)
    if (blockEnd != null) {
      const block = lines.slice(index, blockEnd).join('\n')
      tables.push(block)
      out.push(`<<<LQ_TABLE_${tables.length - 1}>>>`)
      index = blockEnd
      continue
    }
    out.push(lines[index])
    index += 1
  }

  return { body: out.join('\n'), tables }
}

function restoreGfmTableBlocks(body: string, tables: string[]): string {
  return body.replace(/<<<LQ_TABLE_(\d+)>>>/g, (_match, index: string) => {
    const table = tables[Number(index)]
    return table ?? _match
  })
}

/**
 * Preprocesses markdown content to ensure proper spacing between elements.
 * This fixes common issues where LLMs generate markdown without proper blank lines.
 * GFM table blocks are preserved verbatim so list/heading spacing rules cannot split rows.
 */
export function preprocessMarkdown(content: string): string {
  const { body, tables } = extractGfmTableBlocks(content)
  const spaced = body
    // Add blank line before headings (if not already present)
    .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
    // Add blank line after headings (if followed by list or text without blank line)
    .replace(/(#{1,6}\s+[^\n]+)\n([^#\n])/g, '$1\n\n$2')
    // Add blank line before lists (-, *, +, or numbered lists) at line start only
    .replace(/([^\n])\n(?=[-*+]\s|[0-9]+\.\s)/gm, '$1\n\n')
    // Add blank line after list items when the next line is not another list item
    .replace(/^([-*+]\s[^\n]+)\n(?![-*+]\s|[0-9]+\.\s)/gm, '$1\n\n')
    .replace(/^([0-9]+\.\s[^\n]+)\n(?![-*+]\s|[0-9]+\.\s)/gm, '$1\n\n')
    // Add blank line before images
    .replace(/([^\n])\n(\!\[)/g, '$1\n\n$2')
    // Add blank line after images
    .replace(/(\!\[[^\]]*\]\([^)]+\))\n([^\n])/g, '$1\n\n$2')
    // Add blank line before code blocks
    .replace(/([^\n])\n(```)/g, '$1\n\n$2')
    // Add blank line after code blocks
    .replace(/(```)\n([^`\n])/g, '$1\n\n$2')

  return restoreGfmTableBlocks(spaced, tables)
}

/**
 * Truncates a string to show first and last parts with ellipsis in the middle.
 * Useful for displaying long IDs while maintaining readability.
 *
 * @param str - The string to truncate
 * @param startLength - Number of characters to show at the start (default: 8)
 * @param endLength - Number of characters to show at the end (default: 4)
 * @returns Truncated string or original if shorter than threshold
 */
export function truncateMiddle(str: string, startLength = 8, endLength = 4): string {
  const totalLength = startLength + endLength
  if (str.length <= totalLength + 3) return str
  return `${str.slice(0, startLength)}...${str.slice(-endLength)}`
}

/**
 * Copies text to clipboard.
 *
 * @param text - The text to copy
 * @returns Promise that resolves to true if successful, false otherwise
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (err) {
    console.error('Failed to copy to clipboard:', err)
    return false
  }
}
