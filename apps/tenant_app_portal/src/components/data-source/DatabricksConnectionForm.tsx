import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import ConnectionTestFeedback from '@/components/ConnectionTestFeedback'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      databricksForm: {
        serverHostname: 'Server Hostname',
        accessToken: 'Access Token',
        httpPath: 'HTTP Path',
        testConnection: 'Test Connection',
        testing: 'Testing...',
        connectSuccess: 'Connection successful',
        connectFailed: 'Connection failed',
        completeRequiredFields: 'Fill in all required connection fields before testing.',
        hint: 'Enter your Databricks connection details. Required fields are marked with *. After saving, search for tables across catalogs and schemas.',
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
      databricksForm: {
        serverHostname: '服务器主机名',
        accessToken: '访问令牌',
        httpPath: 'HTTP 路径',
        testConnection: '测试连接',
        testing: '测试中...',
        connectSuccess: '连接成功',
        connectFailed: '连接失败',
        completeRequiredFields: '请先填写所有必填连接字段再测试。',
        hint: '输入 Databricks 连接详情。必填字段标有 *。保存后可按目录、模式或表名搜索。',
      },
    },
  },
  true,
  true
)
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { testConnection } from '@/lib/dataSourceApi'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import type { FieldErrors, UseFormRegister } from 'react-hook-form'
import * as z from 'zod'

// Schema definition for Databricks connections
export const databricksConnectionSchema = z.object({
  host: z.string().min(1, 'Server hostname is required'),
  password: z.string().min(1, 'Access token is required'),
  warehouse_id: z.string().min(1, 'Warehouse ID is required'),
  http_path: z.string().optional(),
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

  const setConnectionTestResult = (ok: boolean, message: string) => {
    setConnectionTested(true)
    setConnectionSuccess(ok)
    setConnectionMessage(message)
  }

  const handleTestConnection = async () => {
    if (!getFormData) return

    const formData = getFormData()

    // Validate required fields
    if (!formData.host || !formData.password || !formData.warehouse_id) {
      setConnectionTestResult(false, t('components.databricksForm.completeRequiredFields'))
      return
    }

    setTestingConnection(true)
    setConnectionTested(false)
    setConnectionMessage('')

    try {
      const config = {
        host: formData.host,
        password: formData.password,
        extra_params: {
          warehouse_id: formData.warehouse_id,
          ...(formData.http_path && { http_path: formData.http_path }),
        },
      }

      const result = await testConnection({
        type: 'databricks',
        config,
      })

      setConnectionTested(true)
      setConnectionSuccess(result.success)
      setConnectionMessage(
        result.message ||
          (result.success
            ? t('components.databricksForm.connectSuccess')
            : t('components.databricksForm.connectFailed'))
      )

      if (!result.success && result.error) {
        setConnectionMessage(result.error)
      }
    } catch (error: any) {
      setConnectionTested(true)
      setConnectionSuccess(false)
      setConnectionMessage(
        error.response?.data?.detail ||
          error.message ||
          t('components.databricksForm.connectFailed')
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
    }
    onFieldChange?.()
  }

  return (
    <div className="space-y-2">
      <div className="space-y-2.5">
        <div className="flex items-center gap-2">
          <Label htmlFor="host" className="min-w-fit">
            {t('components.databricksForm.serverHostname')}{' '}
            <span className="text-destructive">*</span>
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

      {connectionTested ? (
        <ConnectionTestFeedback
          className="text-xs"
          result={{ ok: connectionSuccess, message: connectionMessage }}
          successFallback={t('components.databricksForm.connectSuccess')}
          failureFallback={t('components.databricksForm.connectFailed')}
        />
      ) : null}

      {/* Help Text */}
      <p className="text-xs text-muted-foreground pt-1">{t('components.databricksForm.hint')}</p>
    </div>
  )
}
