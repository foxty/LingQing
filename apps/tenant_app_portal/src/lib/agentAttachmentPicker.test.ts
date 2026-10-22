import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import {
  agentAttachmentPickerQueryKeys,
  buildAttachmentLabelMap,
  searchAgentAttachmentPicker,
  selectedAttachmentOptions,
} from './agentAttachmentPicker'

vi.mock('./documentCollectionsApi', () => ({
  listDocumentCollections: vi.fn(async () => ({
    items: [{ id: 3, name: 'Sales SSOT', description: null }],
    total: 1,
    page: 1,
    page_size: 20,
    total_pages: 1,
  })),
}))

describe('agentAttachmentPicker', () => {
  it('builds label map from attachment access', () => {
    const map = buildAttachmentLabelMap([
      { resource_type: 'data_source', resource_id: 3, name: 'Sales SSOT', can_read: true },
    ])
    const options = selectedAttachmentOptions([3], 'data_source', map, {})
    expect(options).toEqual([{ id: '3', label: 'Sales SSOT' }])
  })

  it('searchAgentAttachmentPicker uses react-query cache key per query', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const first = await searchAgentAttachmentPicker(
      queryClient,
      1,
      'document_collection',
      'sales'
    )
    expect(first).toEqual([{ id: '3', label: 'Sales SSOT', description: undefined }])

    const cached = queryClient.getQueryData(
      agentAttachmentPickerQueryKeys.search(1, 'document_collection', 'sales')
    )
    expect(cached).toEqual(first)
  })
})
