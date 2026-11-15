import ConnectionTestFeedback from '@/components/ConnectionTestFeedback'
import { IntegrationSecretField } from '@/components/integration/IntegrationSecretField'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  isSecretSatisfiedForTest,
  secretPayloadValue,
  type SecretFieldBinding,
} from '@/lib/sensitiveCredential'
import { configuredSecretKeysFromConnection } from '@/lib/maskedFields'
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
  const [plainSecrets, setPlainSecrets] = useState<Record<string, string>>({})
  const [accountLabel, setAccountLabel] = useState('')
  const [configuredSecretKeys, setConfiguredSecretKeys] = useState<Set<string>>(() => new Set())
  const [testFeedback, setTestFeedback] = useState<{ ok: boolean; message: string } | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [secretBindings, setSecretBindings] = useState<Record<string, SecretFieldBinding>>({})
  const secretBindingsRef = useRef<Record<string, SecretFieldBinding>>({})

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

  const secretResetKey = `${resourceKind}-${resourceId}-${status?.status ?? 'none'}-${[...configuredSecretKeys].sort().join(',')}`

  useEffect(() => {
    setPlainSecrets({})
    setAccountLabel('')
    setConfiguredSecretKeys(new Set())
    setTestFeedback(null)
    setFieldErrors({})
    secretBindingsRef.current = {}
    setSecretBindings({})
  }, [resourceId, resourceKind])

  useEffect(() => {
    if (!status) {
      return
    }
    setAccountLabel(status.account_label ?? '')
    const publicSecrets = status.secrets_public ?? {}
    const configured = new Set(configuredSecretKeysFromConnection(status))
    setConfiguredSecretKeys(configured)
    const nextPlain: Record<string, string> = {}
    for (const field of secretFields) {
      if (isSensitiveFieldKey(field.key)) {
        continue
      }
      if (publicSecrets[field.key] !== undefined) {
        nextPlain[field.key] = String(publicSecrets[field.key])
      } else {
        nextPlain[field.key] = ''
      }
    }
    setPlainSecrets(nextPlain)
  }, [status, secretFields])

  const onSecretBindingChange = useCallback((key: string, binding: SecretFieldBinding) => {
    secretBindingsRef.current[key] = binding
    setSecretBindings((prev) => {
      const prior = prev[key]
      if (
        prior &&
        prior.mode === binding.mode &&
        prior.stored === binding.stored &&
        prior.editing === binding.editing &&
        prior.draft === binding.draft
      ) {
        return prev
      }
      return { ...prev, [key]: binding }
    })
  }, [])

  const bumpSecretRevision = useCallback(() => {
    setTestFeedback(null)
    setFieldErrors((prev) => {
      if (Object.keys(prev).length === 0) {
        return prev
      }
      return {}
    })
  }, [])

  const fieldSatisfied = useCallback(
    (key: string) => {
      if (isSensitiveFieldKey(key)) {
        const binding = secretBindings[key] ?? secretBindingsRef.current[key]
        if (!binding) {
          return false
        }
        return isSecretSatisfiedForTest(binding)
      }
      return Boolean(plainSecrets[key]?.trim())
    },
    [plainSecrets, secretBindings],
  )

  const secretsComplete = useMemo(
    () => secretFields.every((field) => fieldSatisfied(field.key)),
    [secretFields, fieldSatisfied],
  )

  const isConnected = status?.status === 'connected'

  const buildSecretsForApi = (): Record<string, string> => {
    const out: Record<string, string> = {}
    for (const field of secretFields) {
      if (isSensitiveFieldKey(field.key)) {
        const binding = secretBindingsRef.current[field.key]
        if (!binding) {
          continue
        }
        const payload = secretPayloadValue(binding)
        if (payload !== undefined) {
          out[field.key] = payload
        } else if (binding.stored && !binding.editing) {
          out[field.key] = ''
        }
      } else {
        const trimmed = plainSecrets[field.key]?.trim()
        if (trimmed) {
          out[field.key] = trimmed
        }
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
      setTestFeedback(null)
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
    setTestFeedback({ ok: false, message })
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
          t('myIntegrationConnection.testFailed'),
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
      setPlainSecrets({})
      setAccountLabel('')
      setConfiguredSecretKeys(new Set())
      setTestFeedback(null)
      secretBindingsRef.current = {}
      setSecretBindings({})
      queryClient.invalidateQueries({ queryKey })
      showSuccess(t('myIntegrationConnection.disconnected'))
      onConnectionChanged?.()
    },
    onError: (err: unknown) =>
      showError(getApiErrorMessage(err, t('myIntegrationConnection.testFailed'))),
  })

  if (credentialMode !== 'user') {
    return null
  }

  const statusKey = status?.status ?? 'not_connected'
  const statusLabel = t(`myIntegrationConnection.status.${statusKey}`, {
    defaultValue: t('myIntegrationConnection.status.unknown'),
  })
  const busy = saveMutation.isPending || testMutation.isPending

  const secretMode = (fieldKey: string): 'create' | 'edit' =>
    configuredSecretKeys.has(fieldKey) ? 'edit' : 'create'

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
        if (isSensitiveFieldKey(field.key)) {
          return (
            <IntegrationSecretField
              key={field.key}
              fieldKey={field.key}
              label={field.label}
              mode={secretMode(field.key)}
              stored={configuredSecretKeys.has(field.key)}
              resetKey={secretResetKey}
              disabled={busy}
              errorMsg={fieldErrors[field.key]}
              onBindingChange={onSecretBindingChange}
              onUserEdit={bumpSecretRevision}
            />
          )
        }
        return (
          <div key={field.key} className="space-y-1">
            <Label htmlFor={`${resourceKind}-${resourceId}-${field.key}`}>{field.label}</Label>
            <Input
              id={`${resourceKind}-${resourceId}-${field.key}`}
              autoComplete={field.key === 'username' ? 'username' : 'off'}
              value={plainSecrets[field.key] ?? ''}
              onChange={(e) => {
                setPlainSecrets((prev) => ({ ...prev, [field.key]: e.target.value }))
                bumpSecretRevision()
              }}
              onInput={(e) => {
                const value = e.currentTarget.value
                setPlainSecrets((prev) =>
                  prev[field.key] === value ? prev : { ...prev, [field.key]: value },
                )
                bumpSecretRevision()
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