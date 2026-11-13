import ConnectionTestFeedback from '@/components/ConnectionTestFeedback'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage, sanitizeUserFacingMessage } from '@/lib/api'
import type { UserIntegrationConnectionUpsert } from '@/lib/dataSourceApi'
import {
  deleteMyApiConnectorConnection,
  getMyApiConnectorConnection,
  testMyApiConnectorConnection,
  upsertMyApiConnectorConnection,
} from '@/lib/apiConnectorApi'
import {
  deleteMyDataSourceConnection,
  getMyDataSourceConnection,
  testMyDataSourceConnection,
  upsertMyDataSourceConnection,
} from '@/lib/dataSourceApi'

export const SAVED_SECRET_MASK = '*****'

i18n.addResourceBundle('en', 'translation', {
  myIntegrationConnection: {
    title: 'My connection',
    save: 'Save',
    test: 'Test connection',
    disconnect: 'Disconnect',
    accountLabel: 'Account label (optional)',
    saved: 'Connection saved',
    disconnected: 'Disconnected',
    fillSecrets: 'Enter your credentials before saving or testing.',
    testBeforeSave: 'Fix the connection error below before saving.',
    testSuccess: 'Connection successful',
    testFailed: 'Connection failed',
    status: {
      not_connected: 'Not connected',
      connected: 'Connected',
      expired: 'Expired',
      unknown: 'Unknown',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  myIntegrationConnection: {
    title: '我的连接',
    save: '保存',
    test: '测试连接',
    disconnect: '断开',
    accountLabel: '账号备注（可选）',
    saved: '连接已保存',
    disconnected: '已断开连接',
    fillSecrets: '请先填写凭证再保存或测试。',
    testBeforeSave: '请先解决下方连接错误再保存。',
    testSuccess: '连接成功',
    testFailed: '连接失败',
    status: {
      not_connected: '未连接',
      connected: '已连接',
      expired: '已过期',
      unknown: '未知',
    },
  },
}, true, true)

type ResourceKind = 'data_source' | 'api_connector'

interface Props {
  resourceKind: ResourceKind
  resourceId: number
  credentialMode?: string
  authTypeHint?: string
  secretFields?: { key: string; label: string }[]
  onConnectionChanged?: () => void
  /** Called after a successful test-then-save (e.g. close dialog). */
  onSaved?: () => void
  compact?: boolean
}

function isSensitiveFieldKey(key: string): boolean {
  return key === 'password' || key.includes('token') || key === 'api_key'
}

export default function MyIntegrationConnectionPanel({
  resourceKind,
  resourceId,
  credentialMode = 'shared',
  authTypeHint = 'pat',
  secretFields = [{ key: 'password', label: 'Token / password' }],
  onConnectionChanged,
  onSaved,
  compact = false,
}: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { showError, showSuccess } = useNotification()
  const [secrets, setSecrets] = useState<Record<string, string>>({})
  const [accountLabel, setAccountLabel] = useState('')
  const [configuredSecretKeys, setConfiguredSecretKeys] = useState<Set<string>>(() => new Set())
  const [testFeedback, setTestFeedback] = useState<{ ok: boolean; message: string } | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const queryKey = ['my-integration-connection', resourceKind, resourceId]

  const { data: status, isLoading } = useQuery({
    queryKey,
    queryFn: () =>
      resourceKind === 'data_source'
        ? getMyDataSourceConnection(resourceId)
        : getMyApiConnectorConnection(resourceId),
    enabled: credentialMode === 'user',
    refetchOnMount: 'always',
  })

  useEffect(() => {
    setSecrets({})
    setAccountLabel('')
    setConfiguredSecretKeys(new Set())
    setTestFeedback(null)
    setFieldErrors({})
  }, [resourceId, resourceKind])

  useEffect(() => {
    if (!status) {
      return
    }
    setAccountLabel(status.account_label ?? '')
    const publicSecrets = status.secrets_public ?? {}
    const configured = new Set(status.secret_keys_configured ?? [])
    setConfiguredSecretKeys(configured)
    const nextSecrets: Record<string, string> = {}
    for (const field of secretFields) {
      if (publicSecrets[field.key] !== undefined) {
        nextSecrets[field.key] = publicSecrets[field.key]
      } else if (configured.has(field.key) && isSensitiveFieldKey(field.key)) {
        nextSecrets[field.key] = SAVED_SECRET_MASK
      } else {
        nextSecrets[field.key] = ''
      }
    }
    setSecrets(nextSecrets)
  }, [status, secretFields])

  const fieldSatisfied = (key: string) => {
    const value = (secrets[key] ?? '').trim()
    if (value && value !== SAVED_SECRET_MASK) {
      return true
    }
    return configuredSecretKeys.has(key) || value === SAVED_SECRET_MASK
  }

  const secretsComplete = useMemo(
    () => secretFields.every((field) => fieldSatisfied(field.key)),
    [secretFields, secrets, configuredSecretKeys]
  )

  const isConnected = status?.status === 'connected'

  const buildSecretsForApi = (): Record<string, string> => {
    const out: Record<string, string> = {}
    for (const field of secretFields) {
      const raw = secrets[field.key] ?? ''
      if (raw === SAVED_SECRET_MASK || !raw.trim()) {
        if (configuredSecretKeys.has(field.key) || raw === SAVED_SECRET_MASK) {
          out[field.key] = ''
        }
      } else {
        out[field.key] = raw
      }
    }
    return out
  }

  const formatConnectionMessage = (message: string, fallback: string) =>
    sanitizeUserFacingMessage(message, fallback)

  const buildConnectionBody = (): UserIntegrationConnectionUpsert => ({
    auth_type: authTypeHint,
    secrets: buildSecretsForApi(),
    account_label: accountLabel.trim() || undefined,
  })

  const runTest = async (body: UserIntegrationConnectionUpsert) => {
    if (resourceKind === 'data_source') {
      return testMyDataSourceConnection(resourceId, body)
    }
    return testMyApiConnectorConnection(resourceId, body)
  }

  const ensureSecretsOrMarkFields = (): boolean => {
    if (secretsComplete) {
      setFieldErrors({})
      return true
    }
    const missing: Record<string, string> = {}
    const message = t('myIntegrationConnection.fillSecrets')
    for (const field of secretFields) {
      if (!fieldSatisfied(field.key)) {
        missing[field.key] = message
      }
    }
    setFieldErrors(missing)
    return false
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!secretsComplete) {
        throw new Error(t('myIntegrationConnection.fillSecrets'))
      }
      const body = buildConnectionBody()
      const testRes = await runTest(body)
      if (!testRes.success) {
        const failMessage = formatConnectionMessage(
          testRes.message || '',
          t('myIntegrationConnection.testFailed')
        )
        throw new Error(failMessage)
      }
      if (resourceKind === 'data_source') {
        await upsertMyDataSourceConnection(resourceId, body)
      } else {
        await upsertMyApiConnectorConnection(resourceId, body)
      }
      return testRes
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
      showSuccess(t('myIntegrationConnection.saved'))
      onConnectionChanged?.()
      onSaved?.()
    },
    onError: (err: unknown) => {
      const message = getApiErrorMessage(err, t('myIntegrationConnection.testFailed'))
      setTestFeedback({ ok: false, message })
    },
  })

  const testMutation = useMutation({
    mutationFn: async () => {
      if (!secretsComplete) {
        throw new Error(t('myIntegrationConnection.fillSecrets'))
      }
      const body = buildConnectionBody()
      return runTest(body)
    },
    onSuccess: (res) => {
      const fallback = res.success
        ? t('myIntegrationConnection.testSuccess')
        : t('myIntegrationConnection.testFailed')
      const message = formatConnectionMessage(res.message || '', fallback)
      setTestFeedback({ ok: res.success, message })
    },
    onError: (err: unknown) => {
      const message = getApiErrorMessage(err, t('myIntegrationConnection.testFailed'))
      setTestFeedback({ ok: false, message })
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: () =>
      resourceKind === 'data_source'
        ? deleteMyDataSourceConnection(resourceId)
        : deleteMyApiConnectorConnection(resourceId),
    onSuccess: () => {
      setSecrets({})
      setAccountLabel('')
      setConfiguredSecretKeys(new Set())
      setTestFeedback(null)
      queryClient.invalidateQueries({ queryKey })
      showSuccess(t('myIntegrationConnection.disconnected'))
      onConnectionChanged?.()
    },
    onError: (err: unknown) => showError(getApiErrorMessage(err, t('myIntegrationConnection.testFailed'))),
  })

  if (credentialMode !== 'user') {
    return null
  }

  const statusKey = status?.status ?? 'not_connected'
  const statusLabel = t(`myIntegrationConnection.status.${statusKey}`, {
    defaultValue: t('myIntegrationConnection.status.unknown'),
  })
  const busy = saveMutation.isPending || testMutation.isPending

  return (
    <div className={compact ? 'space-y-3' : 'rounded-lg border p-4 space-y-3 bg-card'}>
      <p
        className={`text-xs font-medium ${
          statusKey === 'connected'
            ? 'text-success'
            : statusKey === 'expired'
              ? 'text-destructive'
              : 'text-muted-foreground'
        }`}
      >
        {isLoading ? '…' : statusLabel}
      </p>
      {secretFields.map((field) => {
        const sensitive = isSensitiveFieldKey(field.key)
        const value = secrets[field.key] ?? ''
        const showSavedMask = value === SAVED_SECRET_MASK
        return (
          <div key={field.key} className="space-y-1">
            <Label htmlFor={`${resourceKind}-${resourceId}-${field.key}`}>{field.label}</Label>
            <Input
              id={`${resourceKind}-${resourceId}-${field.key}`}
              type={sensitive && !showSavedMask ? 'password' : 'text'}
              autoComplete="off"
              value={secrets[field.key] ?? ''}
              onChange={(e) => {
                let value = e.target.value
                const prev = secrets[field.key] ?? ''
                if (prev === SAVED_SECRET_MASK && value !== SAVED_SECRET_MASK) {
                  if (value.startsWith(SAVED_SECRET_MASK)) {
                    value = value.slice(SAVED_SECRET_MASK.length)
                  }
                  setConfiguredSecretKeys((keys) => {
                    const next = new Set(keys)
                    next.delete(field.key)
                    return next
                  })
                }
                setSecrets((prevSecrets) => ({ ...prevSecrets, [field.key]: value }))
                setTestFeedback(null)
                setFieldErrors((prev) => {
                  if (!prev[field.key]) {
                    return prev
                  }
                  const next = { ...prev }
                  delete next[field.key]
                  return next
                })
              }}
              errorMsg={fieldErrors[field.key]}
            />
          </div>
        )
      })}
      <div className="space-y-1">
        <Label htmlFor={`${resourceKind}-${resourceId}-label`}>{t('myIntegrationConnection.accountLabel')}</Label>
        <Input
          id={`${resourceKind}-${resourceId}-label`}
          value={accountLabel}
          onChange={(e) => {
            setAccountLabel(e.target.value)
            setTestFeedback(null)
          }}
        />
      </div>
      {testFeedback ? (
        <ConnectionTestFeedback
          className="text-xs"
          result={testFeedback}
          successFallback={t('myIntegrationConnection.testSuccess')}
          failureFallback={t('myIntegrationConnection.testFailed')}
        />
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => {
            if (!ensureSecretsOrMarkFields()) {
              return
            }
            saveMutation.mutate()
          }}
          disabled={busy}
        >
          {t('myIntegrationConnection.save')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => {
            if (!ensureSecretsOrMarkFields()) {
              return
            }
            testMutation.mutate()
          }}
          disabled={busy}
        >
          {t('myIntegrationConnection.test')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => disconnectMutation.mutate()}
          disabled={disconnectMutation.isPending || !isConnected}
        >
          {t('myIntegrationConnection.disconnect')}
        </Button>
      </div>
    </div>
  )
}
