import type { ApiConnector } from '@/lib/apiConnectorApi'

export function packIdFromRef(packRef: string | null | undefined): string | null {
  if (!packRef?.trim()) return null
  const at = packRef.indexOf('@')
  return at === -1 ? packRef.trim() : packRef.slice(0, at).trim()
}

export function isPackInstalledForTenant(connectors: ApiConnector[], packId: string): boolean {
  const normalized = packId.trim()
  if (!normalized) return false
  return connectors.some((connector) => packIdFromRef(connector.pack_ref) === normalized)
}