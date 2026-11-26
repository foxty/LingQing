import { buildDataSourceSaveConfig } from '@/components/data-source/buildDataSourceSaveConfig'
import {
  getDataSourceFormDefaultValues,
  getDataSourceFormSchema,
  MASKED_DS_OAUTH_CLIENT_SECRET,
  MASKED_DS_PASSWORD,
  MASKED_DS_SYNC_PASSWORD,
  type DataSourceFormType,
  type DataSourceFormValues,
} from '@/components/data-source/addDataSourceDialogModel'
import type { DataSourceUserAuthFieldErrors } from '@/components/data-source/DataSourceUserCredentialAuthSection'
import type { DataSourceConnectionFieldErrors } from '@/components/data-source/formLayout'
import { validateDataSourceFormSubmit } from '@/components/data-source/validateDataSourceFormSubmit'
import { createDefaultOAuth2Config } from '@/components/api-connector/types'
import type { OAuth2FormConfig } from '@/components/api-connector/types'
import { useDataSources } from '@/hooks/useDataSources'
import { useNotification } from '@/hooks/useNotification'
import { useSecretCredentialField } from '@/hooks/useSecretCredentialField'
import type { DataSource } from '@/lib/dataSourceApi'
import { hasMaskedFieldPath } from '@/lib/maskedFields'
import {
  applyOidcUrlsFromHost,
  DATABRICKS_USER_AUTH_OAUTH2,
  DATABRICKS_USER_AUTH_PAT,
  oauth2ConfigFromDataSourceConfig,
  type DatabricksUserCredentialAuthType,
} from '@/lib/dataSourceUserAuth'
import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export function useAddDataSourceDialog(options: {
  open: boolean
  dataSource?: DataSource | null
  onSuccess?: () => void
  onClose: () => void
}) {
  const { open, dataSource, onSuccess, onClose } = options
  const { t } = useTranslation()
  const { addDataSource, modifyDataSource } = useDataSources()
  const { showError, showSuccess } = useNotification()

  const [selectedType, setSelectedType] = useState<DataSourceFormType>('postgres')
  const [saving, setSaving] = useState(false)
  const [connectionFieldErrors, setConnectionFieldErrors] = useState<DataSourceConnectionFieldErrors>({})
  const [userCredentialAuthType, setUserCredentialAuthType] =
    useState<DatabricksUserCredentialAuthType>(DATABRICKS_USER_AUTH_PAT)
  const [oauth2Config, setOauth2Config] = useState<OAuth2FormConfig>(() => createDefaultOAuth2Config())
  const [userAuthFieldErrors, setUserAuthFieldErrors] = useState<DataSourceUserAuthFieldErrors>({})

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<DataSourceFormValues>({
    resolver: zodResolver(getDataSourceFormSchema()),
    defaultValues: getDataSourceFormDefaultValues(dataSource),
    shouldUnregister: false,
    mode: 'onSubmit',
  })

  const formData = watch()
  const watchedType = watch('type') as DataSourceFormType
  const watchedCredentialMode = watch('credentialMode')
  const watchedHost = watch('host')

  const formMode = dataSource ? 'edit' : 'create'
  const secretResetKey = open ? (dataSource?.id ?? 'new') : 'closed'

  const storedMetadataSyncPassword = useMemo(
    () => (dataSource ? hasMaskedFieldPath(dataSource.masked_fields, MASKED_DS_SYNC_PASSWORD) : false),
    [dataSource],
  )
  const storedSharedPassword = useMemo(
    () => (dataSource ? hasMaskedFieldPath(dataSource.masked_fields, MASKED_DS_PASSWORD) : false),
    [dataSource],
  )
  const storedOAuthClientSecret = useMemo(
    () => (dataSource ? hasMaskedFieldPath(dataSource.masked_fields, MASKED_DS_OAUTH_CLIENT_SECRET) : false),
    [dataSource],
  )

  const sharedPasswordSecret = useSecretCredentialField(formMode, storedSharedPassword, `${secretResetKey}-shared`)
  const syncPasswordSecret = useSecretCredentialField(formMode, storedMetadataSyncPassword, `${secretResetKey}-sync`)
  const oauthClientSecret = useSecretCredentialField(formMode, storedOAuthClientSecret, `${secretResetKey}-ds-oauth`)

  const clearConnectionFieldErrors = () => setConnectionFieldErrors({})

  useEffect(() => {
    if (watchedType !== selectedType) {
      setSelectedType(watchedType)
      reset(getDataSourceFormDefaultValues(dataSource), { keepValues: true, keepErrors: false })
    }
  }, [watchedType, selectedType, dataSource, reset])

  useEffect(() => {
    if (!open) {
      return
    }
    reset(getDataSourceFormDefaultValues(dataSource))
    setSelectedType((dataSource?.type as DataSourceFormType) || 'postgres')
    clearConnectionFieldErrors()
    setUserAuthFieldErrors({})
    const authType =
      dataSource?.config?.user_credential_auth_type === DATABRICKS_USER_AUTH_OAUTH2
        ? DATABRICKS_USER_AUTH_OAUTH2
        : DATABRICKS_USER_AUTH_PAT
    setUserCredentialAuthType(authType)
    const host = String(dataSource?.config?.host ?? '')
    const initial = dataSource
      ? oauth2ConfigFromDataSourceConfig(dataSource.config, host)
      : applyOidcUrlsFromHost(createDefaultOAuth2Config(), host)
    setOauth2Config(initial)
  }, [open, dataSource, reset])

  useEffect(() => {
    if (watchedCredentialMode !== 'user' || watchedType !== 'databricks') {
      return
    }
    if (userCredentialAuthType !== DATABRICKS_USER_AUTH_OAUTH2) {
      return
    }
    setOauth2Config((prev) => applyOidcUrlsFromHost(prev, String(watchedHost ?? '')))
  }, [watchedHost, watchedCredentialMode, watchedType, userCredentialAuthType])

  const handleTypeChange = (type: DataSourceFormType) => {
    reset(
      {
        name: formData.name,
        description: formData.description,
        type,
        credentialMode: formData.credentialMode,
        readOnly: true,
        ...(type === 'databricks'
          ? {
              host: '',
              password: '',
              warehouse_id: '',
              http_path: '',
              port: undefined,
              database: undefined,
              username: undefined,
              ssl: undefined,
            }
          : {
              host: '',
              port: type === 'postgres' ? 5432 : 3306,
              database: '',
              username: '',
              password: '',
              ssl: false,
              warehouse_id: undefined,
              http_path: undefined,
            }),
      },
      { keepDirty: false },
    )
    setSelectedType(type)
    setValue('type', type)
  }

  const onSubmit = async (data: DataSourceFormValues) => {
    const validation = await validateDataSourceFormSubmit({
      data,
      formData: watch(),
      sharedPasswordSecret,
      syncPasswordSecret,
      userCredentialAuthType,
      oauth2Config,
      oauthClientSecret,
    })
    if (!validation.ok) {
      setConnectionFieldErrors(validation.connectionFieldErrors)
      setUserAuthFieldErrors(validation.userAuthFieldErrors ?? {})
      return
    }

    setConnectionFieldErrors({})
    setUserAuthFieldErrors({})
    setSaving(true)

    try {
      const config = buildDataSourceSaveConfig(data, {
        sharedPasswordSecret,
        syncPasswordSecret,
        userCredentialAuthType,
        oauth2Config,
        oauthClientSecret,
      })

      let savedDataSource: DataSource
      if (dataSource) {
        savedDataSource = await modifyDataSource(dataSource.id, {
          name: data.name,
          description: data.description,
          config,
          credential_mode: data.credentialMode,
        })
        showSuccess(t('components.addDataSourceDialog.updateSuccess', { name: dataSource.name }))
        onSuccess?.()
        onClose()
        return { kind: 'updated' as const, savedDataSource }
      }

      savedDataSource = await addDataSource({
        name: data.name,
        type: data.type,
        managed: false,
        description: data.description,
        config,
        credential_mode: data.credentialMode,
      })
      showSuccess(t('components.addDataSourceDialog.createSuccess'))
      onSuccess?.()
      return { kind: 'created' as const, savedDataSource, name: savedDataSource.name, id: savedDataSource.id }
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      const message = error instanceof Error ? error.message : undefined
      showError(detail || message || t('components.addDataSourceDialog.saveFailed'))
      return { kind: 'error' as const }
    } finally {
      setSaving(false)
    }
  }

  return {
    register,
    handleSubmit,
    watch,
    setValue,
    errors,
    isSubmitting,
    saving,
    selectedType,
    watchedCredentialMode,
    watchedHost: String(watchedHost ?? ''),
    connectionFieldErrors,
    clearConnectionFieldErrors,
    sharedPasswordSecret,
    syncPasswordSecret,
    oauthClientSecret,
    userCredentialAuthType,
    setUserCredentialAuthType,
    oauth2Config,
    setOauth2Config,
    userAuthFieldErrors,
    setUserAuthFieldErrors,
    handleTypeChange,
    onSubmit,
  }
}