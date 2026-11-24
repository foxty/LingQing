import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ApiConnector, ApiConnectorUpdateRequest } from '@/lib/apiConnectorApi'
import { useSecretCredentialField } from '@/hooks/useSecretCredentialField'
import {
  secretPayloadValue,
  validateSecretRequired,
  validateSecretWhenEditing,
} from '@/lib/sensitiveCredential'
import { hasMaskedFieldPath } from '@/lib/maskedFields'
import { omitUnchangedSecretsDeep } from '@/lib/secretWire'
import {
  type ApiConnectorAuthType,
  type ApiConnectorSchemaSourceType,
  type ApiKeyConfig,
  type BasicConfig,
  type CustomAuthFormConfig,
  type FieldErrorKey,
  type OAuth2FormConfig,
  defaultApiKeyConfig,
  defaultBasicConfig,
  defaultCustomAuthConfig,
  createDefaultOAuth2Config,
  scopesToText,
  textToScopes,
} from '@/components/api-connector/types'

const maskedAuthSecretPath = (field: string) => `auth_config.${field}`

interface UseApiConnectorFormArgs {
  open: boolean
  connector?: ApiConnector | null
  mode: 'create' | 'edit'
}

export function useApiConnectorForm({ open, connector, mode }: UseApiConnectorFormArgs) {
  const { t } = useTranslation()

  const initialAuthType = connector?.auth_type ?? 'none'
  const maskedFields = connector?.masked_fields
  const maskedAuth = connector?.auth_config ?? {}
  const isAuthConfigured =
    mode === 'edit' &&
    connector?.auth_type !== 'none' &&
    (maskedFields ?? []).some((path) => path.startsWith('auth_config.'))
  const packLocked = Boolean(connector?.pack_ref)

  const authResetKey = open ? (connector?.id ?? 'new') : 'closed'
  const apiKeyValueSecret = useSecretCredentialField(
    mode,
    hasMaskedFieldPath(maskedFields, maskedAuthSecretPath('key_value')) ||
      hasMaskedFieldPath(maskedFields, maskedAuthSecretPath('api_key')),
    `${authResetKey}-api-key`
  )
  const bearerSecret = useSecretCredentialField(
    mode,
    hasMaskedFieldPath(maskedFields, maskedAuthSecretPath('token')),
    `${authResetKey}-bearer`
  )
  const basicPasswordSecret = useSecretCredentialField(
    mode,
    hasMaskedFieldPath(maskedFields, maskedAuthSecretPath('password')),
    `${authResetKey}-basic`
  )
  const oauthClientSecret = useSecretCredentialField(
    mode,
    hasMaskedFieldPath(maskedFields, maskedAuthSecretPath('client_secret')),
    `${authResetKey}-oauth-client-secret`
  )

  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [description, setDescription] = useState('')
  const [authType, setAuthTypeState] = useState<ApiConnectorAuthType>('none')
  const [apiKeyConfig, setApiKeyConfig] = useState<ApiKeyConfig>(defaultApiKeyConfig)
  const [basicConfig, setBasicConfig] = useState<BasicConfig>(defaultBasicConfig)
  const [customAuthConfig, setCustomAuthConfig] =
    useState<CustomAuthFormConfig>(defaultCustomAuthConfig)
  const [oauth2Config, setOauth2Config] = useState<OAuth2FormConfig>(createDefaultOAuth2Config)
  const [schemaSourceType, setSchemaSourceType] = useState<ApiConnectorSchemaSourceType>('manual')
  const [schemaSourceUrl, setSchemaSourceUrl] = useState('')
  const [credentialMode, setCredentialMode] = useState<'shared' | 'user'>('shared')
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldErrorKey, string>>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)

  const v = (key: string) => t(`components.addApiConnectorDialog.validation.${key}`)

  const clearFieldError = (key: FieldErrorKey) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const setAuthType = (next: ApiConnectorAuthType) => {
    setAuthTypeState(next)
    if (next === 'oauth2') {
      setCredentialMode('user')
      setOauth2Config((prev) =>
        prev.redirectUri.trim()
          ? prev
          : { ...prev, redirectUri: createDefaultOAuth2Config().redirectUri }
      )
    }
  }

  const resetForm = () => {
    setName('')
    setBaseUrl('')
    setDescription('')
    setAuthTypeState('none')
    setApiKeyConfig(defaultApiKeyConfig)
    setBasicConfig(defaultBasicConfig)
    setCustomAuthConfig(defaultCustomAuthConfig)
    setOauth2Config(createDefaultOAuth2Config())
    setSchemaSourceType('manual')
    setSchemaSourceUrl('')
    setCredentialMode('shared')
    setFieldErrors({})
    setSubmitError(null)
  }

  useEffect(() => {
    if (!open) return

    if (mode === 'edit' && connector) {
      setName(connector.name)
      setBaseUrl(connector.base_url)
      setDescription(connector.description || '')
      setAuthTypeState(connector.auth_type)
      setSchemaSourceType(connector.schema_source_type)
      setSchemaSourceUrl(connector.schema_source_url || '')
      setCredentialMode(
        connector.auth_type === 'oauth2' ? 'user' : (connector.credential_mode ?? 'shared')
      )

      const masked = connector.auth_config ?? {}
      if (connector.auth_type === 'api_key') {
        setApiKeyConfig({
          keyName:
            typeof masked.key_name === 'string' ? masked.key_name : defaultApiKeyConfig.keyName,
          keyValue: '',
        })
      } else {
        setApiKeyConfig(defaultApiKeyConfig)
      }

      if (connector.auth_type === 'basic') {
        setBasicConfig({
          username: typeof masked.username === 'string' ? masked.username : '',
        })
      } else {
        setBasicConfig(defaultBasicConfig)
      }

      if (connector.auth_type === 'custom' && connector.auth_config) {
        setCustomAuthConfig({
          loginEndpoint: masked.login_endpoint || '',
          loginMethod: masked.login_method || 'POST',
          loginPayloadTemplate: JSON.stringify(masked.login_payload_template || {}, null, 2),
          tokenExtraction: JSON.stringify(masked.token_extraction || {}, null, 2),
          requestHeaders: JSON.stringify(masked.request_headers || {}, null, 2),
          extraConfig: JSON.stringify(masked.extra_config || {}, null, 2),
        })
      } else {
        setCustomAuthConfig(defaultCustomAuthConfig)
      }

      if (connector.auth_type === 'oauth2') {
        const storedRedirect =
          typeof masked.redirect_uri === 'string' ? masked.redirect_uri.trim() : ''
        setOauth2Config({
          clientId: typeof masked.client_id === 'string' ? masked.client_id : '',
          redirectUri: storedRedirect || createDefaultOAuth2Config().redirectUri,
          authorizeUrl: typeof masked.authorize_url === 'string' ? masked.authorize_url : '',
          tokenUrl: typeof masked.token_url === 'string' ? masked.token_url : '',
          scopes: Array.isArray(masked.scopes)
            ? masked.scopes.filter((scope): scope is string => typeof scope === 'string')
            : [],
          scopeParam: typeof masked.scope_param === 'string' ? masked.scope_param : 'scope',
          tokenAuthMethod:
            typeof masked.token_auth_method === 'string'
              ? masked.token_auth_method
              : 'client_secret_post',
          tokenResponsePath:
            typeof masked.token_response_path === 'string' ? masked.token_response_path : '',
        })
      } else {
        setOauth2Config(createDefaultOAuth2Config())
      }

      setFieldErrors({})
      setSubmitError(null)
      return
    }

    resetForm()
  }, [open, mode, connector])

  const authConfig = useMemo<Record<string, unknown>>(() => {
    if (authType === 'api_key') {
      const keyValue = secretPayloadValue(apiKeyValueSecret)
      return {
        auth_method: 'api_key',
        key_name: apiKeyConfig.keyName.trim(),
        ...(keyValue !== undefined ? { key_value: keyValue } : {}),
      }
    }

    if (authType === 'bearer') {
      const token = secretPayloadValue(bearerSecret)
      return {
        auth_method: 'bearer',
        ...(token !== undefined ? { token } : {}),
      }
    }

    if (authType === 'basic') {
      const password = secretPayloadValue(basicPasswordSecret)
      return {
        auth_method: 'basic',
        username: basicConfig.username,
        ...(password !== undefined ? { password } : {}),
      }
    }

    if (authType === 'custom') {
      const parseJsonSafely = (jsonString: string): unknown => {
        if (!jsonString || !jsonString.trim()) return {}
        try {
          return JSON.parse(jsonString)
        } catch {
          return {}
        }
      }

      return {
        auth_method: 'custom',
        login_endpoint: customAuthConfig.loginEndpoint.trim(),
        login_method: customAuthConfig.loginMethod || 'POST',
        login_payload_template: parseJsonSafely(customAuthConfig.loginPayloadTemplate),
        token_extraction: parseJsonSafely(customAuthConfig.tokenExtraction),
        request_headers: parseJsonSafely(customAuthConfig.requestHeaders),
        extra_config: omitUnchangedSecretsDeep(parseJsonSafely(customAuthConfig.extraConfig)),
      }
    }

    if (authType === 'oauth2') {
      const clientSecret = secretPayloadValue(oauthClientSecret)
      return {
        auth_method: 'oauth2',
        authorize_url: oauth2Config.authorizeUrl.trim(),
        token_url: oauth2Config.tokenUrl.trim(),
        client_id: oauth2Config.clientId.trim(),
        redirect_uri: oauth2Config.redirectUri.trim() || null,
        scopes: oauth2Config.scopes,
        scope_param: oauth2Config.scopeParam || 'scope',
        token_auth_method: oauth2Config.tokenAuthMethod || 'client_secret_post',
        token_response_path: oauth2Config.tokenResponsePath.trim() || null,
        ...(clientSecret !== undefined ? { client_secret: clientSecret } : {}),
      }
    }

    return {}
  }, [
    apiKeyConfig,
    apiKeyValueSecret,
    authType,
    basicConfig,
    basicPasswordSecret,
    bearerSecret,
    customAuthConfig,
    oauth2Config,
    oauthClientSecret,
  ])

  const hasUnsavedData = () =>
    !!(
      name.trim() ||
      baseUrl.trim() ||
      description.trim() ||
      schemaSourceUrl.trim() ||
      authType !== 'none' ||
      schemaSourceType !== 'manual' ||
      apiKeyValueSecret.draft.trim() ||
      bearerSecret.draft.trim() ||
      basicConfig.username.trim() ||
      basicPasswordSecret.draft.trim() ||
      oauth2Config.clientId.trim() ||
      oauth2Config.authorizeUrl.trim() ||
      oauthClientSecret.draft.trim()
    )

  const validateBeforeSubmit = (): boolean => {
    setSubmitError(null)
    const errors: Partial<Record<FieldErrorKey, string>> = {}

    if (!name.trim()) errors.name = v('nameRequired')
    if (!baseUrl.trim()) errors.baseUrl = v('baseUrlRequired')

    const requiresSharedSecrets = credentialMode === 'shared'

    if (requiresSharedSecrets && authType === 'api_key') {
      const req = validateSecretRequired(apiKeyValueSecret, v('apiKeyValueRequired'))
      const editErr = validateSecretWhenEditing(apiKeyValueSecret, v('apiKeyValueRequired'))
      if (req) errors.apiKeyValue = req
      else if (editErr) errors.apiKeyValue = editErr
    }

    if (requiresSharedSecrets && authType === 'bearer') {
      const req = validateSecretRequired(bearerSecret, v('bearerTokenRequired'))
      const editErr = validateSecretWhenEditing(bearerSecret, v('bearerTokenRequired'))
      if (req) errors.bearerToken = req
      else if (editErr) errors.bearerToken = editErr
    }

    if (requiresSharedSecrets && authType === 'basic') {
      if (!basicConfig.username.trim()) errors.basicUsername = v('basicUsernameRequired')
      const req = validateSecretRequired(basicPasswordSecret, v('basicPasswordRequired'))
      const editErr = validateSecretWhenEditing(basicPasswordSecret, v('basicPasswordRequired'))
      if (req) errors.basicPassword = req
      else if (editErr) errors.basicPassword = editErr
    }

    if (authType === 'custom') {
      const validateJson = (jsonString: string, field: FieldErrorKey): void => {
        if (!jsonString || !jsonString.trim()) return
        try {
          JSON.parse(jsonString)
        } catch {
          errors[field] = v('invalidJson')
        }
      }

      validateJson(customAuthConfig.loginPayloadTemplate, 'loginPayloadTemplate')
      validateJson(customAuthConfig.tokenExtraction, 'tokenExtraction')
      validateJson(customAuthConfig.requestHeaders, 'requestHeaders')
      validateJson(customAuthConfig.extraConfig, 'extraConfig')

      if (!customAuthConfig.loginEndpoint.trim()) {
        errors.loginEndpoint = v('loginEndpointRequired')
      }
    }

    if (authType === 'oauth2') {
      if (!oauth2Config.clientId.trim()) errors.oauthClientId = v('oauthClientIdRequired')
      if (!oauth2Config.authorizeUrl.trim()) {
        errors.oauthAuthorizeUrl = v('oauthAuthorizeUrlRequired')
      }
      if (!oauth2Config.tokenUrl.trim()) errors.oauthTokenUrl = v('oauthTokenUrlRequired')
      if (mode === 'create') {
        const req = validateSecretRequired(oauthClientSecret, v('oauthClientSecretRequired'))
        if (req) errors.oauthClientSecret = req
      } else {
        const editErr = validateSecretWhenEditing(oauthClientSecret, v('oauthClientSecretRequired'))
        if (editErr) errors.oauthClientSecret = editErr
      }
    }

    if (schemaSourceType === 'openapi_url' && !schemaSourceUrl.trim()) {
      errors.schemaSourceUrl = v('schemaUrlRequired')
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return false
    }

    setFieldErrors({})
    return true
  }

  const buildUpdatePayload = (): ApiConnectorUpdateRequest => {
    const payload: ApiConnectorUpdateRequest = {
      name: name.trim(),
      description: description.trim() || undefined,
      base_url: baseUrl.trim(),
      credential_mode: authType === 'oauth2' ? 'user' : credentialMode,
      auth_type: authType,
      schema_source_type: schemaSourceType,
      schema_source_url: schemaSourceType === 'openapi_url' ? schemaSourceUrl.trim() || null : null,
    }

    const authChanged = authType !== initialAuthType
    const hasAuthInput =
      secretPayloadValue(apiKeyValueSecret) !== undefined ||
      secretPayloadValue(bearerSecret) !== undefined ||
      basicConfig.username.trim() ||
      secretPayloadValue(basicPasswordSecret) !== undefined ||
      secretPayloadValue(oauthClientSecret) !== undefined ||
      (authType === 'oauth2' &&
        (oauth2Config.clientId.trim() !== '' ||
          oauth2Config.redirectUri.trim() !== '' ||
          oauth2Config.authorizeUrl.trim() !== ''))

    const shouldIncludeAuthConfig =
      authChanged || hasAuthInput || authType === 'custom' || authType === 'oauth2'

    if (shouldIncludeAuthConfig) {
      payload.auth_config = authConfig as Record<string, unknown>
    }

    return payload
  }

  const buildCreatePayload = () => ({
    name: name.trim(),
    description: description.trim() || undefined,
    base_url: baseUrl.trim(),
    credential_mode: (authType === 'oauth2' ? 'user' : credentialMode) as 'shared' | 'user',
    auth_type: authType,
    auth_config: authConfig as Record<string, unknown>,
    rate_policy: {},
    schema_source_type: schemaSourceType,
    schema_source_url: schemaSourceType === 'openapi_url' ? schemaSourceUrl.trim() || null : null,
  })

  const credentialModeLocked = packLocked || authType === 'oauth2'

  return {
    packLocked,
    credentialModeLocked,
    isAuthConfigured,
    maskedAuth,
    name,
    setName,
    baseUrl,
    setBaseUrl,
    description,
    setDescription,
    authType,
    setAuthType,
    apiKeyConfig,
    setApiKeyConfig,
    basicConfig,
    setBasicConfig,
    customAuthConfig,
    setCustomAuthConfig,
    oauth2Config,
    setOauth2Config,
    scopesText: scopesToText(oauth2Config.scopes),
    setScopesText: (text: string) =>
      setOauth2Config((prev) => ({ ...prev, scopes: textToScopes(text) })),
    schemaSourceType,
    setSchemaSourceType,
    schemaSourceUrl,
    setSchemaSourceUrl,
    credentialMode,
    setCredentialMode,
    fieldErrors,
    clearFieldError,
    submitError,
    setSubmitError,
    apiKeyValueSecret,
    bearerSecret,
    basicPasswordSecret,
    oauthClientSecret,
    resetForm,
    hasUnsavedData,
    validateBeforeSubmit,
    buildUpdatePayload,
    buildCreatePayload,
  }
}
