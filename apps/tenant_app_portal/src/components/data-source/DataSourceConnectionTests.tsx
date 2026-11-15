import ConnectionTestFeedback, { type ConnectionTestResult } from '@/components/ConnectionTestFeedback'
import { Button } from '@/components/ui/button'
import type { SecretCredentialFieldHandle } from '@/hooks/useSecretCredentialField'
import { testConnection, testSavedDataSourceConnection } from '@/lib/dataSourceApi'
import {
  applyNestedSecretKey,
  isSecretSatisfiedForTest,
  type SecretFieldBinding,
} from '@/lib/sensitiveCredential'
import { Loader2 } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { buildDatabricksConfig } from '@/components/data-source/DatabricksConnectionForm'
import { buildRDBMSConfig } from '@/components/data-source/RDBMSConnectionForm'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    components: {
      dataSourceConnectionTests: {
        testConnection: 'Test connection',
        testSyncLogin: 'Test sync login',
        testing: 'Testing...',
        fillSyncLogin: 'Enter sync username and password first.',
        fillConnection: 'Fill in all required connection fields first.',
        fillSyncToken: 'Enter sync access token first.',
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
      dataSourceConnectionTests: {
        testConnection: '测试连接',
        testSyncLogin: '测试同步账号',
        testing: '测试中...',
        fillSyncLogin: '请先填写同步用户名和密码。',
        fillConnection: '请先填写所有必填连接项。',
        fillSyncToken: '请先填写同步访问令牌。',
      },
    },
  },
  true,
  true
)

type DataSourceType = 'postgres' | 'mysql' | 'databricks'

function shortenConnectionError(message: string): string {
  const trimmed = message.trim()
  const bg = trimmed.indexOf('(Background on this error')
  if (bg > 0) return trimmed.slice(0, bg).trim()
  const sqlalchemy = trimmed.indexOf('[SQL:')
  if (sqlalchemy > 0) return trimmed.slice(0, sqlalchemy).trim()
  return trimmed
}

function buildUserModeSyncOverlay(
  type: DataSourceType,
  data: Record<string, unknown>,
  syncSecret?: SecretFieldBinding,
): Record<string, unknown> {
  let overlay: Record<string, unknown>
  if (type === 'databricks') {
    overlay = {
      host: data.host,
      extra_params: {
        warehouse_id: data.warehouse_id,
        ...(data.http_path ? { http_path: data.http_path } : {}),
      },
    }
    if (syncSecret) {
      return applyNestedSecretKey(overlay, 'metadata_sync', 'password', syncSecret)
    }
    return overlay
  } else {
    overlay = {
      readOnly: true,
      host: data.host,
      port: data.port,
      database: data.database,
      ssl: data.ssl || false,
      metadata_sync: {
        username: data.metadataSyncUsername,
      },
    }
  }
  if (syncSecret) {
    overlay = applyNestedSecretKey(overlay, 'metadata_sync', 'password', syncSecret)
  }
  return overlay
}

function buildSaveShapedOverlay(
  type: DataSourceType,
  credentialMode: 'shared' | 'user',
  data: Record<string, unknown>,
  sharedPasswordSecret?: SecretFieldBinding,
  syncPasswordSecret?: SecretFieldBinding,
): Record<string, unknown> {
  if (credentialMode === 'shared') {
    return type === 'databricks'
      ? buildDatabricksConfig(data, { passwordSecret: sharedPasswordSecret })
      : buildRDBMSConfig(data, { passwordSecret: sharedPasswordSecret })
  }
  return buildUserModeSyncOverlay(type, data, syncPasswordSecret)
}

interface DataSourceConnectionTestsProps {
  type: DataSourceType
  credentialMode: 'shared' | 'user'
  getFormData: () => Record<string, unknown>
  disabled?: boolean
  dataSourceId?: number
  sharedPasswordSecret?: SecretCredentialFieldHandle
  syncPasswordSecret?: SecretCredentialFieldHandle
}

export default function DataSourceConnectionTests({
  type,
  credentialMode,
  getFormData,
  disabled = false,
  dataSourceId,
  sharedPasswordSecret,
  syncPasswordSecret,
}: DataSourceConnectionTestsProps) {
  const { t } = useTranslation()
  const [testingId, setTestingId] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, ConnectionTestResult>>({})

  const applyResult = useCallback((testId: string, success: boolean, raw: string) => {
    setResults((prev) => ({
      ...prev,
      [testId]: {
        ok: success,
        message: shortenConnectionError(raw),
      },
    }))
  }, [])

  const runStatelessTest = useCallback(
    async (testId: string, config: Record<string, unknown>) => {
      setTestingId(testId)
      setResults((prev) => {
        const next = { ...prev }
        delete next[testId]
        return next
      })
      try {
        const result = await testConnection({ type, config })
        const raw = result.error || result.message || ''
        applyResult(testId, result.success, raw)
      } catch (error: unknown) {
        const err = error as { response?: { data?: { detail?: string } }; message?: string }
        const raw = err.response?.data?.detail || err.message || t('common.connectionTestFailed')
        applyResult(testId, false, String(raw))
      } finally {
        setTestingId(null)
      }
    },
    [applyResult, t, type]
  )

  const runSavedTest = useCallback(
    async (testId: string, overlay: Record<string, unknown>) => {
      if (!dataSourceId) return
      setTestingId(testId)
      setResults((prev) => {
        const next = { ...prev }
        delete next[testId]
        return next
      })
      try {
        const result = await testSavedDataSourceConnection(dataSourceId, overlay)
        const raw = result.error || result.message || ''
        applyResult(testId, result.success, raw)
      } catch (error: unknown) {
        const err = error as { response?: { data?: { detail?: string } }; message?: string }
        const raw = err.response?.data?.detail || err.message || t('common.connectionTestFailed')
        applyResult(testId, false, String(raw))
      } finally {
        setTestingId(null)
      }
    },
    [applyResult, dataSourceId, t]
  )

  const runConnectionTest = async (testId: string, data: Record<string, unknown>) => {
    const shaped = buildSaveShapedOverlay(
      type,
      credentialMode,
      data,
      sharedPasswordSecret,
      syncPasswordSecret,
    )
    if (dataSourceId) {
      await runSavedTest(testId, shaped)
      return
    }
    await runStatelessTest(testId, shaped)
  }

  const handleTestConnection = async () => {
    const data = getFormData()
    const passwordOk =
      sharedPasswordSecret != null
        ? isSecretSatisfiedForTest(sharedPasswordSecret)
        : Boolean(String(data.password ?? '').trim())

    if (type === 'databricks') {
      if (!data.host || !passwordOk || !data.warehouse_id) {
        setResults({
          connection: {
            ok: false,
            message: t('components.dataSourceConnectionTests.fillConnection'),
          },
        })
        return
      }
      await runConnectionTest('connection', data)
      return
    }
    if (!data.host || !data.port || !data.database || !data.username || !passwordOk) {
      setResults({
        connection: {
          ok: false,
          message: t('components.dataSourceConnectionTests.fillConnection'),
        },
      })
      return
    }
    await runConnectionTest('connection', data)
  }

  const handleTestSyncLogin = async () => {
    const data = getFormData()
    const syncOk =
      syncPasswordSecret != null
        ? isSecretSatisfiedForTest(syncPasswordSecret)
        : Boolean(String(data.metadataSyncPassword ?? '').trim())

    if (type === 'databricks') {
      if (!data.host || !data.warehouse_id || !syncOk) {
        setResults({
          sync: {
            ok: false,
            message: t('components.dataSourceConnectionTests.fillSyncToken'),
          },
        })
        return
      }
    } else if (
      !data.host ||
      !data.port ||
      !data.database ||
      !data.metadataSyncUsername ||
      !syncOk
    ) {
      setResults({
        sync: {
          ok: false,
          message: t('components.dataSourceConnectionTests.fillSyncLogin'),
        },
      })
      return
    }

    await runConnectionTest('sync', data)
  }

  const isUser = credentialMode === 'user'
  const testId = isUser ? 'sync' : 'connection'
  const result = results[testId]

  return (
    <div className="pt-2">
      <div className="flex min-w-0 flex-col gap-2">
        {result ? <ConnectionTestFeedback className="text-xs" result={result} errorOnNewLine /> : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || testingId !== null}
          className="h-9 w-full"
          onClick={() => void (isUser ? handleTestSyncLogin() : handleTestConnection())}
        >
          {testingId === testId ? (
            <>
              <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
              {t('components.dataSourceConnectionTests.testing')}
            </>
          ) : isUser ? (
            t('components.dataSourceConnectionTests.testSyncLogin')
          ) : (
            t('components.dataSourceConnectionTests.testConnection')
          )}
        </Button>
      </div>
    </div>
  )
}