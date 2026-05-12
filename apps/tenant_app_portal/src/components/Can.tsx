import { ReactNode } from 'react'
import { useAuth } from '@/hooks/useAuth'

interface CanProps {
  /**
   * Render children if ANY of these permissions are present
   * Example: any={["documents.read", "documents.write"]}
   */
  any?: string[]

  /**
   * Render children if ALL of these permissions are present
   * Example: all={["dashboards.write", "dashboards.sql.execute"]}
   */
  all?: string[]

  /**
   * Negate the permission check (render if permission is NOT present)
   * Example: not any={["admin"]} renders children if user is not admin
   */
  not?: boolean

  /**
   * Fallback UI to render if permission check fails
   * Example: fallback={<AccessDenied />}
   */
  fallback?: ReactNode

  children: ReactNode
}

/**
 * Reusable permission gate component for hiding/showing UI based on permissions.
 *
 * Usage:
 * <Can any={["documents.read", "documents.write"]}>
 *   <DocumentsList />
 * </Can>
 *
 * <Can all={["dashboards.write"]}>
 *   <CreateDashboardButton />
 * </Can>
 *
 * <Can not any={["documents.write"]}>
 *   <ReadOnlyBanner />
 * </Can>
 */
export function Can({ any, all, not = false, fallback = null, children }: CanProps) {
  const { hasAny, hasAll } = useAuth()

  let hasPermission = true

  if (any) {
    hasPermission = hasAny(any)
  } else if (all) {
    hasPermission = hasAll(all)
  }

  if (not) {
    hasPermission = !hasPermission
  }

  return hasPermission ? <>{children}</> : <>{fallback}</>
}
