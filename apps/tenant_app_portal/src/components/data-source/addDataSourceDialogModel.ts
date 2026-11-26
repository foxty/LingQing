import * as z from 'zod'
import type { DataSource } from '@/lib/dataSourceApi'
import { applyNestedSecretKey } from '@/lib/sensitiveCredential'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'

export const MASKED_DS_PASSWORD = 'config.password'
export const MASKED_DS_SYNC_PASSWORD = 'config.metadata_sync.password'
export const MASKED_DS_OAUTH_CLIENT_SECRET = 'config.user_oauth.client_secret'

export type DataSourceFormType = 'postgres' | 'mysql' | 'databricks'

const baseSchema = z.object({
  name: z.string().min(1).max(100),
  description: z.string().optional(),
  type: z.enum(['postgres', 'mysql', 'databricks']),
  credentialMode: z.enum(['shared', 'user']).default('shared'),
  metadataSyncUsername: z.string().optional(),
  metadataSyncPassword: z.string().optional(),
  readOnly: z.boolean().optional(),
  host: z.any().optional(),
  port: z.any().optional(),
  password: z.any().optional(),
  database: z.any().optional(),
  username: z.any().optional(),
  ssl: z.any().optional(),
  warehouse_id: z.any().optional(),
  http_path: z.any().optional(),
})

export function getDataSourceFormSchema() {
  return baseSchema
}

export type DataSourceFormValues = z.infer<typeof baseSchema>

export function getDataSourceFormDefaultValues(dataSource?: DataSource | null): DataSourceFormValues {
  if (!dataSource) {
    return {
      name: '',
      description: '',
      type: 'postgres',
      credentialMode: 'shared',
      readOnly: true,
      host: '',
      port: 5432,
      database: '',
      username: '',
      password: '',
      ssl: false,
      warehouse_id: '',
      http_path: '',
      metadataSyncUsername: '',
      metadataSyncPassword: '',
    }
  }

  return {
    name: dataSource.name,
    description: dataSource.description || '',
    type: dataSource.type as DataSourceFormType,
    credentialMode: (dataSource.credential_mode ?? 'shared') as 'shared' | 'user',
    readOnly: dataSource.config?.readOnly ?? true,
    host: dataSource.config?.host || '',
    port: dataSource.config?.port || 5432,
    database: dataSource.config?.database || '',
    username: dataSource.config?.username || '',
    password: '',
    ssl: dataSource.config?.ssl || false,
    warehouse_id: dataSource.config?.extra_params?.warehouse_id || '',
    http_path: dataSource.config?.extra_params?.http_path || '',
    metadataSyncUsername: dataSource.config?.metadata_sync?.username || '',
    metadataSyncPassword: '',
  }
}

export function attachMetadataSyncConfig(
  config: Record<string, unknown>,
  data: Pick<DataSourceFormValues, 'credentialMode' | 'type' | 'metadataSyncUsername'>,
  syncPasswordSecret?: SecretCredentialFieldHandle,
): Record<string, unknown> {
  if (data.credentialMode !== 'user') {
    return config
  }
  let next = { ...config }
  if (data.type !== 'databricks' && data.metadataSyncUsername?.trim()) {
    next = {
      ...next,
      metadata_sync: {
        ...((next.metadata_sync as object) || {}),
        username: data.metadataSyncUsername.trim(),
      },
    }
  }
  if (syncPasswordSecret) {
    next = applyNestedSecretKey(next, 'metadata_sync', 'password', syncPasswordSecret)
  }
  return next
}