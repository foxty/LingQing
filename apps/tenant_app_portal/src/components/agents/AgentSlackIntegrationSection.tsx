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
import SettingsSection from '@/components/SettingsSection'
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
        sectionConnection: 'Connection',
        sectionConnectionDesc: 'Workspace identity and ingress status after credentials are saved.',
        sectionSetup: 'Slack app setup',
        sectionSetupDesc: 'Create or open your Slack app, then download the manifest with the URLs below pre-filled.',
        sectionCredentials: 'Credentials',
        sectionCredentialsDesc: 'Write-only secrets. Values are never shown after save.',
        sectionEndpoints: 'Request URLs',
        sectionEndpointsDesc: 'Paste these into your Slack app Event Subscriptions and Interactivity settings.',
        configured: 'Configured',
        notConfigured: 'Not configured',
        secretStoredHint: 'Stored securely on the server.',
        replacePlaceholder: 'Paste new value to replace',
        botTokenPlaceholder: 'xoxb-...',
        signingSecretPlaceholder: 'Signing secret from Slack app',
        credentialsSummary: '{{configured}} of 2 credentials saved',
        connectionTestHint: 'Run Test connection to verify the workspace link.',
        dangerZone: 'Remove integration',
        dangerZoneDesc: 'Deletes this agent Slack bot and stops all Slack ingress for this agent.',
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
        sectionConnection: '连接状态',
        sectionConnectionDesc: '保存凭证后显示工作区身份与入站状态。',
        sectionSetup: 'Slack 应用配置',
        sectionSetupDesc: '创建或打开 Slack 应用，下载已预填下方 URL 的 Manifest。',
        sectionCredentials: '凭证',
        sectionCredentialsDesc: '仅写入，保存后不会回显明文。',
        sectionEndpoints: '请求 URL',
        sectionEndpointsDesc: '填入 Slack 应用的 Event Subscriptions 与 Interactivity 设置。',
        configured: '已配置',
        notConfigured: '未配置',
        secretStoredHint: '已安全存储在服务端。',
        replacePlaceholder: '粘贴新值以替换',
        botTokenPlaceholder: 'xoxb-...',
        signingSecretPlaceholder: 'Slack 应用的 Signing Secret',
        credentialsSummary: '已保存 {{configured}} / 2 项凭证',
        connectionTestHint: '运行「测试连接」以验证工作区绑定。',
        dangerZone: '移除集成',
        dangerZoneDesc: '删除此智能体的 Slack 机器人，并停止所有 Slack 入站消息。',
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
  const [saveError, setSaveError] = useState<string | null>(null)
  const deleteConfirm = useConfirmation<SlackIntegration>()

  useEffect(() => {
    let active = true
    setLoading(true)
    prepareAgentSlackIntegration(agentId)
      .then((existing) => {
        if (active) setIntegration(existing)
      })
      .catch((error: unknown) =>
        showError(getApiErrorMessage(error, t('agents.slackIntegration.saveFailed')))
      )
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
    setSaveError(null)
    try {
      if (credentialsConfigured) {
        const payload: Record<string, string> = {}
        if (botToken) payload.bot_token = botToken
        if (signingSecret) payload.signing_secret = signingSecret
        const updated = await updateAgentSlackIntegration(agentId, payload)
        setIntegration(updated)
      } else {
        if (!botToken || !signingSecret) {
          setSaveError(t('agents.slackIntegration.tokenInvalid'))
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
      setSaveError(getApiErrorMessage(error, t('agents.slackIntegration.saveFailed')))
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
      showError(getApiErrorMessage(error, t('agents.slackIntegration.deleteFailed')))
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

  const configuredCount =
    Number(integration?.bot_token_configured) + Number(integration?.signing_secret_configured)

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

  const runConnectionTest = async () => {
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
  }

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-4 rounded-lg border p-4'}>
      {!embedded ? (
        <div className="space-y-1">
          <h3 className="text-sm font-medium">{t('agents.slackIntegration.title')}</h3>
          <p className="text-xs text-muted-foreground">{t('agents.slackIntegration.description')}</p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('agents.slackIntegration.description')}</p>
      )}

      <SettingsSection
        title={t('agents.slackIntegration.sectionEndpoints')}
        description={t('agents.slackIntegration.sectionEndpointsDesc')}
      >
        {integration ? (
          <div className="space-y-3">
            <CopyableEventsUrl label={t('agents.slackIntegration.eventsUrl')} value={integration.events_url} />
            <CopyableEventsUrl
              label={t('agents.slackIntegration.interactionsUrl')}
              value={integration.interactions_url}
            />
            <p className="text-xs text-muted-foreground">{t('agents.slackIntegration.interactivityNote')}</p>
          </div>
        ) : null}
      </SettingsSection>

      <SettingsSection
        title={t('agents.slackIntegration.sectionSetup')}
        description={t('agents.slackIntegration.sectionSetupDesc')}
      >
        <div className="flex flex-wrap items-center gap-2">
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
            className="inline-flex items-center text-sm text-primary underline-offset-4 hover:underline"
          >
            api.slack.com/apps
            <ExternalLink className="ml-1 h-3.5 w-3.5" />
          </a>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agents.slackIntegration.sectionCredentials')}
        description={t('agents.slackIntegration.sectionCredentialsDesc')}
        action={
          <span className="text-xs text-muted-foreground">
            {t('agents.slackIntegration.credentialsSummary', { configured: configuredCount })}
          </span>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <CredentialField
              id={`slack-bot-token-${agentId}`}
              label={t('agents.slackIntegration.botToken')}
              configured={Boolean(integration?.bot_token_configured)}
              value={botToken}
              emptyPlaceholder={t('agents.slackIntegration.botTokenPlaceholder')}
              onChange={setBotToken}
            />
            <CredentialField
              id={`slack-signing-secret-${agentId}`}
              label={t('agents.slackIntegration.signingSecret')}
              configured={Boolean(integration?.signing_secret_configured)}
              value={signingSecret}
              emptyPlaceholder={t('agents.slackIntegration.signingSecretPlaceholder')}
              onChange={setSigningSecret}
            />
          </div>
          {credentialsConfigured ? (
            <p className="text-xs text-muted-foreground">
              {t('agents.slackIntegration.emptyTokenKeepsPrevious')}
            </p>
          ) : null}
          {saveError ? (
            <Alert variant="destructive">
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          ) : null}
          <div>
            <Button type="button" onClick={save} disabled={saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {credentialsConfigured
                ? t('agents.slackIntegration.update')
                : t('agents.slackIntegration.connect')}
            </Button>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agents.slackIntegration.sectionConnection')}
        description={t('agents.slackIntegration.sectionConnectionDesc')}
        action={statusBadge}
      >
        <div className="space-y-4">
          {credentialsConfigured && integration && !integration.enabled ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{t('agents.slackIntegration.disabledNotice')}</AlertDescription>
            </Alert>
          ) : null}

          {credentialsConfigured && integration && hasConnectedAppMetadata ? (
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
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
          ) : credentialsConfigured ? (
            <p className="text-sm text-muted-foreground">
              {t('agents.slackIntegration.connectionTestHint')}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('agents.slackIntegration.statusNotConfigured')}
            </p>
          )}

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
              <AlertDescription>
                {testResult.error || t('agents.slackIntegration.testFailed')}
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={testing || !credentialsConfigured}
              onClick={() => void runConnectionTest()}
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
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agents.slackIntegration.dangerZone')}
        description={t('agents.slackIntegration.dangerZoneDesc')}
      >
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="text-destructive hover:text-destructive"
          disabled={!integration || !credentialsConfigured}
          onClick={() => integration && deleteConfirm.open(integration)}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          {t('agents.slackIntegration.deleteIntegration')}
        </Button>
      </SettingsSection>

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

function CredentialField({
  id,
  label,
  configured,
  value,
  emptyPlaceholder,
  onChange,
}: {
  id: string
  label: string
  configured: boolean
  value: string
  emptyPlaceholder: string
  onChange: (value: string) => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <Badge variant={configured ? 'default' : 'outline'} className="gap-1 text-xs font-normal">
          {configured ? (
            <>
              <CheckCircle2 className="h-3 w-3" />
              {t('agents.slackIntegration.configured')}
            </>
          ) : (
            t('agents.slackIntegration.notConfigured')
          )}
        </Badge>
      </div>
      {configured ? (
        <p className="text-xs text-muted-foreground">{t('agents.slackIntegration.secretStoredHint')}</p>
      ) : null}
      <Input
        id={id}
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={
          configured ? t('agents.slackIntegration.replacePlaceholder') : emptyPlaceholder
        }
        autoComplete="off"
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
