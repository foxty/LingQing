import api from './api'

export interface DocumentCollection {
  id: number
  tenant_id: number
  name: string
  description: string | null
  owner_id: number
  owner_name: string | null
  document_count: number
  created_at: string
  updated_at: string
}

export interface DocumentCollectionCreate {
  name: string
  description?: string | null
}

export interface DocumentCollectionUpdate {
  name?: string
  description?: string | null
}

export async function listDocumentCollections(): Promise<DocumentCollection[]> {
  const response = await api.get<DocumentCollection[]>('/document-collections')
  return response.data
}

export async function createDocumentCollection(
  payload: DocumentCollectionCreate
): Promise<DocumentCollection> {
  const response = await api.post<DocumentCollection>('/document-collections', payload)
  return response.data
}

export async function updateDocumentCollection(
  collectionId: number,
  payload: DocumentCollectionUpdate
): Promise<DocumentCollection> {
  const response = await api.put<DocumentCollection>(`/document-collections/${collectionId}`, payload)
  return response.data
}

export async function deleteDocumentCollection(collectionId: number): Promise<void> {
  await api.delete(`/document-collections/${collectionId}`)
}

export interface DocumentQueueResponse {
  queued_count: number
  skipped_count: number
}

export async function reparseDocumentCollection(
  collectionId: number
): Promise<DocumentQueueResponse> {
  const response = await api.post<DocumentQueueResponse>(
    `/document-collections/${collectionId}/reparse`
  )
  return response.data
}

export async function reindexDocumentCollection(
  collectionId: number
): Promise<DocumentQueueResponse> {
  const response = await api.post<DocumentQueueResponse>(
    `/document-collections/${collectionId}/reindex`
  )
  return response.data
}
