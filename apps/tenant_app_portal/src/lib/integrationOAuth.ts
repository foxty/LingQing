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

const OAUTH_HINT_PARAM_KEYS = ['oauth_detail', 'oauth_code', 'oauth_reason'] as const

/** Prefer IdP description, then error code, then server reason (callback redirect query). */
export function readOAuthCallbackHint(searchParams: URLSearchParams): string | null {
  for (const key of OAUTH_HINT_PARAM_KEYS) {
    const value = searchParams.get(key)?.trim()
    if (value) {
      return value
    }
  }
  return null
}

/** Dedupe OAuth result toasts (e.g. React Strict Mode double effect). */
export function consumeIntegrationOAuthToastOnce(searchParams: URLSearchParams): boolean {
  const oauth = searchParams.get('oauth')
  if (!oauth || typeof sessionStorage === 'undefined') {
    return true
  }
  const key = `integration-oauth-toast:${oauth}:${OAUTH_HINT_PARAM_KEYS.map((k) => searchParams.get(k) ?? '').join('|')}`
  if (sessionStorage.getItem(key)) {
    return false
  }
  sessionStorage.setItem(key, '1')
  return true
}

export function stripIntegrationOAuthCallbackParams(searchParams: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(searchParams)
  next.delete('oauth')
  next.delete('ds')
  for (const key of OAUTH_HINT_PARAM_KEYS) {
    next.delete(key)
  }
  return next
}
