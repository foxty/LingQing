/** BYOT `…/connections/*` API types (data sources + API connectors). */

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

export interface UserIntegrationConnectionSummary {
  user_id: number
  username?: string | null
  resource_type: string
  resource_id: number
  resource_name?: string | null
  status: 'not_connected' | 'connected' | 'expired'
  account_label?: string | null
  auth_type?: string | null
  updated_at?: string | null
  provisioned_by_user_id?: number | null
  provisioned_at?: string | null
}

export interface UserIntegrationConnectionClient {
  get: () => Promise<UserIntegrationConnection>
  upsert: (body: UserIntegrationConnectionUpsert) => Promise<UserIntegrationConnection>
  remove: () => Promise<void>
  test: (body?: UserIntegrationConnectionUpsert) => Promise<{ success: boolean; message: string }>
}