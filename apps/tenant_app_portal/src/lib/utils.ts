import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Preprocesses markdown content to ensure proper spacing between elements.
 * This fixes common issues where LLMs generate markdown without proper blank lines.
 */
export function preprocessMarkdown(content: string): string {
  return content
  return (
    content
      // Add blank line before headings (if not already present)
      .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
      // Add blank line after headings (if followed by list or text without blank line)
      .replace(/(#{1,6}\s+[^\n]+)\n([^#\n])/g, '$1\n\n$2')
      // Add blank line before lists (-, *, +, or numbered lists)
      .replace(/([^\n])\n([-*+]\s|[0-9]+\.\s)/g, '$1\n\n$2')
      // Add blank line after lists (when followed by non-list content)
      .replace(/([-*+]\s[^\n]+)\n([^-*+\n])/g, '$1\n\n$2')
      // Add blank line before images
      .replace(/([^\n])\n(\!\[)/g, '$1\n\n$2')
      // Add blank line after images
      .replace(/(\!\[[^\]]*\]\([^)]+\))\n([^\n])/g, '$1\n\n$2')
      // Add blank line before code blocks
      .replace(/([^\n])\n(```)/g, '$1\n\n$2')
      // Add blank line after code blocks
      .replace(/(```)\n([^`\n])/g, '$1\n\n$2')
  )
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
