import i18n from '@/i18n/config'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useGoogleDriveSource, useUpsertGoogleDriveSource } from '@/hooks/useDocumentSync'
import { useAuth } from '@/hooks/useAuth'
import { actionRules } from '@/lib/permissionRules'
import { getBackendUrl } from '@/lib/api'
import type { GoogleDriveSourceConfig } from '@/lib/documentSourcesApi'
import {
  AlertCircle,
  Check,
  Cloud,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  Save,
} from 'lucide-react'

const CALLBACK_PATH = '/document-sync/google/callback'
const GOOGLE_CREDENTIALS_URL = 'https://console.cloud.google.com/apis/credentials'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      documentSourcesTab: {
        title: 'Document Sources',
        description: 'Connect external file providers so users can sync folders into knowledge base collections.',
        googleDrive: 'Google Drive',
        googleDriveDesc: 'Users connect their own Google account and choose folders to sync.',
        statusNotConfigured: 'Not configured',
        statusEnabled: 'Enabled',
        statusDisabled: 'Disabled',
        setupTitle: 'Setup checklist',
        step1: 'Create an OAuth 2.0 client (Web application) in Google Cloud Console.',
        step1Link: 'Open Google Cloud Console',
        step2: 'Add this redirect URI to Authorized redirect URIs in that client:',
        step3: 'Enter the Client ID and Client Secret below, then turn on access and save.',
        credentialsTitle: 'OAuth credentials',
        clientId: 'Client ID',
        clientIdHint: 'From your Google OAuth client — sent as client_id during authorization.',
        clientSecret: 'Client Secret',
        clientSecretHint: 'Leave blank when saving to keep the stored secret unchanged.',
        clientSecretConfigured: 'A secret is already stored — enter a new value only to replace it.',
        enabled: 'Allow Google Drive connections',
        enabledHint: 'When off, users cannot connect Google Drive or sync folders.',
        callbackUrl: 'Redirect URI',
        copy: 'Copy',
        copied: 'Copied',
        save: 'Save changes',
        saving: 'Saving…',
        saveSuccess: 'Google Drive settings saved',
        saveFailed: 'Failed to save Google Drive settings',
        noPermission: 'You do not have permission to manage document sources',
        unsavedHint: 'You have unsaved changes',
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
    settings: {
      documentSourcesTab: {
        title: '文档来源',
        description: '连接外部文件提供商，让用户将文件夹同步到知识库集合。',
        googleDrive: 'Google Drive',
        googleDriveDesc: '用户连接自己的 Google 账号并选择要同步的文件夹。',
        statusNotConfigured: '未配置',
        statusEnabled: '已启用',
        statusDisabled: '已禁用',
        setupTitle: '配置步骤',
        step1: '在 Google Cloud Console 中创建 OAuth 2.0 客户端（Web 应用）。',
        step1Link: '打开 Google Cloud Console',
        step2: '在该客户端的 Authorized redirect URIs 中添加以下重定向 URI：',
        step3: '在下方填写 Client ID 与 Client Secret，然后开启访问并保存。',
        credentialsTitle: 'OAuth 凭据',
        clientId: 'Client ID',
        clientIdHint: '来自 Google OAuth 客户端 — 授权时作为 client_id 发送。',
        clientSecret: 'Client Secret',
        clientSecretHint: '保存时留空将保留已存储的密钥。',
        clientSecretConfigured: '已存储密钥 — 仅在需要更换时输入新值。',
        enabled: '允许 Google Drive 连接',
        enabledHint: '关闭后，用户无法连接 Google Drive 或同步文件夹。',
        callbackUrl: '重定向 URI',
        copy: '复制',
        copied: '已复制',
        save: '保存更改',
        saving: '保存中…',
        saveSuccess: 'Google Drive 设置已保存',
        saveFailed: '保存 Google Drive 设置失败',
        noPermission: '您没有管理文档来源的权限',
        unsavedHint: '有未保存的更改',
      },
    },
  },
  true,
  true
)

function ConfigStatusBadge({ source }: { source: GoogleDriveSourceConfig | undefined }) {
  const { t } = useTranslation()

  if (!source?.client_id?.trim()) {
    return <Badge variant="secondary">{t('settings.documentSourcesTab.statusNotConfigured')}</Badge>
  }
  if (source.enabled) {
    return <Badge>{t('settings.documentSourcesTab.statusEnabled')}</Badge>
  }
  return <Badge variant="outline">{t('settings.documentSourcesTab.statusDisabled')}</Badge>
}

function CopyableRedirectUri() {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const callbackUrl = getBackendUrl(CALLBACK_PATH)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(callbackUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard may be blocked
    }
  }

  return (
    <div className="flex gap-2">
      <Input readOnly value={callbackUrl} className="font-mono text-xs" aria-label={t('settings.documentSourcesTab.callbackUrl')} />
      <Button type="button" variant="outline" size="icon" className="shrink-0" onClick={copy}>
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        <span className="sr-only">
          {copied ? t('settings.documentSourcesTab.copied') : t('settings.documentSourcesTab.copy')}
        </span>
      </Button>
    </div>
  )
}

function SetupChecklist() {
  const { t } = useTranslation()

  return (
    <section className="rounded-lg border bg-muted/20 p-4">
      <h3 className="text-sm font-medium">{t('settings.documentSourcesTab.setupTitle')}</h3>
      <ol className="mt-3 space-y-4 text-sm">
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-background text-xs font-medium text-muted-foreground ring-1 ring-border">
            1
          </span>
          <div className="space-y-2 pt-0.5">
            <p className="text-muted-foreground">{t('settings.documentSourcesTab.step1')}</p>
            <a
              href={GOOGLE_CREDENTIALS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-foreground underline-offset-4 hover:underline"
            >
              {t('settings.documentSourcesTab.step1Link')}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-background text-xs font-medium text-muted-foreground ring-1 ring-border">
            2
          </span>
          <div className="min-w-0 flex-1 space-y-2 pt-0.5">
            <p className="text-muted-foreground">{t('settings.documentSourcesTab.step2')}</p>
            <CopyableRedirectUri />
          </div>
        </li>
        <li className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-background text-xs font-medium text-muted-foreground ring-1 ring-border">
            3
          </span>
          <p className="pt-0.5 text-muted-foreground">{t('settings.documentSourcesTab.step3')}</p>
        </li>
      </ol>
    </section>
  )
}

function CredentialField({
  id,
  label,
  hint,
  children,
}: {
  id: string
  label: string
  hint: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      <p className="text-[13px] leading-snug text-muted-foreground">{hint}</p>
    </div>
  )
}

export default function SettingsDocumentSourcesTab() {
  const { t } = useTranslation()
  const { hasAny } = useAuth()
  const canManage = hasAny(actionRules.canManageDocumentSources())
  const { data: source, isLoading } = useGoogleDriveSource()
  const upsertMutation = useUpsertGoogleDriveSource()

  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [showSecret, setShowSecret] = useState(false)

  useEffect(() => {
    if (source) {
      setClientId(source.client_id ?? '')
      setClientSecret('')
      setEnabled(source.enabled)
    }
  }, [source])

  const isDirty = useMemo(() => {
    if (!source) {
      return clientId.trim().length > 0 || enabled
    }
    return (
      clientId.trim() !== (source.client_id ?? '').trim() ||
      clientSecret.length > 0 ||
      enabled !== source.enabled
    )
  }, [source, clientId, clientSecret, enabled])

  if (!canManage) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{t('settings.documentSourcesTab.noPermission')}</AlertDescription>
      </Alert>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const handleSave = () => {
    upsertMutation.mutate({
      client_id: clientId.trim(),
      client_secret: clientSecret,
      enabled,
    })
  }

  const canSave = clientId.trim().length > 0 && isDirty && !upsertMutation.isPending

  return (
    <SettingsPageShell>
      <SettingsSection
        title={t('settings.documentSourcesTab.title')}
        description={t('settings.documentSourcesTab.description')}
        action={<ConfigStatusBadge source={source} />}
      >
        <div className="space-y-8">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border bg-background">
              <Cloud className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="min-w-0 space-y-1">
              <h3 className="text-base font-medium">{t('settings.documentSourcesTab.googleDrive')}</h3>
              <p className="text-sm text-muted-foreground">{t('settings.documentSourcesTab.googleDriveDesc')}</p>
            </div>
          </div>

          <SetupChecklist />

          <section className="space-y-4 border-t pt-6">
            <h3 className="text-sm font-medium">{t('settings.documentSourcesTab.credentialsTitle')}</h3>
            <div className="grid max-w-xl gap-5">
              <CredentialField
                id="google-drive-client-id"
                label={t('settings.documentSourcesTab.clientId')}
                hint={t('settings.documentSourcesTab.clientIdHint')}
              >
                <Input
                  id="google-drive-client-id"
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  placeholder="123456789.apps.googleusercontent.com"
                  autoComplete="off"
                />
              </CredentialField>

              <CredentialField
                id="google-drive-client-secret"
                label={t('settings.documentSourcesTab.clientSecret')}
                hint={
                  source?.client_secret_configured
                    ? t('settings.documentSourcesTab.clientSecretConfigured')
                    : t('settings.documentSourcesTab.clientSecretHint')
                }
              >
                <div className="relative">
                  <Input
                    id="google-drive-client-secret"
                    type={showSecret ? 'text' : 'password'}
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder={source?.client_secret_configured ? '••••••••' : ''}
                    autoComplete="new-password"
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                    onClick={() => setShowSecret((value) => !value)}
                  >
                    {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </CredentialField>
            </div>
          </section>

          <section className="border-t pt-6">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <Label htmlFor="google-drive-enabled">{t('settings.documentSourcesTab.enabled')}</Label>
                <p className="text-[13px] leading-snug text-muted-foreground">
                  {t('settings.documentSourcesTab.enabledHint')}
                </p>
              </div>
              <Switch id="google-drive-enabled" checked={enabled} onCheckedChange={setEnabled} />
            </div>
          </section>

          <div className="flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
            {isDirty ? (
              <p className="text-[13px] text-muted-foreground">{t('settings.documentSourcesTab.unsavedHint')}</p>
            ) : (
              <span />
            )}
            <Button onClick={handleSave} disabled={!canSave} className="sm:min-w-[140px]">
              {upsertMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              {upsertMutation.isPending
                ? t('settings.documentSourcesTab.saving')
                : t('settings.documentSourcesTab.save')}
            </Button>
          </div>
        </div>
      </SettingsSection>
    </SettingsPageShell>
  )
}
