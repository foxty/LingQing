/** Suggested authorize scopes for chip autocomplete (must match each IdP app registration). */

export { SUGGESTED_DATABRICKS_OAUTH_SCOPES } from '@/lib/dataSourceUserAuth'

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

export function apiConnectorOAuthScopeSuggestions(
  packRef: string | null | undefined,
  authorizeUrl: string,
): readonly string[] {
  if (packRef === 'slack-user') return SUGGESTED_SLACK_USER_OAUTH_SCOPES
  const url = authorizeUrl.trim().toLowerCase()
  if (url.includes('slack.com')) return SUGGESTED_SLACK_USER_OAUTH_SCOPES
  return []
}