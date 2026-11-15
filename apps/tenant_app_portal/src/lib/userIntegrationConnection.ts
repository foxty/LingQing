/** BYOT `…/connections/me` API types (data sources + API connectors). */

export interface UserIntegrationConnection {
  resource_type: string
  resource_id: number
  status: 'not_connected' | 'connected' | 'expired'
  account_label?: string | null
  auth_type?: string | null
  expires_at?: string | null
  secrets?: Record<string, string>
  masked_fields?: string[]
}

export interface UserIntegrationConnectionUpsert {
  auth_type: string
  secrets: Record<string, string>
  account_label?: string | null
}