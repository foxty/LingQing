import {
  databricksConnectionSchema,
  databricksUserTemplateSchema,
} from '@/components/data-source/DatabricksConnectionForm'
import {
  rdbmsConnectionSchema,
  rdbmsUserTemplateConnectionSchema,
} from '@/components/data-source/RDBMSConnectionForm'
import type { DataSourceUserAuthFieldErrors } from '@/components/data-source/DataSourceUserCredentialAuthSection'
import type { DataSourceConnectionFieldErrors } from '@/components/data-source/formLayout'
import type { DataSourceFormValues } from '@/components/data-source/addDataSourceDialogModel'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import {
  DATABRICKS_USER_AUTH_OAUTH2,
  type DatabricksUserCredentialAuthType,
} from '@/lib/dataSourceUserAuth'
import { validateSecretRequired, validateSecretWhenEditing } from '@/lib/sensitiveCredential'

const connectionFieldKeys = new Set<keyof DataSourceConnectionFieldErrors>([
  'host',
  'port',
  'database',
  'username',
  'password',
  'warehouse_id',
  'http_path',
  'metadataSyncUsername',
  'metadataSyncPassword',
])

function applyZodIssuesToFieldErrors(
  issues: { path: (string | number)[]; message: string }[],
  target: DataSourceConnectionFieldErrors,
) {
  for (const issue of issues) {
    const key = issue.path[0]
    if (typeof key !== 'string' || !connectionFieldKeys.has(key as keyof DataSourceConnectionFieldErrors)) {
      continue
    }
    target[key as keyof DataSourceConnectionFieldErrors] = issue.message
  }
}

function mergeSecretFieldError(existing: string | undefined, next: string | null): string | undefined {
  if (!next) {
    return existing
  }
  return next
}

export type DataSourceSubmitValidationResult =
  | { ok: true }
  | {
      ok: false
      connectionFieldErrors: DataSourceConnectionFieldErrors
      userAuthFieldErrors?: DataSourceUserAuthFieldErrors
    }

export async function validateDataSourceFormSubmit(options: {
  data: DataSourceFormValues
  formData: DataSourceFormValues
  sharedPasswordSecret: SecretCredentialFieldHandle
  syncPasswordSecret: SecretCredentialFieldHandle
  userCredentialAuthType: DatabricksUserCredentialAuthType
  oauth2Config: OAuth2FormConfig
  oauthClientSecret: SecretCredentialFieldHandle
}): Promise<DataSourceSubmitValidationResult> {
  const {
    data,
    formData,
    sharedPasswordSecret,
    syncPasswordSecret,
    userCredentialAuthType,
    oauthClientSecret,
  } = options
  const fieldErrors: DataSourceConnectionFieldErrors = {}

  try {
    if (data.type === 'databricks' && data.credentialMode === 'user') {
      await databricksUserTemplateSchema.parseAsync(formData)
      fieldErrors.metadataSyncPassword = mergeSecretFieldError(
        fieldErrors.metadataSyncPassword,
        validateSecretRequired(
          syncPasswordSecret,
          'Sync access token is required for per-user Databricks sources.',
        ),
      )
      fieldErrors.metadataSyncPassword = mergeSecretFieldError(
        fieldErrors.metadataSyncPassword,
        validateSecretWhenEditing(syncPasswordSecret, 'Enter a new sync token or keep saved'),
      )
    } else if (data.type === 'databricks') {
      await databricksConnectionSchema.omit({ password: true }).parseAsync(formData)
      fieldErrors.password = mergeSecretFieldError(
        fieldErrors.password,
        validateSecretRequired(sharedPasswordSecret, 'Access token is required'),
      )
      fieldErrors.password = mergeSecretFieldError(
        fieldErrors.password,
        validateSecretWhenEditing(sharedPasswordSecret, 'Enter a new access token or keep saved'),
      )
    } else if (data.credentialMode === 'user') {
      await rdbmsUserTemplateConnectionSchema.parseAsync(formData)
      fieldErrors.metadataSyncPassword = mergeSecretFieldError(
        fieldErrors.metadataSyncPassword,
        validateSecretRequired(
          syncPasswordSecret,
          'Sync login password is required for per-user data sources.',
        ),
      )
      fieldErrors.metadataSyncPassword = mergeSecretFieldError(
        fieldErrors.metadataSyncPassword,
        validateSecretWhenEditing(syncPasswordSecret, 'Enter a new sync password or keep saved'),
      )
      if (!data.metadataSyncUsername?.trim()) {
        fieldErrors.metadataSyncUsername =
          'Sync login username is required for per-user data sources.'
      }
    } else {
      await rdbmsConnectionSchema.omit({ password: true }).parseAsync(formData)
      fieldErrors.password = mergeSecretFieldError(
        fieldErrors.password,
        validateSecretRequired(sharedPasswordSecret, 'Password is required'),
      )
      fieldErrors.password = mergeSecretFieldError(
        fieldErrors.password,
        validateSecretWhenEditing(sharedPasswordSecret, 'Enter a new password or keep saved'),
      )
    }
  } catch (error: unknown) {
    if (error && typeof error === 'object' && 'errors' in error) {
      applyZodIssuesToFieldErrors((error as { errors: { path: (string | number)[]; message: string }[] }).errors, fieldErrors)
    }
    return { ok: false, connectionFieldErrors: fieldErrors }
  }

  if (Object.values(fieldErrors).some(Boolean)) {
    return { ok: false, connectionFieldErrors: fieldErrors }
  }

  if (
    data.credentialMode === 'user' &&
    data.type === 'databricks' &&
    userCredentialAuthType === DATABRICKS_USER_AUTH_OAUTH2
  ) {
    const oauthErrors: DataSourceUserAuthFieldErrors = {}
    if (!options.oauth2Config.clientId.trim()) {
      oauthErrors.oauthClientId = 'OAuth client ID is required'
    }
    const clientSecretErr = validateSecretRequired(oauthClientSecret, 'OAuth client secret is required')
    if (clientSecretErr) {
      oauthErrors.oauthClientSecret = clientSecretErr
    }
    const clientSecretEditErr = validateSecretWhenEditing(
      oauthClientSecret,
      'Enter a new client secret or keep saved',
    )
    if (clientSecretEditErr) {
      oauthErrors.oauthClientSecret = clientSecretEditErr
    }
    if (!options.oauth2Config.scopes.length) {
      oauthErrors.oauthScopes = 'Enter at least one authorize scope (must match your Databricks OAuth app)'
    }
    if (Object.values(oauthErrors).some(Boolean)) {
      return { ok: false, connectionFieldErrors: fieldErrors, userAuthFieldErrors: oauthErrors }
    }
  }

  return { ok: true }
}