/**
 * Document file type constants
 * Must match backend RAG manager supported types
 */

export const SUPPORTED_DOCUMENT_EXTENSIONS = [
  '.pdf',
  '.doc',
  '.docx',
  '.ppt',
  '.pptx',
  '.html',
  '.htm',
  '.md',
  '.xlsx',
  '.xls',
] as const

export const SUPPORTED_DOCUMENT_TYPES_DESCRIPTION =
  'PDF, Word (.doc/.docx), PowerPoint (.ppt/.pptx), HTML, Markdown (.md), Excel (.xls/.xlsx)'

// For HTML input accept attribute
export const ACCEPT_FILE_TYPES = SUPPORTED_DOCUMENT_EXTENSIONS.join(',')

/**
 * Validate if a file has supported extension
 */
export function isValidFileType(filename: string): boolean {
  const ext = filename.toLowerCase().match(/\.[^.]+$/)?.[0]
  return ext ? SUPPORTED_DOCUMENT_EXTENSIONS.includes(ext as any) : false
}

/**
 * Get file extension from filename
 */
export function getFileExtension(filename: string): string | null {
  return filename.toLowerCase().match(/\.[^.]+$/)?.[0] || null
}

