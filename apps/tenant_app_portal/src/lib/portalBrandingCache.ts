import type { PortalBranding } from '@/lib/portalBrandingApi'

const STORAGE_PREFIX = 'portal-branding:v1:'

export function readCachedPortalBranding(tenantId: number): PortalBranding | undefined {
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${tenantId}`)
    if (!raw) {
      return undefined
    }
    return JSON.parse(raw) as PortalBranding
  } catch {
    return undefined
  }
}

export function writeCachedPortalBranding(tenantId: number, branding: PortalBranding): void {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${tenantId}`, JSON.stringify(branding))
  } catch {
    // ignore quota / private mode
  }
}
