import { useState } from 'react'

export const TENANT_USERS_PAGE_SIZE = 10
export const TENANT_USERS_SEARCH_DEBOUNCE_MS = 300

/** Local UI state for tenant user list: search box and page (server-driven). */
export function useTenantUsersListView() {
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(1)

  return {
    searchQuery,
    setSearchQuery,
    page,
    setPage,
  }
}
