import i18n from '@/i18n/config'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotification } from '@/hooks/useNotification'
import { getApiErrorMessage } from '@/lib/api'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Trash2,
} from 'lucide-react'
import {
  createAgentSlackIntegration,
  deleteAgentSlackIntegration,
  disableAgentSlackIntegration,
  downloadAgentSlackAppManifest,
  enableAgentSlackIntegration,
  prepareAgentSlackIntegration,
  testAgentSlackConnection,
  updateAgentSlackIntegration,
  type SlackIntegration,
  type SlackTestConnectionResponse,
} from '@/lib/slackApi'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agents: {
      slackIntegration: {
        title: 'Slack',
        description: 'Connect a dedicated Slack app so users can DM or @mention this agent.',
        connect: 'Connect Slack',
        update: 'Save credentials',
        botToken: 'Bot User OAuth Token',
        signingSecret: 'Signing Secret',
        eventsUrl: 'Events URL',
        interactionsUrl: 'Interactivity URL',
        interactivityNote:
          'Re-download the manifest (or set Interactivity URL in Slack app settings) so thumbs up/down feedback works on bot replies.',
        testConnection: 'Test connection',
        enable: 'Enable',
        disable: 'Disable',
        deleteIntegration: 'Remove Slack bot',
        downloadManifest: 'Download manifest',
        tokenInvalid: 'Bot token and signing secret are required',
        saveSuccess: 'Slack settings saved',
        saveFailed: 'Save failed',
        deleteSuccess: 'Slack bot removed',
        deleteFailed: 'Delete failed',
        confirmDelete: 'Remove this agent Slack bot? Existing channel mappings will stop working.',
        emptyTokenKeepsPrevious: 'Leave blank to keep the existing value.',
        statusConnected: 'Connected',
        statusDisabled: 'Disabled',
        statusNotConfigured: 'Not connected',
        disabledNotice:
          'Slack ingress is disabled. Messages from Slack are ignored until you enable this integration.',
        enableSuccess: 'Slack integration enabled',
        disableSuccess: 'Slack integration disabled',
        testSuccess: 'Slack connection successful',
        testSuccessDetail: 'Connected to {{team}} ({{teamId}}) as bot {{botUserId}}',
        testFailed: 'Slack connection test failed',
        downloadManifestFailed: 'Failed to download manifest',
        connectedApp: 'Connected Slack app',
        workspace: 'Workspace',
        appId: 'App ID',
        botUser: 'Bot user',
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
    agents: {
      slackIntegration: {
        title: 'Slack',
        description: '为此智能体连接独立 Slack 应用，支持私信与频道 @mention。',
        connect: '连接 Slack',
        update: '保存凭证',
        botToken: 'Bot User OAuth Token',
        signingSecret: 'Signing Secret',
        eventsUrl: 'Events URL',
        interactionsUrl: '交互 URL',
        interactivityNote:
          '重新下载 Manifest（或在 Slack 应用设置中配置 Interactivity URL），以便机器人回复支持点赞/点踩反馈。',
        testConnection: '测试连接',
        enable: '启用',
        disable: '禁用',
        deleteIntegration: '移除 Slack 机器人',
        downloadManifest: '下载 Manifest',
        tokenInvalid: 'Bot Token 和 Signing Secret 为必填项',
        saveSuccess: 'Slack 配置已保存',
        saveFailed: '保存失败',
        deleteSuccess: 'Slack 机器人已移除',
        deleteFailed: '删除失败',
        confirmDelete: '移除此智能体的 Slack 机器人？现有频道映射将失效。',
        emptyTokenKeepsPrevious: '留空则保留原值。',
        statusConnected: '已连接',
        statusDisabled: '已禁用',
        statusNotConfigured: '未连接',
        disabledNotice: 'Slack 入站已禁用。启用前，来自 Slack 的消息不会被处理。',
        enableSuccess: 'Slack 集成已启用',
        disableSuccess: 'Slack 集成已禁用',
        testSuccess: 'Slack 连接测试成功',
        testSuccessDetail: '已连接 {{team}}（{{teamId}}），机器人 {{botUserId}}',
        testFailed: 'Slack 连接测试失败',
        downloadManifestFailed: 'Manifest 下载失败',
        connectedApp: '已连接的 Slack 应用',
        workspace: '工作区',
        appId: 'App ID',
        botUser: '机器人用户',
      },
    },
  },
  true,
  true
)

type Props = {
  agentId: number
  canManage: boolean
  embedded?: boolean
  onChanged?: () => void
}

export default function AgentSlackIntegrationSection({
  agentId,
  canManage,
  embedded = false,
  onChanged,
}: Props) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(true)
  const [integration, setIntegration] = useState<SlackIntegration | null>(null)
  const [botToken, setBotToken] = useState('')
  const [signingSecret, setSigningSecret] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [downloadingManifest, setDownloadingManifest] = useState(false)
  const [testResult, setTestResult] = useState<SlackTestConnectionResponse | null>(null)
  const deleteConfirm = useConfirmation<SlackIntegration>()

  useEffect(() => {
    let active = true
    setLoading(true)
    prepareAgentSlackIntegration(agentId)
      .then((existing) => {
        if (active) setIntegration(existing)
      })
      .catch((error: Error) => showError(error.message))
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [agentId, showError])

  if (!canManage) {
    return null
  }

  const credentialsConfigured = Boolean(
    integration?.bot_token_configured && integration?.signing_secret_configured
  )
  const hasConnectedAppMetadata = Boolean(
    integration?.slack_team_name ||
      integration?.slack_team_id ||
      integration?.slack_app_id ||
      integration?.bot_user_id
  )

  const save = async () => {
    setSaving(true)
    try {
      if (credentialsConfigured) {
        const payload: Record<string, string> = {}
        if (botToken) payload.bot_token = botToken
        if (signingSecret) payload.signing_secret = signingSecret
        const updated = await updateAgentSlackIntegration(agentId, payload)
        setIntegration(updated)
      } else {
        if (!botToken || !signingSecret) {
          showError(t('agents.slackIntegration.tokenInvalid'))
          return
        }
        const created = await createAgentSlackIntegration(agentId, {
          bot_token: botToken,
          signing_secret: signingSecret,
          enabled: false,
        })
        setIntegration(created)
      }
      setBotToken('')
      setSigningSecret('')
      onChanged?.()
      showSuccess(t('agents.slackIntegration.saveSuccess'))
    } catch (error: unknown) {
      const detail =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      showError(detail || t('agents.slackIntegration.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    deleteConfirm.setLoading(true)
    try {
      await deleteAgentSlackIntegration(agentId)
      const refreshed = await prepareAgentSlackIntegration(agentId)
      setIntegration(refreshed)
      setTestResult(null)
      onChanged?.()
      showSuccess(t('agents.slackIntegration.deleteSuccess'))
      deleteConfirm.close()
    } catch (error: unknown) {
      const detail =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      showError(detail || t('agents.slackIntegration.deleteFailed'))
      deleteConfirm.setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('common.loading')}
      </div>
    )
  }

  const statusBadge = (
    <Badge
      variant={
        credentialsConfigured && integration?.enabled
          ? 'default'
          : credentialsConfigured
            ? 'secondary'
            : 'outline'
      }
    >
      {!credentialsConfigured
        ? t('agents.slackIntegration.statusNotConfigured')
        : integration?.enabled
          ? t('agents.slackIntegration.statusConnected')
          : t('agents.slackIntegration.statusDisabled')}
    </Badge>
  )

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-4 rounded-lg border p-4'}>
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          {!embedded ? (
            <h3 className="text-sm font-medium">{t('agents.slackIntegration.title')}</h3>
          ) : null}
          <p className={embedded ? 'text-sm text-muted-foreground' : 'text-xs text-muted-foreground'}>
            {t('agents.slackIntegration.description')}
          </p>
        </div>
        {statusBadge}
      </div>

      {credentialsConfigured && integration && !integration.enabled ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{t('agents.slackIntegration.disabledNotice')}</AlertDescription>
        </Alert>
      ) : null}

      {credentialsConfigured && integration && hasConnectedAppMetadata ? (
        <div className="rounded-md border bg-muted/30 p-3 text-xs">
          <p className="mb-2 font-medium text-muted-foreground">
            {t('agents.slackIntegration.connectedApp')}
          </p>
          <dl className="grid gap-1 sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">{t('agents.slackIntegration.workspace')}</dt>
              <dd className="font-mono">
                {integration.slack_team_name || '—'}
                {integration.slack_team_id ? ` (${integration.slack_team_id})` : ''}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t('agents.slackIntegration.appId')}</dt>
              <dd className="font-mono">{integration.slack_app_id || '—'}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">{t('agents.slackIntegration.botUser')}</dt>
              <dd className="font-mono">{integration.bot_user_id || '—'}</dd>
            </div>
          </dl>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={downloadingManifest}
          onClick={async () => {
            setDownloadingManifest(true)
            try {
              await downloadAgentSlackAppManifest(agentId)
              const refreshed = await prepareAgentSlackIntegration(agentId)
              setIntegration(refreshed)
              onChanged?.()
            } catch {
              showError(t('agents.slackIntegration.downloadManifestFailed'))
            } finally {
              setDownloadingManifest(false)
            }
          }}
        >
          {downloadingManifest ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          {t('agents.slackIntegration.downloadManifest')}
        </Button>
        <a
          href="https://api.slack.com/apps"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center text-xs text-primary underline-offset-4 hover:underline"
        >
          api.slack.com/apps
          <ExternalLink className="ml-1 h-3 w-3" />
        </a>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor={`slack-bot-token-${agentId}`}>{t('agents.slackIntegration.botToken')}</Label>
          <Input
            id={`slack-bot-token-${agentId}`}
            type="password"
            value={botToken}
            onChange={(event) => setBotToken(event.target.value)}
            placeholder={integration?.bot_token_configured ? '••••••••' : 'xoxb-...'}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`slack-signing-secret-${agentId}`}>
            {t('agents.slackIntegration.signingSecret')}
          </Label>
          <Input
            id={`slack-signing-secret-${agentId}`}
            type="password"
            value={signingSecret}
            onChange={(event) => setSigningSecret(event.target.value)}
            placeholder={integration?.signing_secret_configured ? '••••••••' : ''}
          />
        </div>
      </div>
      {credentialsConfigured ? (
        <p className="text-xs text-muted-foreground">{t('agents.slackIntegration.emptyTokenKeepsPrevious')}</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={save} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          {credentialsConfigured
            ? t('agents.slackIntegration.update')
            : t('agents.slackIntegration.connect')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={testing || !credentialsConfigured}
          onClick={async () => {
            setTesting(true)
            setTestResult(null)
            try {
              const result = await testAgentSlackConnection(agentId)
              setTestResult(result)
              if (result.ok) {
                const refreshed = await prepareAgentSlackIntegration(agentId)
                setIntegration(refreshed)
                onChanged?.()
              }
            } catch (error: unknown) {
              const detail = getApiErrorMessage(error, t('agents.slackIntegration.testFailed'))
              setTestResult({ ok: false, error: detail })
            } finally {
              setTesting(false)
            }
          }}
        >
          {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          {t('agents.slackIntegration.testConnection')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!credentialsConfigured || !integration}
          onClick={async () => {
            if (!integration) return
            const updated = integration.enabled
              ? await disableAgentSlackIntegration(agentId)
              : await enableAgentSlackIntegration(agentId)
            setIntegration(updated)
            onChanged?.()
            showSuccess(
              updated.enabled
                ? t('agents.slackIntegration.enableSuccess')
                : t('agents.slackIntegration.disableSuccess')
            )
          }}
        >
          {integration?.enabled
            ? t('agents.slackIntegration.disable')
            : t('agents.slackIntegration.enable')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive"
          disabled={!integration}
          onClick={() => integration && deleteConfirm.open(integration)}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          {t('agents.slackIntegration.deleteIntegration')}
        </Button>
      </div>

      {testResult?.ok ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertDescription>
            {t('agents.slackIntegration.testSuccessDetail', {
              team: testResult.team_name || testResult.team_id || '—',
              teamId: testResult.team_id || '—',
              botUserId: testResult.bot_user_id || '—',
            })}
          </AlertDescription>
        </Alert>
      ) : null}
      {testResult && !testResult.ok ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{testResult.error || t('agents.slackIntegration.testFailed')}</AlertDescription>
        </Alert>
      ) : null}

      {integration ? (
        <div className="space-y-2">
          <CopyableEventsUrl label={t('agents.slackIntegration.eventsUrl')} value={integration.events_url} />
          <CopyableEventsUrl
            label={t('agents.slackIntegration.interactionsUrl')}
            value={integration.interactions_url}
          />
          <p className="text-xs text-muted-foreground">{t('agents.slackIntegration.interactivityNote')}</p>
        </div>
      ) : null}

      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('common.delete')}
        description={() => t('agents.slackIntegration.confirmDelete')}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={remove}
        onCancel={deleteConfirm.close}
      />
    </div>
  )
}

function CopyableEventsUrl({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard may be blocked
    }
  }

  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <code className="break-all font-mono text-xs">{value}</code>
        <Button variant="outline" size="sm" onClick={copy} className="h-8 shrink-0 px-3 text-xs">
          {copied ? <Check className="mr-1.5 h-3.5 w-3.5" /> : <Copy className="mr-1.5 h-3.5 w-3.5" />}
          {copied ? t('settings.ssoForm.copied') : t('settings.ssoForm.copy')}
        </Button>
      </div>
    </div>
  )
}
