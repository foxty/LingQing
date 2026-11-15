import i18n from '@/i18n/config'
import DatabricksConnectionForm, {
  buildDatabricksConfig,
  buildDatabricksUserTemplateConfig,
  databricksConnectionSchema,
  databricksUserTemplateSchema,
} from '@/components/data-source/DatabricksConnectionForm'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      addDataSourceDialog: {
        title: 'Add Data Source',
        editTitle: 'Edit Data Source',
        createDescription: 'Connect a new data source for querying',
        editDescription: 'Edit data source {{name}}',
        typeChangeDisabled: 'Data source type cannot be changed after creation',
        basicInfo: 'Basic Information',
        name: 'Name',
        namePlaceholder: 'My Data Source',
        description: 'Description',
        descPlaceholder: 'Optional description',
        connectionConfig: 'Connection',
        connectionConfigSharedHint: 'Everyone uses this login to query data and refresh table lists.',
        connectionConfigUserTitle: 'Server',
        connectionConfigUserHint:
          'Where the database lives. Each person adds their own username and password on the Data Assets page.',
        updateSuccess: 'Data source {{name}} updated successfully',
        createSuccess: 'Data source created successfully',
        saveFailed: 'Failed to save data source',
        cancelConfirmTitle: 'Discard changes?',
        cancelConfirmDesc: 'You have unsaved changes. Are you sure you want to discard them?',
        continueEditing: 'Continue Editing',
        discard: 'Discard',
        credentialMode: 'Credential mode',
        credentialModeSharedTitle: 'Shared',
        credentialModeSharedSubtitle: 'One connection for the whole tenant',
        credentialModeUserTitle: 'Per-user',
        credentialModeUserSubtitle: 'Each member saves their own login',
        credentialModeHelpShared: 'Fill in one connection below.',
        credentialModeHelpUser:
          'Set the server, then a sync login. Members connect with their own login on Data Assets.',
        metadataSyncTitle: 'Sync login',
        metadataSyncHelp: 'Lists tables and updates schemas. Not used when people run queries.',
        metadataSyncUsername: 'Username',
        metadataSyncPassword: 'Password',
        metadataSyncToken: 'Access token',
      },
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    components: {
      addDataSourceDialog: {
        title: '添加数据源',
        editTitle: '编辑数据源',
        createDescription: '连接新的数据源进行查询',
        editDescription: '编辑数据源 {{name}}',
        typeChangeDisabled: '数据源类型创建后不可更改',
        basicInfo: '基本信息',
        name: '名称',
        namePlaceholder: '我的数据源',
        description: '描述',
        descPlaceholder: '可选描述',
        connectionConfig: '连接',
        connectionConfigSharedHint: '所有人用下方账号查询并刷新表列表。',
        connectionConfigUserTitle: '服务器',
        connectionConfigUserHint: '数据库地址；成员在数据资产页各自填写账号密码。',
        updateSuccess: '数据源 {{name}} 更新成功',
        createSuccess: '数据源创建成功',
        saveFailed: '保存数据源失败',
        cancelConfirmTitle: '放弃更改？',
        cancelConfirmDesc: '你有未保存的更改，确定要放弃吗？',
        continueEditing: '继续编辑',
        discard: '放弃',
        credentialMode: '凭证模式',
        credentialModeSharedTitle: '共享',
        credentialModeSharedSubtitle: '租户统一连接',
        credentialModeUserTitle: '用户',
        credentialModeUserSubtitle: '每人各自登录',
        credentialModeHelpShared: '在下方填写一套连接信息。',
        credentialModeHelpUser: '先填服务器，再填同步账号；成员在数据资产页使用自己的登录。',
        metadataSyncTitle: '同步账号',
        metadataSyncHelp: '用于列出台库表、更新表结构；不用于日常查询。',
        metadataSyncUsername: '用户名',
        metadataSyncPassword: '密码',
        metadataSyncToken: '访问令牌',
      },
    },
  },
  true,
  true
)
import RDBMSConnectionForm, {
  buildRDBMSConfig,
  buildRDBMSUserTemplateConfig,
  rdbmsConnectionSchema,
  rdbmsUserTemplateConnectionSchema,
} from '@/components/data-source/RDBMSConnectionForm'
import DataSourceConnectionTests from '@/components/data-source/DataSourceConnectionTests'
import DataSourceFormSectionHeader from '@/components/data-source/DataSourceFormSectionHeader'
import {
  type DataSourceConnectionFieldErrors,
  dsFieldLabelClass,
  dsFieldPairRowClass,
  dsFieldRowClass,
  dsFieldRowStartClass,
  resolveConnectionFieldError,
} from '@/components/data-source/formLayout'
import SelectAssetsDialog from '@/components/SelectAssetsDialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDataSources } from '@/hooks/useDataSources'
import { useNotification } from '@/hooks/useNotification'
import type { DataSource } from '@/lib/dataSourceApi'
import { SensitiveCredentialField } from '@/components/SensitiveCredentialField'
import { useSecretCredentialField } from '@/hooks/useSecretCredentialField'
import {
  applyNestedSecretKey,
  validateSecretRequired,
  validateSecretWhenEditing,
} from '@/lib/sensitiveCredential'
import { hasMaskedFieldPath } from '@/lib/maskedFields'
import { zodResolver } from '@hookform/resolvers/zod'
import { Database, InfoIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import * as z from 'zod'

const MASKED_DS_PASSWORD = 'config.password'
const MASKED_DS_SYNC_PASSWORD = 'config.metadata_sync.password'

type DataSourceType = 'postgres' | 'mysql' | 'databricks'

type FormData = z.infer<ReturnType<typeof getFormSchema>>

interface AddDataSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  dataSource?: DataSource | null
  onSuccess?: () => void
}

// Base schema - ONLY base fields, connection details validated in individual forms
const baseSchema = z.object({
  name: z.string().min(1).max(100),
  description: z.string().optional(),
  type: z.enum(['postgres', 'mysql', 'databricks']),
  credentialMode: z.enum(['shared', 'user']).default('shared'),
  metadataSyncUsername: z.string().optional(),
  metadataSyncPassword: z.string().optional(),
  readOnly: z.boolean().optional(),
  // Type-specific fields are stored but NOT validated at parent level
  // Each ConnectionForm handles its own validation
  host: z.any().optional(),
  port: z.any().optional(),
  password: z.any().optional(),
  database: z.any().optional(),
  username: z.any().optional(),
  ssl: z.any().optional(),
  warehouse_id: z.any().optional(),
  http_path: z.any().optional(),
})

// Helper function to get only base schema (parent only validates base fields)
const getFormSchema = () => {
  return baseSchema
}

// Helper to get default values
const getDefaultValues = (dataSource?: DataSource | null) => {
  if (!dataSource) {
    return {
      name: '',
      description: '',
      type: 'postgres' as DataSourceType,
      credentialMode: 'shared' as const,
      readOnly: true,
      // RDBMS fields
      host: '',
      port: 5432,
      database: '',
      username: '',
      password: '',
      ssl: false,
      // Databricks fields
      warehouse_id: '',
      http_path: '',
      metadataSyncUsername: '',
      metadataSyncPassword: '',
    }
  }

  return {
    name: dataSource.name,
    description: dataSource.description || '',
    type: dataSource.type as DataSourceType,
    credentialMode: (dataSource.credential_mode ?? 'shared') as 'shared' | 'user',
    readOnly: dataSource.config?.readOnly ?? true,
    // RDBMS fields
    host: dataSource.config?.host || '',
    port: dataSource.config?.port || 5432,
    database: dataSource.config?.database || '',
    username: dataSource.config?.username || '',
    password: '',
    ssl: dataSource.config?.ssl || false,
    // Databricks fields
    warehouse_id: dataSource.config?.extra_params?.warehouse_id || '',
    http_path: dataSource.config?.extra_params?.http_path || '',
    metadataSyncUsername: dataSource.config?.metadata_sync?.username || '',
    metadataSyncPassword: '',
  }
}

function attachMetadataSyncConfig(
  config: Record<string, any>,
  data: { credentialMode: string; type: string; metadataSyncUsername?: string },
  syncPasswordSecret?: ReturnType<typeof useSecretCredentialField>,
): Record<string, any> {
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

export default function AddDataSourceDialog({
  open,
  onOpenChange,
  dataSource,
  onSuccess,
}: AddDataSourceDialogProps) {
  const { t } = useTranslation()
  const { addDataSource, modifyDataSource } = useDataSources()
  const { showError, showSuccess } = useNotification()
  const [selectedType, setSelectedType] = useState<DataSourceType>('postgres')
  const [saving, setSaving] = useState(false)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [savedDataSourceId, setSavedDataSourceId] = useState<number | null>(null)
  const [savedDataSourceName, setSavedDataSourceName] = useState<string>('')
  const [selectAssetsDialogOpen, setSelectAssetsDialogOpen] = useState(false)
  const [connectionFieldErrors, setConnectionFieldErrors] =
    useState<DataSourceConnectionFieldErrors>({})

  const clearConnectionFieldErrors = () => setConnectionFieldErrors({})

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(getFormSchema()),
    defaultValues: getDefaultValues(dataSource),
    shouldUnregister: false,
    mode: 'onSubmit',
  })

  const formData = watch()

  const hasUnsavedData = () => {
    return !!(
      formData.name ||
      formData.description ||
      (formData as any).host ||
      (formData as any).port ||
      (formData as any).database ||
      (formData as any).username ||
      (formData as any).password
    )
  }

  useEffect(() => {
    if (Object.keys(errors).length > 0) {
      console.log('[AddDataSourceDialog] Form validation errors:', errors)
    }
  }, [errors])

  const watchedType = watch('type') as DataSourceType
  const watchedCredentialMode = watch('credentialMode')

  const storedMetadataSyncPassword = useMemo(
    () =>
      dataSource ? hasMaskedFieldPath(dataSource.masked_fields, MASKED_DS_SYNC_PASSWORD) : false,
    [dataSource]
  )
  const storedSharedPassword = useMemo(
    () => (dataSource ? hasMaskedFieldPath(dataSource.masked_fields, MASKED_DS_PASSWORD) : false),
    [dataSource]
  )

  const formMode = dataSource ? 'edit' : 'create'
  const secretResetKey = open ? (dataSource?.id ?? 'new') : 'closed'
  const sharedPasswordSecret = useSecretCredentialField(
    formMode,
    storedSharedPassword,
    `${secretResetKey}-shared`,
  )
  const syncPasswordSecret = useSecretCredentialField(
    formMode,
    storedMetadataSyncPassword,
    `${secretResetKey}-sync`,
  )

  // Update form validation schema when type changes
  useEffect(() => {
    if (watchedType !== selectedType) {
      setSelectedType(watchedType)
      // Clear validation errors when switching types since fields may differ
      reset(getDefaultValues(dataSource), {
        keepValues: true,
        keepErrors: false,
      })
    }
  }, [watchedType, selectedType, dataSource, reset])

  useEffect(() => {
    if (open) {
      // Reset form when dialog opens to get fresh defaultValues
      reset(getDefaultValues(dataSource))
      setSelectedType((dataSource?.type as DataSourceType) || 'postgres')
      clearConnectionFieldErrors()
    }
  }, [open, dataSource, reset])

  const handleTypeChange = (type: DataSourceType) => {
    // Reset form with new type defaults and clear errors
    reset(
      {
        name: formData.name,
        description: formData.description,
        type: type,
        readOnly: true,
        // Clear type-specific fields to reset to defaults
        ...(type === 'databricks'
          ? {
              // Databricks defaults
              host: '',
              password: '',
              warehouse_id: '',
              http_path: '',
              // Clear RDBMS fields
              port: undefined,
              database: undefined,
              username: undefined,
              ssl: undefined,
            }
          : {
              // RDBMS defaults
              host: '',
              port: type === 'postgres' ? 5432 : 3306,
              database: '',
              username: '',
              password: '',
              ssl: false,
              // Clear Databricks fields
              warehouse_id: undefined,
              http_path: undefined,
            }),
      },
      { keepDirty: false }
    )
    setSelectedType(type)
  }

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

  const applyZodIssuesToFieldErrors = (
    issues: { path: (string | number)[]; message: string }[],
    target: DataSourceConnectionFieldErrors,
  ) => {
    for (const issue of issues) {
      const key = issue.path[0]
      if (typeof key !== 'string' || !connectionFieldKeys.has(key as keyof DataSourceConnectionFieldErrors)) {
        continue
      }
      target[key as keyof DataSourceConnectionFieldErrors] = issue.message
    }
  }

  const mergeSecretFieldError = (
    existing: string | undefined,
    next: string | null,
  ): string | undefined => {
    if (!next) {
      return existing
    }
    return next
  }

  const onSubmit = async (data: FormData) => {
    const formData = watch()
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
          validateSecretWhenEditing(
            syncPasswordSecret,
            'Enter a new sync token or keep saved',
          ),
        )
      } else if (data.type === 'databricks') {
        await databricksConnectionSchema.omit({ password: true }).parseAsync(formData)
        fieldErrors.password = mergeSecretFieldError(
          fieldErrors.password,
          validateSecretRequired(sharedPasswordSecret, 'Access token is required'),
        )
        fieldErrors.password = mergeSecretFieldError(
          fieldErrors.password,
          validateSecretWhenEditing(
            sharedPasswordSecret,
            'Enter a new access token or keep saved',
          ),
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
          validateSecretWhenEditing(
            syncPasswordSecret,
            'Enter a new sync password or keep saved',
          ),
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
          validateSecretWhenEditing(
            sharedPasswordSecret,
            'Enter a new password or keep saved',
          ),
        )
      }
    } catch (error: any) {
      if (error.errors) {
        applyZodIssuesToFieldErrors(error.errors, fieldErrors)
      }
      setConnectionFieldErrors(fieldErrors)
      return
    }

    const hasFieldErrors = Object.values(fieldErrors).some(Boolean)
    if (hasFieldErrors) {
      setConnectionFieldErrors(fieldErrors)
      return
    }

    setConnectionFieldErrors({})

    setSaving(true)

    try {
      // Delegate config building to respective form modules
      let config: Record<string, any>

      if (data.type === 'databricks' && data.credentialMode === 'user') {
        config = buildDatabricksUserTemplateConfig(data)
      } else if (data.type === 'databricks') {
        config = buildDatabricksConfig(data, { passwordSecret: sharedPasswordSecret })
      } else if (data.credentialMode === 'user') {
        config = buildRDBMSUserTemplateConfig(data)
      } else {
        config = buildRDBMSConfig(data, { passwordSecret: sharedPasswordSecret })
      }

      config = attachMetadataSyncConfig(config, data, syncPasswordSecret)

      console.log('[AddDataSourceDialog] Config to save:', config)

      let savedDataSource: DataSource

      if (dataSource) {
        // Update existing data source
        console.log('[AddDataSourceDialog] Calling modifyDataSource with id:', dataSource.id)
        savedDataSource = await modifyDataSource(dataSource.id, {
          name: data.name,
          description: data.description,
          config,
          credential_mode: data.credentialMode,
        })
        showSuccess(t('components.addDataSourceDialog.updateSuccess', { name: dataSource.name }))
      } else {
        // Create new data source
        console.log('[AddDataSourceDialog] Calling addDataSource')
        savedDataSource = await addDataSource({
          name: data.name,
          type: data.type,
          managed: false,
          description: data.description,
          config,
          credential_mode: data.credentialMode,
        })
        showSuccess(t('components.addDataSourceDialog.createSuccess'))
      }

      console.log('[AddDataSourceDialog] Save successful, savedDataSource:', savedDataSource)

      // Success - save data source info for asset selection
      onSuccess?.()

      // For new data sources, show asset selection dialog
      if (!dataSource) {
        setSavedDataSourceId(savedDataSource.id)
        setSavedDataSourceName(savedDataSource.name)
        setSelectAssetsDialogOpen(true)
      } else {
        // For editing, just close the dialog
        handleClose()
      }
    } catch (error: any) {
      console.error('[AddDataSourceDialog] Submit error:', error)
      showError(
        error.response?.data?.detail ||
          error.message ||
          t('components.addDataSourceDialog.saveFailed')
      )
    } finally {
      setSaving(false)
    }
  }

  const handleClose = () => {
    if (!isSubmitting && !saving) {
      setSaving(false)
      setShowCloseConfirm(false)
      onOpenChange(false)
    }
  }

  const handleCloseWithConfirm = () => {
    if (!isSubmitting && !saving) {
      if (hasUnsavedData()) {
        setShowCloseConfirm(true)
      } else {
        handleClose()
      }
    }
  }

  const handleConfirmClose = () => {
    setShowCloseConfirm(false)
    setSaving(false)
    onOpenChange(false)
  }

  const handleSelectAssetsSuccess = () => {
    setSelectAssetsDialogOpen(false)
    handleClose()
  }

  return (
    <>
      <Dialog open={open} onOpenChange={handleCloseWithConfirm}>
        <DialogContent className="flex max-h-[85vh] min-h-0 min-w-0 flex-col sm:max-w-[700px]">
          <DialogHeader>
            <DialogTitle>
              {dataSource
                ? t('components.addDataSourceDialog.editTitle')
                : t('components.addDataSourceDialog.title')}
            </DialogTitle>
            <DialogDescription>
              {dataSource
                ? t('components.addDataSourceDialog.editDescription', { name: dataSource.name })
                : t('components.addDataSourceDialog.createDescription')}
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={handleSubmit(onSubmit)}
            className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
          >
            <div className="min-h-0 min-w-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto overscroll-contain py-3 pl-0.5 pr-5 [scrollbar-gutter:stable]">
              {/* Data Source Type */}
              <div className="grid grid-cols-3 gap-2">
                {(['postgres', 'mysql', 'databricks'] as const).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => handleTypeChange(type)}
                    disabled={isSubmitting || !!dataSource}
                    className={`p-2 border-2 rounded-lg text-center transition-colors ${
                      selectedType === type
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-primary/50'
                    } ${isSubmitting || !!dataSource ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <Database className="w-5 h-5 mx-auto mb-1" />
                    <p className="text-xs font-medium">
                      {type === 'postgres'
                        ? 'PostgreSQL'
                        : type === 'mysql'
                          ? 'MySQL'
                          : 'Databricks'}
                    </p>
                  </button>
                ))}
              </div>
              {dataSource && (
                <p className="text-xs text-muted-foreground">
                  {t('components.addDataSourceDialog.typeChangeDisabled')}
                </p>
              )}

              {/* Basic Information */}
              <div className="space-y-2.5">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <InfoIcon className="w-4 h-4" />
                  {t('components.addDataSourceDialog.basicInfo')}
                </h3>

                <div className={dsFieldRowClass}>
                  <Label htmlFor="name" className={dsFieldLabelClass}>
                    {t('components.addDataSourceDialog.name')}{' '}
                    <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="name"
                    {...register('name')}
                    placeholder={t('components.addDataSourceDialog.namePlaceholder')}
                    disabled={isSubmitting}
                    className="h-8 text-sm w-full min-w-0"
                    errorMsg={errors.name?.message as string}
                  />
                </div>

                <div className={dsFieldRowClass}>
                  <Label htmlFor="description" className={dsFieldLabelClass}>
                    {t('components.addDataSourceDialog.description')}
                  </Label>
                  <Input
                    id="description"
                    {...register('description')}
                    placeholder={t('components.addDataSourceDialog.descPlaceholder')}
                    disabled={isSubmitting}
                    multiple
                    className="h-8 text-sm w-full min-w-0"
                    errorMsg={errors.description?.message as string}
                  />
                </div>

                <div className={dsFieldRowStartClass}>
                  <Label className={`${dsFieldLabelClass} pt-2`}>
                    {t('components.addDataSourceDialog.credentialMode')}
                  </Label>
                  <div className="min-w-0 space-y-1.5">
                    <input type="hidden" {...register('credentialMode')} />
                    <div className="grid grid-cols-2 gap-2">
                      {(
                        [
                          {
                            value: 'shared' as const,
                            titleKey: 'credentialModeSharedTitle',
                            subtitleKey: 'credentialModeSharedSubtitle',
                          },
                          {
                            value: 'user' as const,
                            titleKey: 'credentialModeUserTitle',
                            subtitleKey: 'credentialModeUserSubtitle',
                          },
                        ] as const
                      ).map((option) => {
                        const selected = watchedCredentialMode === option.value
                        return (
                          <button
                            key={option.value}
                            type="button"
                            disabled={isSubmitting}
                            onClick={() =>
                              setValue('credentialMode', option.value, { shouldDirty: true })
                            }
                            className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                              selected
                                ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                                : 'border-border hover:border-primary/40 hover:bg-muted/40'
                            } ${isSubmitting ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                          >
                            <span className="block text-sm font-medium leading-tight">
                              {t(`components.addDataSourceDialog.${option.titleKey}`)}
                            </span>
                            <span className="block text-xs text-muted-foreground mt-0.5 leading-snug">
                              {t(`components.addDataSourceDialog.${option.subtitleKey}`)}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {watchedCredentialMode === 'user'
                        ? t('components.addDataSourceDialog.credentialModeHelpUser')
                        : t('components.addDataSourceDialog.credentialModeHelpShared')}
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-5">
                <div className="space-y-2.5">
                  <DataSourceFormSectionHeader
                    icon={Database}
                    title={
                      watchedCredentialMode === 'user'
                        ? t('components.addDataSourceDialog.connectionConfigUserTitle')
                        : t('components.addDataSourceDialog.connectionConfig')
                    }
                    description={
                      watchedCredentialMode === 'user'
                        ? t('components.addDataSourceDialog.connectionConfigUserHint')
                        : t('components.addDataSourceDialog.connectionConfigSharedHint')
                    }
                  />

                  {selectedType === 'databricks' ? (
                    <DatabricksConnectionForm
                      register={register}
                      errors={errors}
                      connectionFieldErrors={connectionFieldErrors}
                      disabled={isSubmitting}
                      getFormData={() => watch()}
                      showTestConnection={false}
                      credentialMode={watchedCredentialMode}
                      onFieldChange={clearConnectionFieldErrors}
                      sharedPasswordSecret={
                        watchedCredentialMode === 'shared' ? sharedPasswordSecret : undefined
                      }
                      sharedPasswordMaskedPreview={
                        watchedCredentialMode === 'shared' && dataSource?.config?.password
                          ? String(dataSource.config.password)
                          : null
                      }
                    />
                  ) : (
                    <RDBMSConnectionForm
                      type={selectedType}
                      register={register}
                      errors={errors}
                      connectionFieldErrors={connectionFieldErrors}
                      disabled={isSubmitting}
                      getFormData={() => watch()}
                      credentialMode={watchedCredentialMode}
                      showTestConnection={false}
                      onFieldChange={clearConnectionFieldErrors}
                      sharedPasswordSecret={
                        watchedCredentialMode === 'shared' ? sharedPasswordSecret : undefined
                      }
                      sharedPasswordMaskedPreview={
                        watchedCredentialMode === 'shared' && dataSource?.config?.password
                          ? String(dataSource.config.password)
                          : null
                      }
                    />
                  )}
                </div>

                {watchedCredentialMode === 'user' ? (
                  <div className="space-y-2.5 pt-2">
                    <DataSourceFormSectionHeader
                      title={t('components.addDataSourceDialog.metadataSyncTitle')}
                      description={t('components.addDataSourceDialog.metadataSyncHelp')}
                    />
                    {selectedType !== 'databricks' ? (
                      <div className={dsFieldPairRowClass}>
                        <Label htmlFor="metadataSyncUsername" className={dsFieldLabelClass}>
                          {t('components.addDataSourceDialog.metadataSyncUsername')}{' '}
                          <span className="text-destructive">*</span>
                        </Label>
                        <Input
                          id="metadataSyncUsername"
                          {...register('metadataSyncUsername', {
                            onChange: () => clearConnectionFieldErrors(),
                          })}
                          disabled={isSubmitting}
                          className="h-8 text-sm w-full min-w-0"
                          autoComplete="off"
                          errorMsg={resolveConnectionFieldError(
                            'metadataSyncUsername',
                            connectionFieldErrors,
                            errors,
                          )}
                        />
                        <Label htmlFor="metadataSyncPassword" className={dsFieldLabelClass}>
                          {t('components.addDataSourceDialog.metadataSyncPassword')}{' '}
                          <span className="text-destructive">*</span>
                        </Label>
                        <SensitiveCredentialField
                          id="metadataSyncPassword"
                          hideLabel
                          label={
                            <>
                              {t('components.addDataSourceDialog.metadataSyncPassword')}{' '}
                              <span className="text-destructive">*</span>
                            </>
                          }
                          binding={syncPasswordSecret}
                          maskedPreview={
                            dataSource?.config?.metadata_sync?.password
                              ? String(dataSource.config.metadata_sync.password)
                              : null
                          }
                          disabled={isSubmitting}
                          errorMsg={resolveConnectionFieldError(
                            'metadataSyncPassword',
                            connectionFieldErrors,
                            errors,
                          )}
                          onStartEdit={syncPasswordSecret.startEdit}
                          onCancelEdit={syncPasswordSecret.cancelEdit}
                          onDraftChange={(value) => {
                            syncPasswordSecret.setDraft(value)
                            clearConnectionFieldErrors()
                          }}
                        />
                      </div>
                    ) : (
                      <div className={dsFieldRowClass}>
                        <Label htmlFor="metadataSyncPassword" className={dsFieldLabelClass}>
                          {t('components.addDataSourceDialog.metadataSyncToken')}{' '}
                          <span className="text-destructive">*</span>
                        </Label>
                        <SensitiveCredentialField
                          id="metadataSyncPassword"
                          hideLabel
                          label={
                            <>
                              {t('components.addDataSourceDialog.metadataSyncToken')}{' '}
                              <span className="text-destructive">*</span>
                            </>
                          }
                          binding={syncPasswordSecret}
                          maskedPreview={
                            dataSource?.config?.metadata_sync?.password
                              ? String(dataSource.config.metadata_sync.password)
                              : null
                          }
                          disabled={isSubmitting}
                          errorMsg={resolveConnectionFieldError(
                            'metadataSyncPassword',
                            connectionFieldErrors,
                            errors,
                          )}
                          onStartEdit={syncPasswordSecret.startEdit}
                          onCancelEdit={syncPasswordSecret.cancelEdit}
                          onDraftChange={(value) => {
                            syncPasswordSecret.setDraft(value)
                            clearConnectionFieldErrors()
                          }}
                        />
                      </div>
                    )}
                  </div>
                ) : null}

                <DataSourceConnectionTests
                  key={`${selectedType}-${watchedCredentialMode}`}
                  type={selectedType}
                  credentialMode={watchedCredentialMode}
                  getFormData={() => watch()}
                  disabled={isSubmitting || saving}
                  dataSourceId={dataSource?.id}
                  sharedPasswordSecret={
                    watchedCredentialMode === 'shared' ? sharedPasswordSecret : undefined
                  }
                  syncPasswordSecret={
                    watchedCredentialMode === 'user' ? syncPasswordSecret : undefined
                  }
                />
              </div>
            </div>

            <DialogFooter className="mt-3 gap-2 flex items-center justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCloseWithConfirm}
                disabled={isSubmitting || saving}
                className="h-9"
              >
                {t('common.cancel')}
              </Button>
              <Button type="submit" size="sm" disabled={isSubmitting || saving} className="h-9">
                {saving ? t('common.loading') : dataSource ? t('common.confirm') : t('common.next')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Close Confirmation Dialog */}
      <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('components.addDataSourceDialog.cancelConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('components.addDataSourceDialog.cancelConfirmDesc')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('components.addDataSourceDialog.continueEditing')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmClose}
              className={buttonVariants({ variant: 'destructive' })}
            >
              {t('components.addDataSourceDialog.discard')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Select Assets Dialog for new data source */}
      {savedDataSourceId && (
        <SelectAssetsDialog
          open={selectAssetsDialogOpen}
          onOpenChange={setSelectAssetsDialogOpen}
          dataSourceId={savedDataSourceId}
          dataSourceName={savedDataSourceName}
          mode="create"
          onSuccess={handleSelectAssetsSuccess}
        />
      )}
    </>
  )
}
