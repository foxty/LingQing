import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Alert, AlertDescription } from '@/components/ui/alert'

i18n.addResourceBundle('en', 'translation', {
  components: {
    databricksForm: {
      serverHostname: 'Server Hostname',
      accessToken: 'Access Token',
      httpPath: 'HTTP Path',
      catalog: 'Catalog',
      catalogPlaceholder: 'e.g. main',
      schema: 'Schema',
      schemaPlaceholder: 'e.g. default',
      testConnection: 'Test Connection',
      testing: 'Testing...',
      connectSuccess: 'Connection successful',
      connectFailed: 'Connection failed',
      hint: 'Enter your Databricks connection details. Required fields are marked with *.',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    databricksForm: {
      serverHostname: '服务器主机名',
      accessToken: '访问令牌',
      httpPath: 'HTTP 路径',
      catalog: '目录',
      catalogPlaceholder: '例如 main',
      schema: '模式',
      schemaPlaceholder: '例如 default',
      testConnection: '测试连接',
      testing: '测试中...',
      connectSuccess: '连接成功',
      connectFailed: '连接失败',
      hint: '输入你的 Databricks 连接详情。必填字段标有 *。',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { testConnection } from '@/lib/dataSourceApi'
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import { useState } from 'react'
import type { FieldErrors, UseFormRegister } from 'react-hook-form'
import * as z from 'zod'

// Schema definition for Databricks connections
export const databricksConnectionSchema = z.object({
  host: z.string().min(1, 'Server hostname is required'),
  password: z.string().min(1, 'Access token is required'),
  warehouse_id: z.string().min(1, 'Warehouse ID is required'),
  http_path: z.string().optional(),
  catalog: z.string().optional(),
  schema: z.string().optional(),
})

// Helper to build Databricks config from form data
export function buildDatabricksConfig(data: any): Record<string, any> {
  const config: Record<string, any> = {
    readOnly: true,
  }
  if (data.host) config.host = data.host
  if (data.password) config.password = data.password
  config.extra_params = {
    warehouse_id: data.warehouse_id,
    ...(data.http_path && { http_path: data.http_path }),
    ...(data.catalog && { catalog: data.catalog }),
    ...(data.schema && { schema: data.schema }),
  }
  return config
}

interface DatabricksConnectionFormProps {
  register: UseFormRegister<any>
  errors?: FieldErrors
  disabled?: boolean
  onFieldChange?: () => void
  getFormData?: () => any
}

export default function DatabricksConnectionForm({
  register,
  errors,
  disabled = false,
  onFieldChange,
  getFormData,
}: DatabricksConnectionFormProps) {
  const { t } = useTranslation()
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionTested, setConnectionTested] = useState(false)
  const [connectionSuccess, setConnectionSuccess] = useState(false)
  const [connectionMessage, setConnectionMessage] = useState('')
  const [testError, setTestError] = useState('')

  const handleTestConnection = async () => {
    if (!getFormData) return

    const formData = getFormData()

    // Validate required fields
    if (!formData.host || !formData.password || !formData.warehouse_id) {
      setTestError(t('common.failedToLoad'))
      return
    }

    setTestingConnection(true)
    setTestError('')
    setConnectionTested(false)
    setConnectionMessage('')

    try {
      const config = {
        host: formData.host,
        password: formData.password,
        extra_params: {
          warehouse_id: formData.warehouse_id,
          ...(formData.http_path && { http_path: formData.http_path }),
          ...(formData.catalog && { catalog: formData.catalog }),
          ...(formData.schema && { schema: formData.schema }),
        },
      }

      const result = await testConnection({
        type: 'databricks',
        config,
      })

      setConnectionTested(true)
      setConnectionSuccess(result.success)
      setConnectionMessage(result.message || (result.success ? t('components.databricksForm.connectSuccess') : t('components.databricksForm.connectFailed')))

      if (!result.success && result.error) {
        setConnectionMessage(result.error)
      }
    } catch (error: any) {
      setConnectionTested(true)
      setConnectionSuccess(false)
      setConnectionMessage(
        error.response?.data?.detail || error.message || t('components.databricksForm.connectFailed')
      )
    } finally {
      setTestingConnection(false)
    }
  }

  const resetConnectionStatus = () => {
    if (connectionTested) {
      setConnectionTested(false)
      setConnectionSuccess(false)
      setConnectionMessage('')
      setTestError('')
    }
    onFieldChange?.()
  }

  return (
    <div className="space-y-2">
      <div className="space-y-2.5">
        <div className="flex items-center gap-2">
          <Label htmlFor="host" className="min-w-fit">
            {t('components.databricksForm.serverHostname')} <span className="text-destructive">*</span>
          </Label>
          <Input
            id="host"
            {...register('host')}
            placeholder="adb-1234567890123456.7.azuredatabricks.net"
            disabled={disabled}
            className="h-8 text-sm flex-1"
            onChange={(e) => {
              register('host').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.host?.message as string}
          />
        </div>

        <div className="flex items-center gap-2">
          <Label htmlFor="password" className="min-w-fit">
             {t('components.databricksForm.accessToken')} <span className="text-destructive">*</span>
          </Label>
          <Input
            id="password"
            type="password"
            {...register('password')}
            placeholder="dapi••••••••••••••••"
            disabled={disabled}
            className="h-8 text-sm flex-1"
            onChange={(e) => {
              register('password').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.password?.message as string}
          />
        </div>

        <div className="flex items-center gap-2">
          <Label htmlFor="warehouse_id" className="min-w-fit">
            Warehouse ID <span className="text-destructive">*</span>
          </Label>
          <Input
            id="warehouse_id"
            {...register('warehouse_id')}
            placeholder="abc123def456"
            disabled={disabled}
            className="h-8 text-sm flex-1"
            onChange={(e) => {
              register('warehouse_id').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.warehouse_id?.message as string}
          />
        </div>

        <div className="flex items-center gap-2">
          <Label htmlFor="http_path" className="min-w-fit">
            {t('components.databricksForm.httpPath')}
          </Label>
          <Input
            id="http_path"
            {...register('http_path')}
            placeholder="/sql/1.0/warehouses/abc123def456"
            disabled={disabled}
            className="h-8 text-sm flex-1"
            onChange={(e) => {
              register('http_path').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.http_path?.message as string}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-center gap-2">
            <Label htmlFor="catalog" className="min-w-fit">
               {t('components.databricksForm.catalog')}
            </Label>
            <Input
              id="catalog"
              {...register('catalog')}
              placeholder={t('components.databricksForm.catalogPlaceholder')}
              disabled={disabled}
              className="h-8 text-sm flex-1"
              onChange={(e) => {
                register('catalog').onChange(e)
                resetConnectionStatus()
              }}
              errorMsg={errors?.catalog?.message as string}
            />
          </div>

          <div className="flex items-center gap-2">
            <Label htmlFor="schema" className="min-w-fit">
               {t('components.databricksForm.schema')}
            </Label>
            <Input
              id="schema"
              {...register('schema')}
              placeholder={t('components.databricksForm.schemaPlaceholder')}
              disabled={disabled}
              className="h-8 text-sm flex-1"
              onChange={(e) => {
                register('schema').onChange(e)
                resetConnectionStatus()
              }}
              errorMsg={errors?.schema?.message as string}
            />
          </div>
        </div>
      </div>

      {/* Test Connection Button */}
      <div className="pt-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleTestConnection}
          disabled={disabled || testingConnection}
          className="h-9 w-full"
        >
          {testingConnection ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              {t('components.databricksForm.testing')}
            </>
          ) : (
            t('components.databricksForm.testConnection')
          )}
        </Button>
      </div>

      {/* Test Error Message */}
      {testError && (
        <Alert variant="destructive" className="py-2">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-sm">{testError}</AlertDescription>
        </Alert>
      )}

      {/* Connection Test Result */}
      {connectionTested && (
        <Alert
          variant={connectionSuccess ? 'default' : 'destructive'}
          className={connectionSuccess ? 'py-2 border-green-200' : 'py-2'}
        >
          <div className="flex items-start gap-2">
            {connectionSuccess ? (
              <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5" />
            ) : (
              <AlertCircle className="h-4 w-4 mt-0.5" />
            )}
            <AlertDescription className="text-sm">
              <div className={connectionSuccess ? 'font-medium text-green-700' : 'font-medium'}>
                {connectionSuccess ? t('components.databricksForm.connectSuccess') : t('components.databricksForm.connectFailed')}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{connectionMessage}</div>
            </AlertDescription>
          </div>
        </Alert>
      )}

      {/* Help Text */}
      <p className="text-xs text-muted-foreground pt-1">
        {t('components.databricksForm.hint')}
      </p>
    </div>
  )
}
