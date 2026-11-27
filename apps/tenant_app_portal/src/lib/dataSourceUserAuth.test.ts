import { describe, expect, it } from 'vitest'

import {
  DATABRICKS_USER_AUTH_OAUTH2,
  DATABRICKS_USER_AUTH_PAT,
  applyOidcUrlsFromHost,
  attachDatabricksUserCredentialAuth,
  databricksOidcUrls,
  defaultDatabricksOAuth2Config,
  oauth2ConfigFromDataSourceConfig,
} from '@/lib/dataSourceUserAuth'
import { createDefaultOAuth2Config } from '@/components/api-connector/types'
import type { SecretFieldBinding } from '@/lib/sensitiveCredential'

describe('databricksOidcUrls', () => {
  it('builds OIDC URLs from host without scheme', () => {
    const { authorizeUrl, tokenUrl } = databricksOidcUrls('adb-example.azuredatabricks.net')
    expect(authorizeUrl).toBe('https://adb-example.azuredatabricks.net/oidc/v1/authorize')
    expect(tokenUrl).toBe('https://adb-example.azuredatabricks.net/oidc/v1/token')
  })

  it('returns empty urls when host blank', () => {
    expect(databricksOidcUrls('  ')).toEqual({ authorizeUrl: '', tokenUrl: '' })
  })
})

describe('applyOidcUrlsFromHost', () => {
  it('merges urls into oauth form config', () => {
    const base = defaultDatabricksOAuth2Config()
    const next = applyOidcUrlsFromHost(base, 'adb-example.azuredatabricks.net')
    expect(next.authorizeUrl).toContain('/oidc/v1/authorize')
    expect(next.tokenUrl).toContain('/oidc/v1/token')
  })
})

describe('oauth2ConfigFromDataSourceConfig', () => {
  it('reads persisted user_oauth block', () => {
    const cfg = oauth2ConfigFromDataSourceConfig(
      {
        user_oauth: {
          client_id: 'cid',
          redirect_uri: 'https://app/cb',
          authorize_url: 'https://adb/oidc/v1/authorize',
          token_url: 'https://adb/oidc/v1/token',
          scopes: ['sql', 'offline_access'],
        },
      },
      'adb.example.net',
    )
    expect(cfg.clientId).toBe('cid')
    expect(cfg.scopes).toEqual(['sql', 'offline_access'])
    expect(cfg.redirectUri).toBe('https://app/cb')
  })

  it('falls back to default redirect when block missing', () => {
    const cfg = oauth2ConfigFromDataSourceConfig(undefined, 'adb.example.net')
    expect(cfg.redirectUri).toBe(createDefaultOAuth2Config().redirectUri)
  })
})

describe('attachDatabricksUserCredentialAuth', () => {
  const clientSecret: SecretFieldBinding = {
    mode: 'create',
    stored: false,
    editing: true,
    draft: 'app-secret',
  }

  it('sets pat auth type without user_oauth block', () => {
    const out = attachDatabricksUserCredentialAuth(
      { host: 'adb.example.net' },
      {
        userCredentialAuthType: DATABRICKS_USER_AUTH_PAT,
        oauth2Config: defaultDatabricksOAuth2Config('adb.example.net'),
        clientSecret,
      },
    )
    expect(out.user_credential_auth_type).toBe(DATABRICKS_USER_AUTH_PAT)
    expect(out.user_oauth).toBeUndefined()
  })

  it('builds user_oauth for oauth2 with scopes and secret binding', () => {
    const oauth2 = {
      ...defaultDatabricksOAuth2Config('adb.example.net'),
      clientId: 'cid',
      redirectUri: 'https://app/cb',
      scopes: ['sql', 'offline_access'],
    }
    const out = attachDatabricksUserCredentialAuth(
      { host: 'adb.example.net' },
      {
        userCredentialAuthType: DATABRICKS_USER_AUTH_OAUTH2,
        oauth2Config: oauth2,
        clientSecret,
      },
    )
    expect(out.user_credential_auth_type).toBe(DATABRICKS_USER_AUTH_OAUTH2)
    const block = out.user_oauth as Record<string, unknown>
    expect(block.client_id).toBe('cid')
    expect(block.scopes).toEqual(['sql', 'offline_access'])
    expect(block.client_secret).toBe('app-secret')
  })
})
