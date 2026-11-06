/** Stable React Query keys for tenant user list (settings + usage filters). */

export const tenantUsersListQueryKey = (tenantId: number | undefined) => ['tenant-users', tenantId] as const
