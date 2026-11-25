import { afterEach, describe, expect, it, vi } from 'vitest'

describe('integrationOAuth redirect URI builder', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('uses absolute backend URL when configured', async () => {
    vi.doMock('@/lib/config', () => ({
      default: { backendUrl: 'https://api.example.test/' },
    }))
    const { getDefaultIntegrationOAuthRedirectUri, INTEGRATION_OAUTH_CALLBACK_PATH } = await import(
      './integrationOAuth'
    )
    expect(getDefaultIntegrationOAuthRedirectUri()).toBe(
      `https://api.example.test${INTEGRATION_OAUTH_CALLBACK_PATH}`,
    )
  })

  it('joins relative backend prefix with current origin', async () => {
    vi.stubGlobal('window', { location: { origin: 'https://portal.example.test' } })
    vi.doMock('@/lib/config', () => ({
      default: { backendUrl: '/api' },
    }))
    const { getIntegrationOAuthRedirectUri, INTEGRATION_OAUTH_CALLBACK_PATH } = await import(
      './integrationOAuth'
    )
    expect(getIntegrationOAuthRedirectUri(INTEGRATION_OAUTH_CALLBACK_PATH)).toBe(
      'https://portal.example.test/api/integrations/oauth/callback',
    )
  })
})
