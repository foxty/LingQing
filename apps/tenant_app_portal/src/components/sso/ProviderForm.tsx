import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useNotification } from '@/hooks/useNotification'
import { Check, Copy, Info, Loader2 } from 'lucide-react'
import {
  createAuthProvider,
  updateAuthProvider,
  type AuthProvider,
  type FirstLoginPolicy,
} from '@/lib/ssoApi'
import { CUSTOM_PRESET_KEY, SSO_PRESETS, type SsoPreset } from '@/lib/ssoPresets'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    ssoForm: {
      description: 'Configure an OIDC identity provider for this tenant.',
      displayName: 'Display Name',
      displayNameHint: 'Shown on the login page as the SSO button label.',
      issuerUrl: 'Issuer URL',
      issuerUrlHint: "Your IdP's OIDC issuer. We auto-fetch {issuer}/.well-known/openid-configuration.",
      issuerExamples: 'Examples — Google: https://accounts.google.com · Okta: https://<tenant>.okta.com · Entra: https://login.microsoftonline.com/<tenant-id>/v2.0',
      clientId: 'Client ID',
      clientIdHint: "From your IdP's app registration. Sent as client_id in the authorize request.",
      clientSecret: 'Client Secret',
      clientSecretHint: "From your IdP's app registration. Leave blank on edit to keep the stored secret.",
      clientSecretConfigured: 'Client secret configured',
      firstLoginPolicy: 'First Login Policy',
      firstLoginPolicyHint: 'What happens when a user logs in with no existing account.',
      policyJit: 'JIT: auto-create user',
      policyJitHint: 'Auto-create the internal user on first login.',
      policyPending: 'Need approval',
      policyPendingHint: 'Store the identity as pending; an admin must approve before login succeeds.',
      policyReject: 'Reject unknown users',
      policyRejectHint: 'Deny unknown users. Pre-provisioned members still log in via email match.',
      enabled: 'Enabled',
      enabledHint: 'Disabled providers are not shown on the login page.',
      callbackUrl: 'Callback URL',
      callbackUrlHint: 'Paste this into your IdP app registration.',
      callbackUrlNote: 'The full URL with ?provider_id appears here after you save.',
      copy: 'Copy',
      copied: 'Copied',
      save: 'Save',
      cancel: 'Cancel',
      addProvider: 'Add OIDC Provider',
      editProvider: 'Edit Provider',
      saveSuccess: 'Saved',
      saveFailed: 'Save failed',
      presetLabel: 'Choose a template',
      presetCustom: 'Custom',
      presetCustomHint: 'Start from scratch with a raw OIDC issuer.',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    ssoForm: {
      description: '为本租户配置一个 OIDC 身份提供商。',
      displayName: '显示名称',
      displayNameHint: '将作为登录页 SSO 按钮的标签显示。',
      issuerUrl: 'Issuer URL',
      issuerUrlHint: 'IdP 的 OIDC 发行者。系统会自动获取 {issuer}/.well-known/openid-configuration。',
      issuerExamples: '示例 — Google: https://accounts.google.com · Okta: https://<tenant>.okta.com · Entra: https://login.microsoftonline.com/<tenant-id>/v2.0',
      clientId: 'Client ID',
      clientIdHint: '来自 IdP 应用注册。作为 client_id 发送到授权请求。',
      clientSecret: 'Client Secret',
      clientSecretHint: '来自 IdP 应用注册。编辑时留空以保留已存储的密钥。',
      clientSecretConfigured: '已配置 Client Secret',
      firstLoginPolicy: '首次登录策略',
      firstLoginPolicyHint: '当无既有账户的用户登录时的处理方式。',
      policyJit: 'JIT：自动创建用户',
      policyJitHint: '首次登录时自动创建内部用户。',
      policyPending: '需要审批',
      policyPendingHint: '将身份存为待审批；管理员审批后才能登录成功。',
      policyReject: '拒绝未知用户',
      policyRejectHint: '拒绝未知用户。已预置的成员仍可通过邮箱匹配登录。',
      enabled: '已启用',
      enabledHint: '禁用的提供商不会显示在登录页。',
      callbackUrl: '回调 URL',
      callbackUrlHint: '将此 URL 粘贴到 IdP 应用注册中。',
      callbackUrlNote: '保存后将显示带 ?provider_id 的完整 URL。',
      copy: '复制',
      copied: '已复制',
      save: '保存',
      cancel: '取消',
      addProvider: '添加 OIDC 提供商',
      editProvider: '编辑提供商',
      saveSuccess: '已保存',
      saveFailed: '保存失败',
      presetLabel: '选择模板',
      presetCustom: '自定义',
      presetCustomHint: '从零开始，使用原始 OIDC issuer。',
    },
  },
}, true, true)

interface ProviderFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editingId: number | null
  existing: AuthProvider | null
  onSaved: () => void
}

interface FormState {
  display_name: string
  issuer: string
  client_id: string
  client_secret: string
  first_login_policy: FirstLoginPolicy
  enabled: boolean
}

const emptyForm: FormState = {
  display_name: '',
  issuer: '',
  client_id: '',
  client_secret: '',
  first_login_policy: 'jit_create',
  enabled: false,
}

export default function ProviderForm({
  open,
  onOpenChange,
  editingId,
  existing,
  onSaved,
}: ProviderFormProps) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [saving, setSaving] = useState(false)

  const initial: FormState = existing
    ? {
        display_name: existing.display_name,
        issuer: existing.config.issuer,
        client_id: existing.config.client_id,
        client_secret: '',
        first_login_policy: existing.first_login_policy,
        enabled: existing.enabled,
      }
    : emptyForm

  const [form, setForm] = useState<FormState>(initial)
  const [presetKey, setPresetKey] = useState<string>(CUSTOM_PRESET_KEY)

  // Re-sync form state whenever the dialog opens or the target provider changes.
  useEffect(() => {
    if (open) {
      setForm(initial)
      setPresetKey(CUSTOM_PRESET_KEY)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingId, existing?.id])

  const applyPreset = (preset: SsoPreset) => {
    setPresetKey(preset.key)
    // Only prefill fields a preset can authoritatively set: display name + issuer.
    // Never touch client_secret / first_login_policy / enabled (security-sensitive).
    setForm((f) => ({
      ...f,
      display_name: preset.displayName,
      issuer: preset.issuerTemplate,
    }))
  }

  const selectCustom = () => {
    setPresetKey(CUSTOM_PRESET_KEY)
    setForm((f) => ({ ...f, display_name: '', issuer: '' }))
  }

  const save = async () => {
    setSaving(true)
    try {
      const cfg = {
        client_id: form.client_id,
        issuer: form.issuer,
        scopes: ['openid', 'email', 'profile'],
        ...(form.client_secret ? { client_secret: form.client_secret } : {}),
      }
      if (editingId === null) {
        await createAuthProvider({
          display_name: form.display_name,
          provider_type: 'oidc',
          enabled: form.enabled,
          config: cfg,
          first_login_policy: form.first_login_policy,
        })
      } else {
        await updateAuthProvider(editingId, {
          display_name: form.display_name,
          enabled: form.enabled,
          config: cfg,
        })
      }
      showSuccess(t('settings.ssoForm.saveSuccess'))
      onSaved()
      onOpenChange(false)
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.ssoForm.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {editingId === null ? t('settings.ssoForm.addProvider') : t('settings.ssoForm.editProvider')}
          </DialogTitle>
          <DialogDescription>{t('settings.ssoForm.description')}</DialogDescription>
        </DialogHeader>

        {editingId === null && (
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.ssoForm.presetLabel')}
            </Label>
            <div className="flex flex-wrap gap-2">
              {SSO_PRESETS.map((p) => (
                <PresetChip
                  key={p.key}
                  preset={p}
                  active={presetKey === p.key}
                  onClick={() => applyPreset(p)}
                />
              ))}
              <PresetChip
                preset={{
                  key: CUSTOM_PRESET_KEY,
                  displayName: t('settings.ssoForm.presetCustom'),
                  issuerTemplate: '',
                  issuerHint: t('settings.ssoForm.presetCustomHint'),
                  scopes: ['openid', 'email', 'profile'],
                }}
                active={presetKey === CUSTOM_PRESET_KEY}
                onClick={selectCustom}
              />
            </div>
          </div>
        )}

        <TooltipProvider delayDuration={200}>
          <div className="grid grid-cols-2 gap-5">
            <FormField label={t('settings.ssoForm.displayName')} hint={t('settings.ssoForm.displayNameHint')}>
              <Input
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              />
            </FormField>

            <FormField
              label={t('settings.ssoForm.issuerUrl')}
              hint={
                presetKey !== CUSTOM_PRESET_KEY
                  ? SSO_PRESETS.find((p) => p.key === presetKey)?.issuerHint ??
                    t('settings.ssoForm.issuerUrlHint', { issuer: form.issuer || 'https://issuer.example.com' })
                  : `${t('settings.ssoForm.issuerUrlHint', { issuer: form.issuer || 'https://issuer.example.com' })}\n\n${t('settings.ssoForm.issuerExamples')}`
              }
            >
              <Input
                value={form.issuer}
                onChange={(e) => setForm({ ...form, issuer: e.target.value })}
                placeholder="https://accounts.google.com"
              />
            </FormField>

            <FormField label={t('settings.ssoForm.clientId')} hint={t('settings.ssoForm.clientIdHint')}>
              <Input
                value={form.client_id}
                onChange={(e) => setForm({ ...form, client_id: e.target.value })}
              />
            </FormField>

            <FormField label={t('settings.ssoForm.clientSecret')} hint={t('settings.ssoForm.clientSecretHint')}>
              <Input
                type="password"
                value={form.client_secret}
                onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
                placeholder={editingId !== null ? t('settings.ssoForm.clientSecretConfigured') : ''}
              />
            </FormField>

            {editingId === null ? (
              <FormField
                label={t('settings.ssoForm.firstLoginPolicy')}
                hint={`${t('settings.ssoForm.firstLoginPolicyHint')}\n\n• ${t('settings.ssoForm.policyJitHint')}\n• ${t('settings.ssoForm.policyPendingHint')}\n• ${t('settings.ssoForm.policyRejectHint')}`}
              >
                <Select
                  value={form.first_login_policy}
                  onValueChange={(v) => setForm({ ...form, first_login_policy: v as FirstLoginPolicy })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="jit_create">{t('settings.ssoForm.policyJit')}</SelectItem>
                    <SelectItem value="pending_approval">{t('settings.ssoForm.policyPending')}</SelectItem>
                    <SelectItem value="reject_unknown">{t('settings.ssoForm.policyReject')}</SelectItem>
                  </SelectContent>
                </Select>
              </FormField>
            ) : null}

            <div className="flex items-center justify-between rounded-md border px-3">
              <div className="flex items-center gap-1.5">
                <Label>{t('settings.ssoForm.enabled')}</Label>
                <InfoHint hint={t('settings.ssoForm.enabledHint')} />
              </div>
              <Switch
                checked={form.enabled}
                onCheckedChange={(v) => setForm({ ...form, enabled: v })}
              />
            </div>
          </div>
        </TooltipProvider>

        <CallbackUrlField provider={existing} />

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('settings.ssoForm.cancel')}
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            {t('settings.ssoForm.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FormField({
  label,
  hint,
  className,
  children,
}: {
  label: string
  hint?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={`space-y-1.5 ${className ?? ''}`}>
      <div className="flex items-center gap-1.5">
        <Label>{label}</Label>
        {hint && <InfoHint hint={hint} />}
      </div>
      {children}
    </div>
  )
}

function InfoHint({ hint }: { hint: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="text-muted-foreground hover:text-foreground" tabIndex={-1}>
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs whitespace-pre-line text-left">
        {hint}
      </TooltipContent>
    </Tooltip>
  )
}

function PresetChip({
  preset,
  active,
  onClick,
}: {
  preset: SsoPreset
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? 'rounded-full border border-primary bg-primary px-3 py-1 text-xs font-medium text-primary-foreground'
          : 'rounded-full border border-input bg-background px-3 py-1 text-xs font-medium text-foreground hover:bg-accent'
      }
    >
      {preset.displayName}
    </button>
  )
}

function CallbackUrlField({ provider }: { provider: AuthProvider | null }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  if (!provider) {
    return (
      <div className="space-y-1 rounded-md border bg-muted/30 p-3">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          {t('settings.ssoForm.callbackUrl')}
        </Label>
        <p className="text-xs text-muted-foreground">{t('settings.ssoForm.callbackUrlNote')}</p>
      </div>
    )
  }

  const fullUrl = provider.callback_url

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(fullUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard may be blocked; ignore
    }
  }

  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-3">
      <div className="flex items-center justify-between">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          {t('settings.ssoForm.callbackUrl')}
        </Label>
        <Button variant="ghost" size="sm" onClick={copy} className="h-7 px-2 text-xs">
          {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
          {copied ? t('settings.ssoForm.copied') : t('settings.ssoForm.copy')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('settings.ssoForm.callbackUrlHint')}</p>
      <code className="block break-all rounded bg-background px-2 py-1.5 text-xs">{fullUrl}</code>
    </div>
  )
}
