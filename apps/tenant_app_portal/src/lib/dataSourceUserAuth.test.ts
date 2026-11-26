import { describe, expect, it } from 'vitest'

import {
  attachDatabricksUserCredentialAuth,
  defaultDatabricksOAuth2Config,
  oauth2ConfigFromDataSourceConfig,
} from '@/lib/dataSourceUserAuth'
import type { SecretFieldBinding } from '@/lib/sensitiveCredential'

const createModeSecret: SecretFieldBinding = {
  mode: 'create',
  stored: false,
  editing: false,
  draft: 'synthetic-secret',
}

describe('dataSourceUserAuth scopes', () => {
  it('defaults new OAuth config without scopes until admin enters them', () => {
    expect(defaultDatabricksOAuth2Config().scopes).toEqual([])
  })

  it('round-trips explicit scopes from stored config', () => {
    const config = {
      user_credential_auth_type: 'oauth2',
      user_oauth: {
        client_id: 'client',
        scopes: ['sql:read:restricted-query', 'offline_access'],
      },
    }
    const loaded = oauth2ConfigFromDataSourceConfig(config)
    expect(loaded.scopes).toEqual(['sql:read:restricted-query', 'offline_access'])
  })

  it('persists scopes array on save', () => {
    const merged = attachDatabricksUserCredentialAuth(
      { host: 'adb-example.azuredatabricks.net' },
      {
        userCredentialAuthType: 'oauth2',
        oauth2Config: {
          ...defaultDatabricksOAuth2Config('adb-example.azuredatabricks.net'),
          clientId: 'c1',
          scopes: ['sql:read:restricted-query'],
        },
        clientSecret: createModeSecret,
      },
    )
    const block = merged.user_oauth as Record<string, unknown>
    expect(block.scopes).toEqual(['sql:read:restricted-query'])
  })
})
