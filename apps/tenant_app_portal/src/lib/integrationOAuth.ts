import config from '@/lib/config'

/** Shared backend OAuth callback route for user-scoped integrations (connectors, data sources). */
export const INTEGRATION_OAUTH_CALLBACK_PATH = '/integrations/oauth/callback'

/**
 * Absolute callback URL for OAuth app registration.
 * Uses VITE_BACKEND_URL when absolute; otherwise current origin + relative API prefix.
 */
export function getIntegrationOAuthRedirectUri(path: string): string {
  const base = config.backendUrl.replace(/\/$/, '')
  if (/^https?:\/\//i.test(base)) {
    return `${base}${path}`
  }
  const prefix = base.startsWith('/') ? base : `/${base}`
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}${prefix}${path}`
}

export function getDefaultIntegrationOAuthRedirectUri(): string {
  return getIntegrationOAuthRedirectUri(INTEGRATION_OAUTH_CALLBACK_PATH)
}
