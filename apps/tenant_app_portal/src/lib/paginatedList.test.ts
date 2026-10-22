import { describe, expect, it, vi } from 'vitest'
import { fetchAllPaginatedPages, type PaginatedListResponse } from './paginatedList'

describe('fetchAllPaginatedPages', () => {
  it('merges all pages when total_pages > 1', async () => {
    const fetchPage = vi.fn(
      async (page: number, pageSize: number): Promise<PaginatedListResponse<{ id: number }>> => {
        if (page === 1) {
          return { items: [{ id: 1 }], total: 2, page: 1, page_size: pageSize, total_pages: 2 }
        }
        return { items: [{ id: 2 }], total: 2, page: 2, page_size: pageSize, total_pages: 2 }
      }
    )

    const all = await fetchAllPaginatedPages(fetchPage, 1)
    expect(all).toEqual([{ id: 1 }, { id: 2 }])
    expect(fetchPage).toHaveBeenCalledTimes(2)
  })

  it('returns first page only when total_pages is 1', async () => {
    const fetchPage = vi.fn(async (): Promise<PaginatedListResponse<{ id: number }>> => ({
      items: [{ id: 9 }],
      total: 1,
      page: 1,
      page_size: 100,
      total_pages: 1,
    }))

    const all = await fetchAllPaginatedPages(fetchPage)
    expect(all).toEqual([{ id: 9 }])
    expect(fetchPage).toHaveBeenCalledTimes(1)
  })
})
