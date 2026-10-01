/**
 * Documents API Service
 * Handles all document-related API calls
 */

import api from './api'
import type { ApiDocument } from '@/types'

/** Derive a browser URL for a Google Drive source file. */
export function driveFileViewUrl(externalFileId: string): string {
  return `https://drive.google.com/file/d/${externalFileId}/view`
}

/**
 * Paginated response from API
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * Get documents with pagination
 */
export async function getDocuments(
  page: number = 1,
  pageSize: number = 10,
  query?: string,
  collectionId?: number
): Promise<PaginatedResponse<ApiDocument>> {
  const response = await api.get<PaginatedResponse<ApiDocument>>('/documents', {
    params: {
      page,
      page_size: pageSize,
      ...(query ? { query } : {}),
      ...(collectionId ? { collection_id: collectionId } : {}),
    },
  })
  return response.data
}

/**
 * Delete one or multiple documents by IDs
 * Uses the same endpoint for both single and batch deletion
 */
export async function deleteDocuments(documentIds: number[]): Promise<void> {
  if (documentIds.length === 0) return

  const params = new URLSearchParams()
  documentIds.forEach((id) => params.append('doc_ids', id.toString()))

  await api.delete(`/documents?${params.toString()}`)
}

/**
 * Delete a single document by ID
 * Convenience wrapper around deleteDocuments
 */
export async function deleteDocument(documentId: number): Promise<void> {
  await deleteDocuments([documentId])
}

/**
 * Upload a document file
 */
export async function uploadDocument(file: File, collectionId: number): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('collection_id', String(collectionId))

  await api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export async function reparseDocument(documentId: number): Promise<ApiDocument> {
  const response = await api.post<ApiDocument>(`/documents/${documentId}/reparse`)
  return response.data
}

export async function reindexDocument(documentId: number): Promise<ApiDocument> {
  const response = await api.post<ApiDocument>(`/documents/${documentId}/reindex`)
  return response.data
}

export interface DocumentQueueResponse {
  queued_count: number
  skipped_count: number
}

export interface ApiParsedBlock {
  type: string
  text?: string | null
  caption?: string | null
  page?: number | null
  uri?: string | null
}

export interface ApiParsedDocument {
  document_id: number
  filename: string
  parser?: string | null
  parsed_at?: string | null
  parse_error?: string | null
  block_count: number
  truncated: boolean
  type_counts: Record<string, number>
  blocks: ApiParsedBlock[]
}

export async function getParsedDocument(documentId: number): Promise<ApiParsedDocument> {
  const response = await api.get<ApiParsedDocument>(`/documents/${documentId}/parsed`)
  return response.data
}
