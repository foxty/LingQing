import ConnectionTestFeedback, { type ConnectionTestResult } from '@/components/ConnectionTestFeedback'
import { Button } from '@/components/ui/button'
import { testConnection, testSavedDataSourceConnection } from '@/lib/dataSourceApi'
import { isSavedSecretFormMask, STORED_SECRET_PLACEHOLDER } from '@/lib/storedSecrets'
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

/** Flat connection for stateless sync-login test (create flow). */
function buildRDBMSSyncTestConfig(data: Record<string, unknown>): Record<string, unknown> {
  return {
    readOnly: true,
    host: data.host,
    port: data.port,
    database: data.database,
    username: data.metadataSyncUsername,
    password: data.metadataSyncPassword,
    ssl: data.ssl || false,
  }
}

function buildDatabricksSyncTestConfig(data: Record<string, unknown>): Record<string, unknown> {
  return {
    host: data.host,
    password: data.metadataSyncPassword,
    extra_params: {
      warehouse_id: data.warehouse_id,
      ...(data.http_path ? { http_path: data.http_path } : {}),
    },
  }
}

/** Same shape as save payload — backend merges placeholders with stored secrets. */
function buildSaveShapedOverlay(
  type: DataSourceType,
  credentialMode: 'shared' | 'user',
  data: Record<string, unknown>,
  useStoredSecret: boolean
): Record<string, unknown> {
  if (credentialMode === 'shared') {
    return type === 'databricks' ? buildDatabricksConfig(data) : buildRDBMSConfig(data)
  }

  const rawPwd = typeof data.metadataSyncPassword === 'string' ? data.metadataSyncPassword.trim() : ''
  const syncPassword =
    rawPwd && !isSavedSecretFormMask(rawPwd)
      ? rawPwd
      : useStoredSecret
        ? STORED_SECRET_PLACEHOLDER
        : rawPwd

  if (type === 'databricks') {
    return {
      host: data.host,
      extra_params: {
        warehouse_id: data.warehouse_id,
        ...(data.http_path ? { http_path: data.http_path } : {}),
      },
      metadata_sync: { password: syncPassword },
    }
  }

  return {
    readOnly: true,
    host: data.host,
    port: data.port,
    database: data.database,
    ssl: data.ssl || false,
    metadata_sync: {
      username: data.metadataSyncUsername,
      password: syncPassword,
    },
  }
}

interface DataSourceConnectionTestsProps {
  type: DataSourceType
  credentialMode: 'shared' | 'user'
  getFormData: () => Record<string, unknown>
  disabled?: boolean
  dataSourceId?: number
  storedMetadataSyncPassword?: boolean
  storedSharedPassword?: boolean
}

export default function DataSourceConnectionTests({
  type,
  credentialMode,
  getFormData,
  disabled = false,
  dataSourceId,
  storedMetadataSyncPassword = false,
  storedSharedPassword = false,
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

  const runConnectionTest = async (testId: string, data: Record<string, unknown>, overlay: Record<string, unknown>) => {
    if (dataSourceId) {
      const stored =
        credentialMode === 'user'
          ? storedMetadataSyncPassword
          : storedSharedPassword
      const useStored = Boolean(
        stored &&
          (credentialMode === 'user'
            ? (() => {
                const syncPwd =
                  typeof data.metadataSyncPassword === 'string' ? data.metadataSyncPassword.trim() : ''
                return !syncPwd || isSavedSecretFormMask(syncPwd)
              })()
            : (() => {
                const pwd = typeof data.password === 'string' ? data.password.trim() : ''
                return !pwd || isSavedSecretFormMask(pwd)
              })())
      )
      const shaped = buildSaveShapedOverlay(type, credentialMode, data, useStored)
      await runSavedTest(testId, shaped)
      return
    }
    await runStatelessTest(
      testId,
      credentialMode === 'user'
        ? type === 'databricks'
          ? buildDatabricksSyncTestConfig(data)
          : buildRDBMSSyncTestConfig(data)
        : overlay
    )
  }

  const handleTestConnection = async () => {
    const data = getFormData()
    if (type === 'databricks') {
      if (!data.host || !data.password || !data.warehouse_id) {
        setResults({
          connection: {
            ok: false,
            message: t('components.dataSourceConnectionTests.fillConnection'),
          },
        })
        return
      }
      await runConnectionTest('connection', data, buildDatabricksConfig(data))
      return
    }
    if (!data.host || !data.port || !data.database || !data.username || !data.password) {
      setResults({
        connection: {
          ok: false,
          message: t('components.dataSourceConnectionTests.fillConnection'),
        },
      })
      return
    }
    await runConnectionTest('connection', data, buildRDBMSConfig(data))
  }

  const handleTestSyncLogin = async () => {
    const data = getFormData()
    const syncPwd = typeof data.metadataSyncPassword === 'string' ? data.metadataSyncPassword.trim() : ''

    if (type === 'databricks') {
      if (
        !data.host ||
        !data.warehouse_id ||
        (!syncPwd && !storedMetadataSyncPassword) ||
        (isSavedSecretFormMask(syncPwd) && !storedMetadataSyncPassword)
      ) {
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
      ((!syncPwd && !storedMetadataSyncPassword) ||
        (isSavedSecretFormMask(syncPwd) && !storedMetadataSyncPassword))
    ) {
      setResults({
        sync: {
          ok: false,
          message: t('components.dataSourceConnectionTests.fillSyncLogin'),
        },
      })
      return
    }

    await runConnectionTest('sync', data, {})
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
