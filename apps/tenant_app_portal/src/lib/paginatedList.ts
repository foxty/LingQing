export type PaginatedListResponse<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** Fetch every page when a screen needs the full tenant list (cap: page_size 100). */
export async function fetchAllPaginatedPages<T>(
  fetchPage: (page: number, pageSize: number) => Promise<PaginatedListResponse<T>>,
  pageSize = 100
): Promise<T[]> {
  const first = await fetchPage(1, pageSize)
  if (first.total_pages <= 1) {
    return first.items
  }
  const all = [...first.items]
  for (let page = 2; page <= first.total_pages; page += 1) {
    const next = await fetchPage(page, pageSize)
    all.push(...next.items)
  }
  return all
}
