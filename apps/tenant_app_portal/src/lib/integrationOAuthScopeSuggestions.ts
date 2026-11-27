/** Suggested authorize scopes for chip autocomplete (must match each IdP app registration). */

export { SUGGESTED_DATABRICKS_OAUTH_SCOPES } from '@/lib/dataSourceUserAuth'

/** Google API packs — shared OAuth endpoints; scopes differ per pack YAML. */
export const SUGGESTED_GOOGLE_DRIVE_USER_OAUTH_SCOPES = [
  'https://www.googleapis.com/auth/drive.readonly',
] as const

export const SUGGESTED_GMAIL_USER_OAUTH_SCOPES = [
  'https://www.googleapis.com/auth/gmail.readonly',
] as const

export const SUGGESTED_GOOGLE_CALENDAR_USER_OAUTH_SCOPES = [
  'https://www.googleapis.com/auth/calendar.readonly',
] as const

/** monday.com (user) pack — see `config/integration-packs/api_connector/monday-user.yaml`. */
export const SUGGESTED_MONDAY_USER_OAUTH_SCOPES = [
  'me:read',
  'boards:read',
  'workspaces:read',
  'updates:read',
  'tags:read',
] as const

/** Slack (user) pack defaults — see `config/integration-packs/api_connector/slack-user.yaml`. */
export const SUGGESTED_SLACK_USER_OAUTH_SCOPES = [
  'search:read',
  'channels:read',
  'channels:history',
  'groups:read',
  'groups:history',
  'im:read',
  'im:history',
  'mpim:read',
  'mpim:history',
  'users:read',
  'users:read.email',
  'files:read',
] as const

const GOOGLE_PACK_SCOPES: Record<string, readonly string[]> = {
  'google-drive-user': SUGGESTED_GOOGLE_DRIVE_USER_OAUTH_SCOPES,
  'gmail-user': SUGGESTED_GMAIL_USER_OAUTH_SCOPES,
  'google-calendar-user': SUGGESTED_GOOGLE_CALENDAR_USER_OAUTH_SCOPES,
}

function packIdFromRef(packRef: string | null | undefined): string | null {
  if (!packRef?.trim()) return null
  const at = packRef.indexOf('@')
  return at === -1 ? packRef.trim() : packRef.slice(0, at).trim()
}

export function apiConnectorOAuthScopeSuggestions(
  packRef: string | null | undefined,
  authorizeUrl: string,
): readonly string[] {
  const packId = packIdFromRef(packRef)
  if (packId === 'slack-user') return SUGGESTED_SLACK_USER_OAUTH_SCOPES
  if (packId === 'monday-user') return SUGGESTED_MONDAY_USER_OAUTH_SCOPES
  if (packId && packId in GOOGLE_PACK_SCOPES) {
    return GOOGLE_PACK_SCOPES[packId]
  }
  const url = authorizeUrl.trim().toLowerCase()
  if (url.includes('slack.com')) return SUGGESTED_SLACK_USER_OAUTH_SCOPES
  if (url.includes('auth.monday.com')) return SUGGESTED_MONDAY_USER_OAUTH_SCOPES
  if (url.includes('accounts.google.com')) {
    return SUGGESTED_GOOGLE_DRIVE_USER_OAUTH_SCOPES
  }
  return []
}