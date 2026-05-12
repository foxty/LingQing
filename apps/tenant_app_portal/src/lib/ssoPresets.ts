export interface SsoPreset {
  key: string
  displayName: string
  issuerTemplate: string
  issuerHint: string
  scopes: string[]
}

export const CUSTOM_PRESET_KEY = 'custom'

export const SSO_PRESETS: SsoPreset[] = [
  {
    key: 'google',
    displayName: 'Google',
    issuerTemplate: 'https://accounts.google.com',
    issuerHint:
      'Google OIDC issuer is fixed. Create an OAuth credential in Google Cloud Console (Authorized redirect URI = the Callback URL below).',
    scopes: ['openid', 'email', 'profile'],
  },
  {
    key: 'okta',
    displayName: 'Okta',
    issuerTemplate: 'https://<tenant>.okta.com',
    issuerHint:
      'Replace <tenant> with your Okta org. Create an "Web" app with OIDC in the Okta admin console; set the sign-in redirect URI to the Callback URL below.',
    scopes: ['openid', 'email', 'profile'],
  },
  {
    key: 'entra',
    displayName: 'Microsoft Entra ID',
    issuerTemplate: 'https://login.microsoftonline.com/<tenant-id>/v2.0',
    issuerHint:
      'Replace <tenant-id> with your Entra tenant (GUID or verified domain). Register an app in the Entra portal, add the Callback URL below as a redirect URI.',
    scopes: ['openid', 'email', 'profile'],
  },
  {
    key: 'keycloak',
    displayName: 'Keycloak',
    issuerTemplate: 'https://<host>/realms/<realm>',
    issuerHint:
      'Replace <host> and <realm>. Create an OIDC client in your Keycloak realm with the Callback URL below as a valid redirect URI.',
    scopes: ['openid', 'email', 'profile'],
  },
]

export function getPreset(key: string): SsoPreset | undefined {
  return SSO_PRESETS.find((p) => p.key === key)
}
