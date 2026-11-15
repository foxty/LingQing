/** Secret field definitions for per-user integration connection forms. */

export const BYOT_CONNECTOR_AUTH_TYPES = ['api_key', 'bearer', 'basic'] as const
export type ByotConnectorAuthType = (typeof BYOT_CONNECTOR_AUTH_TYPES)[number]

export function dataSourceUserAuthTypeHint(dataSourceType: string): 'db_password' | 'pat' {
  return dataSourceType === 'databricks' ? 'pat' : 'db_password'
}

export function dataSourceSecretFields(type: string): { key: string; label: string }[] {
  if (type === 'databricks') {
    return [{ key: 'password', label: 'Personal access token' }]
  }
  return [
    { key: 'username', label: 'Database username' },
    { key: 'password', label: 'Database password' },
  ]
}

export function isByotConnectorAuthType(authType: string): authType is ByotConnectorAuthType {
  return (BYOT_CONNECTOR_AUTH_TYPES as readonly string[]).includes(authType)
}

export function apiConnectorSecretFields(authType: string): { key: string; label: string }[] {
  if (authType === 'bearer') {
    return [{ key: 'token', label: 'Bearer token' }]
  }
  if (authType === 'api_key') {
    return [{ key: 'api_key', label: 'API key' }]
  }
  if (authType === 'basic') {
    return [
      { key: 'username', label: 'Username' },
      { key: 'password', label: 'Password' },
    ]
  }
  return []
}

export function apiConnectorAuthTypeHint(authType: string): ByotConnectorAuthType | null {
  return isByotConnectorAuthType(authType) ? authType : null
}
