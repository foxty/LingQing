import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import ConnectionTestFeedback from '@/components/ConnectionTestFeedback'

i18n.addResourceBundle('en', 'translation', {
  components: {
    rdbmsForm: {
      host: 'Host',
      port: 'Port',
      database: 'Database',
      databasePlaceholder: 'e.g. my_database',
      username: 'Username',
      usernamePlaceholder: 'e.g. db_user',
      password: 'Password',
      enableSsl: 'Enable SSL',
      testConnection: 'Test Connection',
      testing: 'Testing...',
      connectSuccess: 'Connection successful',
      connectFailed: 'Connection failed',
      completeRequiredFields: 'Fill in all required connection fields before testing.',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    rdbmsForm: {
      host: '主机',
      port: '端口',
      database: '数据库',
      databasePlaceholder: '例如 my_database',
      username: '用户名',
      usernamePlaceholder: '例如 db_user',
      password: '密码',
      enableSsl: '启用 SSL',
      testConnection: '测试连接',
      testing: '测试中...',
      connectSuccess: '连接成功',
      connectFailed: '连接失败',
      completeRequiredFields: '请先填写所有必填连接字段再测试。',
    },
  },
}, true, true)
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { testConnection } from '@/lib/dataSourceApi'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import type { FieldErrors, UseFormRegister } from 'react-hook-form'
import * as z from 'zod'
import {
  dsFieldLabelClass,
  dsFieldPairRowClass,
  dsFieldRowClass,
} from '@/components/data-source/formLayout'
import { isSavedSecretFormMask, STORED_SECRET_PLACEHOLDER } from '@/lib/storedSecrets'

type DataSourceType = 'postgres' | 'mysql'

// Schema definition for RDBMS connections
export const rdbmsConnectionSchema = z.object({
  host: z.string().min(1, 'Host is required'),
  port: z.coerce.number().int().min(1, 'Port is required').max(65535, 'Invalid port'),
  database: z.string().min(1, 'Database is required'),
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
  ssl: z
    .union([z.boolean(), z.string()])
    .transform((val) => val === true || val === 'true')
    .default(false),
})

export const rdbmsUserTemplateConnectionSchema = z.object({
  host: z.string().min(1, 'Host is required'),
  port: z.coerce.number().int().min(1, 'Port is required').max(65535, 'Invalid port'),
  database: z.string().min(1, 'Database is required'),
  ssl: z
    .union([z.boolean(), z.string()])
    .transform((val) => val === true || val === 'true')
    .default(false),
})

// Helper to build RDBMS config from form data
export function buildRDBMSConfig(data: any): Record<string, any> {
  const config: Record<string, any> = {
    readOnly: true,
  }
  if (data.host) config.host = data.host
  if (data.port) config.port = data.port
  if (data.database) config.database = data.database
  if (data.username) config.username = data.username
  if (data.password) {
    const pwd = String(data.password).trim()
    config.password = isSavedSecretFormMask(pwd) ? STORED_SECRET_PLACEHOLDER : pwd
  }
  if (data.ssl !== undefined) config.ssl = data.ssl
  return config
}

export function buildRDBMSUserTemplateConfig(data: any): Record<string, any> {
  const config: Record<string, any> = {
    readOnly: true,
  }
  if (data.host) config.host = data.host
  if (data.port) config.port = data.port
  if (data.database) config.database = data.database
  if (data.ssl !== undefined) config.ssl = data.ssl
  return config
}

export interface RDBMSConfig {
  host: string
  port: number
  database: string
  username: string
  password: string
  ssl: boolean
}

interface RDBMSConnectionFormProps {
  type: DataSourceType
  register: UseFormRegister<any>
  errors?: FieldErrors
  disabled?: boolean
  onFieldChange?: () => void
  getFormData?: () => any
  credentialMode?: 'shared' | 'user'
  showTestConnection?: boolean
  onClearSavedPassword?: () => void
}

export default function RDBMSConnectionForm({
  type,
  register,
  errors,
  disabled = false,
  onFieldChange,
  getFormData,
  credentialMode = 'shared',
  showTestConnection = true,
  onClearSavedPassword,
}: RDBMSConnectionFormProps) {
  const { t } = useTranslation()
  const isUserCredentialMode = credentialMode === 'user'
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
    if (
      !formData.host ||
      !formData.port ||
      !formData.database ||
      !formData.username ||
      !formData.password ||
      isSavedSecretFormMask(formData.password)
    ) {
      setConnectionTestResult(false, t('components.rdbmsForm.completeRequiredFields'))
      return
    }

    setTestingConnection(true)
    setConnectionTested(false)
    setConnectionMessage('')

    try {
      const config = {
        readOnly: true,
        host: formData.host,
        port: formData.port,
        database: formData.database,
        username: formData.username,
        password: formData.password,
        ssl: formData.ssl || false,
      }

      const result = await testConnection({
        type: type,
        config,
      })

      setConnectionTested(true)
      setConnectionSuccess(result.success)
      setConnectionMessage(result.message || (result.success ? t('components.rdbmsForm.connectSuccess') : t('components.rdbmsForm.connectFailed')))

      if (!result.success && result.error) {
        setConnectionMessage(result.error)
      }
    } catch (error: any) {
      setConnectionTested(true)
      setConnectionSuccess(false)
      setConnectionMessage(
        error.response?.data?.detail || error.message || t('components.rdbmsForm.connectFailed')
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
    <div className="space-y-2.5">
      <div className={dsFieldPairRowClass}>
        <Label htmlFor="host" className={dsFieldLabelClass}>
          {t('components.rdbmsForm.host')} <span className="text-destructive">*</span>
        </Label>
        <Input
          id="host"
          {...register('host')}
          placeholder="localhost"
          disabled={disabled}
          className="h-8 text-sm w-full min-w-0"
          onChange={(e) => {
            register('host').onChange(e)
            resetConnectionStatus()
          }}
          errorMsg={errors?.host?.message as string}
        />
        <Label htmlFor="port" className={dsFieldLabelClass}>
          {t('components.rdbmsForm.port')} <span className="text-destructive">*</span>
        </Label>
        <Input
          id="port"
          type="number"
          {...register('port')}
          placeholder={type === 'postgres' ? '5432' : '3306'}
          disabled={disabled}
          className="h-8 text-sm w-full min-w-0"
          onChange={(e) => {
            register('port').onChange(e)
            resetConnectionStatus()
          }}
          errorMsg={errors?.port?.message as string}
        />
      </div>

      <div className={dsFieldRowClass}>
        <Label htmlFor="database" className={dsFieldLabelClass}>
          {t('components.rdbmsForm.database')} <span className="text-destructive">*</span>
        </Label>
        <Input
          id="database"
          {...register('database')}
          placeholder={t('components.rdbmsForm.databasePlaceholder')}
          disabled={disabled}
          className="h-8 text-sm w-full min-w-0"
          onChange={(e) => {
            register('database').onChange(e)
            resetConnectionStatus()
          }}
          errorMsg={errors?.database?.message as string}
        />
      </div>

      {!isUserCredentialMode ? (
        <div className={dsFieldPairRowClass}>
          <Label htmlFor="username" className={dsFieldLabelClass}>
            {t('components.rdbmsForm.username')} <span className="text-destructive">*</span>
          </Label>
          <Input
            id="username"
            {...register('username')}
            placeholder={t('components.rdbmsForm.usernamePlaceholder')}
            disabled={disabled}
            autoComplete="off"
            className="h-8 text-sm w-full min-w-0"
            onChange={(e) => {
              register('username').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.username?.message as string}
          />
          <Label htmlFor="password" className={dsFieldLabelClass}>
            {t('components.rdbmsForm.password')} <span className="text-destructive">*</span>
          </Label>
          <Input
            id="password"
            type="password"
            {...register('password')}
            placeholder={t('components.rdbmsForm.password')}
            disabled={disabled}
            autoComplete="off"
            className="h-8 text-sm w-full min-w-0"
            onFocus={() => onClearSavedPassword?.()}
            onChange={(e) => {
              register('password').onChange(e)
              resetConnectionStatus()
            }}
            errorMsg={errors?.password?.message as string}
          />
        </div>
      ) : null}

      <div className={dsFieldRowClass}>
        <div className="col-start-2 flex items-center gap-2 min-w-0">
          <Checkbox
            id="ssl"
            {...register('ssl')}
            disabled={disabled}
            onCheckedChange={() => resetConnectionStatus()}
            errorMsg={errors?.ssl?.message as string}
          />
          <Label htmlFor="ssl" className="font-normal cursor-pointer text-sm">
            {t('components.rdbmsForm.enableSsl')}
          </Label>
        </div>
      </div>

      {showTestConnection && !isUserCredentialMode ? (
        <>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleTestConnection}
            disabled={testingConnection || disabled}
            className="h-9 w-full"
          >
            {testingConnection ? (
              <>
                <Loader2 className="w-3 h-3 mr-1.5 animate-spin" />
                {t('components.rdbmsForm.testing')}
              </>
            ) : (
              t('components.rdbmsForm.testConnection')
            )}
          </Button>

          {connectionTested ? (
            <ConnectionTestFeedback
              className="text-xs"
              result={{ ok: connectionSuccess, message: connectionMessage }}
              successFallback={t('components.rdbmsForm.connectSuccess')}
              failureFallback={t('components.rdbmsForm.connectFailed')}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
