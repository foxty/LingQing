export type SsoIconKey = 'google' | 'okta' | 'entra' | 'keycloak'

export function iconKeyForIssuer(issuer?: string | null): SsoIconKey | undefined {
  const normalized = issuer?.toLowerCase().replace(/\/$/, '') ?? ''
  if (!normalized) return undefined
  if (normalized.includes('accounts.google.com')) return 'google'
  if (normalized.includes('okta.com')) return 'okta'
  if (normalized.includes('login.microsoftonline.com') || normalized.includes('microsoftonline.com')) {
    return 'entra'
  }
  if (normalized.includes('/realms/')) return 'keycloak'
  return undefined
}
