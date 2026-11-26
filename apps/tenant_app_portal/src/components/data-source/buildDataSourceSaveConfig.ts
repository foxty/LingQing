import {
  buildDatabricksConfig,
  buildDatabricksUserTemplateConfig,
} from '@/components/data-source/DatabricksConnectionForm'
import { buildRDBMSConfig, buildRDBMSUserTemplateConfig } from '@/components/data-source/RDBMSConnectionForm'
import type { DataSourceFormValues } from '@/components/data-source/addDataSourceDialogModel'
import { attachMetadataSyncConfig } from '@/components/data-source/addDataSourceDialogModel'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import {
  attachDatabricksUserCredentialAuth,
  type DatabricksUserCredentialAuthType,
} from '@/lib/dataSourceUserAuth'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'

export function buildDataSourceSaveConfig(
  data: DataSourceFormValues,
  options: {
    sharedPasswordSecret: SecretCredentialFieldHandle
    syncPasswordSecret: SecretCredentialFieldHandle
    userCredentialAuthType: DatabricksUserCredentialAuthType
    oauth2Config: OAuth2FormConfig
    oauthClientSecret: SecretCredentialFieldHandle
  },
): Record<string, unknown> {
  let config: Record<string, unknown>

  if (data.type === 'databricks' && data.credentialMode === 'user') {
    config = buildDatabricksUserTemplateConfig(data)
  } else if (data.type === 'databricks') {
    config = buildDatabricksConfig(data, { passwordSecret: options.sharedPasswordSecret })
  } else if (data.credentialMode === 'user') {
    config = buildRDBMSUserTemplateConfig(data)
  } else {
    config = buildRDBMSConfig(data, { passwordSecret: options.sharedPasswordSecret })
  }

  config = attachMetadataSyncConfig(config, data, options.syncPasswordSecret)

  if (data.credentialMode === 'user' && data.type === 'databricks') {
    config = attachDatabricksUserCredentialAuth(config, {
      userCredentialAuthType: options.userCredentialAuthType,
      oauth2Config: options.oauth2Config,
      clientSecret: options.oauthClientSecret,
    })
  }

  return config
}