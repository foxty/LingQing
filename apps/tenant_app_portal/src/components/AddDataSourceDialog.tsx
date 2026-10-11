import i18n from '@/i18n/config'
import DatabricksConnectionForm, {
  buildDatabricksConfig,
  databricksConnectionSchema,
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
        connectionConfig: 'Connection Configuration',
        updateSuccess: 'Data source {{name}} updated successfully',
        createSuccess: 'Data source created successfully',
        saveFailed: 'Failed to save data source',
        cancelConfirmTitle: 'Discard changes?',
        cancelConfirmDesc: 'You have unsaved changes. Are you sure you want to discard them?',
        continueEditing: 'Continue Editing',
        discard: 'Discard',
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
        connectionConfig: '连接配置',
        updateSuccess: '数据源 {{name}} 更新成功',
        createSuccess: '数据源创建成功',
        saveFailed: '保存数据源失败',
        cancelConfirmTitle: '放弃更改？',
        cancelConfirmDesc: '你有未保存的更改，确定要放弃吗？',
        continueEditing: '继续编辑',
        discard: '放弃',
      },
    },
  },
  true,
  true
)
import RDBMSConnectionForm, {
  buildRDBMSConfig,
  rdbmsConnectionSchema,
} from '@/components/data-source/RDBMSConnectionForm'
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
import { zodResolver } from '@hookform/resolvers/zod'
import { Database, InfoIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import * as z from 'zod'

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
    }
  }

  return {
    name: dataSource.name,
    description: dataSource.description || '',
    type: dataSource.type as DataSourceType,
    readOnly: dataSource.config?.readOnly ?? true,
    // RDBMS fields
    host: dataSource.config?.host || '',
    port: dataSource.config?.port || 5432,
    database: dataSource.config?.database || '',
    username: dataSource.config?.username || '',
    password: dataSource.config?.password || '',
    ssl: dataSource.config?.ssl || false,
    // Databricks fields
    warehouse_id: dataSource.config?.extra_params?.warehouse_id || '',
    http_path: dataSource.config?.extra_params?.http_path || '',
  }
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
  const [connectionValidationErrors, setConnectionValidationErrors] = useState<string[]>([])

  const {
    register,
    handleSubmit,
    watch,
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

  const onSubmit = async (data: FormData) => {
    console.log('[AddDataSourceDialog] onSubmit - mode:', dataSource ? 'EDIT' : 'CREATE')
    console.log('[AddDataSourceDialog] Form data:', data)

    // Validate connection details based on type
    setConnectionValidationErrors([])
    const formData = watch()
    const validationErrors: string[] = []

    try {
      if (data.type === 'databricks') {
        await databricksConnectionSchema.parseAsync(formData)
      } else {
        await rdbmsConnectionSchema.parseAsync(formData)
      }
    } catch (error: any) {
      if (error.errors) {
        error.errors.forEach((err: any) => {
          validationErrors.push(err.message)
        })
      }
      setConnectionValidationErrors(validationErrors)
      return
    }

    setSaving(true)

    try {
      // Delegate config building to respective form modules
      let config: Record<string, any>

      if (data.type === 'databricks') {
        config = buildDatabricksConfig(data)
      } else {
        config = buildRDBMSConfig(data)
      }

      console.log('[AddDataSourceDialog] Config to save:', config)

      let savedDataSource: DataSource

      if (dataSource) {
        // Update existing data source
        console.log('[AddDataSourceDialog] Calling modifyDataSource with id:', dataSource.id)
        savedDataSource = await modifyDataSource(dataSource.id, {
          name: data.name,
          description: data.description,
          config,
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
        <DialogContent className="sm:max-w-[700px] max-h-[85vh] flex flex-col">
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

          <form onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-hidden flex flex-col">
            <div className="flex-1 overflow-auto py-3 space-y-4 px-0">
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

                <div className="flex items-center gap-2">
                  <Label htmlFor="name" className="min-w-fit">
                    {t('components.addDataSourceDialog.name')}{' '}
                    <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="name"
                    {...register('name')}
                    placeholder={t('components.addDataSourceDialog.namePlaceholder')}
                    disabled={isSubmitting}
                    className="h-8 text-sm flex-1"
                    errorMsg={errors.name?.message as string}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Label htmlFor="description" className="min-w-fit">
                    {t('components.addDataSourceDialog.description')}
                  </Label>
                  <Input
                    id="description"
                    {...register('description')}
                    placeholder={t('components.addDataSourceDialog.descPlaceholder')}
                    disabled={isSubmitting}
                    multiple
                    className="text-sm flex-1"
                    errorMsg={errors.description?.message as string}
                  />
                </div>
              </div>

              {/* Connection Configuration */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  {t('components.addDataSourceDialog.connectionConfig')}
                </h3>

                {connectionValidationErrors.length > 0 && (
                  <div className="bg-destructive/10 border border-destructive/30 rounded p-3 text-xs text-destructive">
                    <ul className="list-disc list-inside">
                      {connectionValidationErrors.map((err, idx) => (
                        <li key={idx}>{err}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {selectedType === 'databricks' ? (
                  <DatabricksConnectionForm
                    register={register}
                    errors={errors}
                    disabled={isSubmitting}
                    getFormData={() => watch()}
                  />
                ) : (
                  <RDBMSConnectionForm
                    type={selectedType}
                    register={register}
                    errors={errors}
                    disabled={isSubmitting}
                    getFormData={() => watch()}
                  />
                )}
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
