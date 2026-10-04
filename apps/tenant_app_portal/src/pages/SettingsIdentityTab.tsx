import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import SettingsPageShell from '@/components/SettingsPageShell'
import SettingsSection from '@/components/SettingsSection'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNotification } from '@/hooks/useNotification'
import { AlertCircle, Loader2 } from 'lucide-react'
import {
  listAuthProviders,
  deleteAuthProvider,
  enableAuthProvider,
  disableAuthProvider,
  type AuthProvider,
  type FirstLoginPolicy,
} from '@/lib/ssoApi'
import {
  listLoginDomains,
  addLoginDomains,
  removeLoginDomain,
  getIdentitySettings,
  updateIdentitySettings,
  listPendingIdentities,
  approvePendingIdentity,
  rejectPendingIdentity,
  listIdentitySources,
  updateIdentitySourceBindPolicy,
  type IdentitySource,
  type LoginDomain,
  type PendingIdentity,
} from '@/lib/identityApi'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import { useConfirmation } from '@/hooks/useConfirmation'
import ProviderForm from '@/components/sso/ProviderForm'
import IdentitySourcesPanel from '@/components/identity/IdentitySourcesPanel'
import IdentityLoginRulesPanel from '@/components/identity/IdentityLoginRulesPanel'
import IdentityPendingPanel from '@/components/identity/IdentityPendingPanel'

const TAB_SOURCES = 'sources'
const TAB_LOGIN = 'login'
const TAB_REQUESTS = 'requests'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    settings: {
      identityTab: {
        tabSources: 'Sources',
        tabLoginRules: 'Login rules',
        tabRequests: 'Requests',
        sourcesDesc: 'Manage portal SSO providers and Slack workspace binding separately.',
        loginAccessDesc: 'Email domains routed to this tenant and optional password-login lockdown',
        pendingDesc: 'OIDC and Slack identities awaiting admin approval',
        addProvider: 'Add OIDC provider',
        enabled: 'Enabled',
        disabled: 'Disabled',
        enable: 'Enable',
        disable: 'Disable',
        loginDomains: 'Login domains',
        loginDomainsEmptyHint:
          'No domains added yet. Users signing in with an email (e.g. you@company.com) won’t be routed to this tenant until you add its domain here. SSO login will be denied as “domain_not_allowed”.',
        addDomain: 'Add domain',
        domainPlaceholder: 'company.com',
        forceSso: 'Force SSO',
        forceSsoDesc: 'Disable password login except for break-glass admins',
        breakGlassCount: 'Break-glass admins: {{count}}',
        approve: 'Approve',
        reject: 'Reject',
        noPending: 'No pending requests',
        saveSuccess: 'Saved',
        saveFailed: 'Save failed',
        deleteSuccess: 'Deleted',
        deleteFailed: 'Delete failed',
        approveSuccess: 'Approved',
        rejectSuccess: 'Rejected',
        forceSsoEnableFailed: 'Cannot enable force SSO without a break-glass admin',
        forceSsoNoBreakGlass:
          'Designate at least one break-glass admin in the Users tab before enabling Force SSO.',
        forceSsoEnabled: 'Force SSO enabled. Password login is disabled except for break-glass admins.',
        forceSsoDisabled: 'Force SSO disabled. Password login is available to all users.',
        domainClaimed: 'Domain already claimed by another tenant',
        confirmDeleteProvider: 'Delete identity provider "{{name}}"? Sign-in with this IdP will stop.',
        confirmRejectPending: 'Reject identity request for "{{name}}"?',
        confirmRemoveDomain: 'Remove login domain "{{name}}"? Emails on this domain will no longer route here.',
        goToAgents: 'Manage on Agents',
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
      identityTab: {
        tabSources: '来源',
        tabLoginRules: '登录规则',
        tabRequests: '待审批',
        sourcesDesc: '分别管理门户 SSO 提供商与 Slack 工作区绑定。',
        loginAccessDesc: '路由到此租户的邮箱域名，以及可选的密码登录限制',
        pendingDesc: '待管理员审批的 OIDC 与 Slack 身份',
        addProvider: '添加 OIDC 提供商',
        enabled: '已启用',
        disabled: '已禁用',
        enable: '启用',
        disable: '禁用',
        loginDomains: '登录域名',
        loginDomainsEmptyHint:
          '尚未添加域名。在添加域名之前，使用邮箱（例如 you@company.com）登录的用户不会被路由到此租户，SSO 登录将被拒绝（domain_not_allowed）。',
        addDomain: '添加域名',
        domainPlaceholder: 'company.com',
        forceSso: '强制 SSO',
        forceSsoDesc: '禁用密码登录（break-glass 管理员除外）',
        breakGlassCount: 'Break-glass 管理员：{{count}}',
        approve: '通过',
        reject: '拒绝',
        noPending: '无待审批请求',
        saveSuccess: '已保存',
        saveFailed: '保存失败',
        deleteSuccess: '已删除',
        deleteFailed: '删除失败',
        approveSuccess: '已通过',
        rejectSuccess: '已拒绝',
        forceSsoEnableFailed: '无 break-glass 管理员，无法启用强制 SSO',
        forceSsoNoBreakGlass: '请先在“用户”标签页中指定至少一名 break-glass 管理员，再启用强制 SSO。',
        forceSsoEnabled: '强制 SSO 已启用。除 break-glass 管理员外，密码登录已禁用。',
        forceSsoDisabled: '强制 SSO 已禁用。所有用户均可使用密码登录。',
        domainClaimed: '域名已被其他租户占用',
        confirmDeleteProvider: '删除身份提供商“{{name}}”？此后无法再用该 IdP 登录。',
        confirmRejectPending: '拒绝“{{name}}”的身份请求？',
        confirmRemoveDomain: '移除登录域名“{{name}}”？该域名邮箱将不再路由到此租户。',
        goToAgents: '在智能体中管理',
      },
    },
  },
  true,
  true
)

export default function SettingsIdentityTab() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab =
    tabParam === TAB_LOGIN || tabParam === TAB_REQUESTS ? tabParam : TAB_SOURCES

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [providers, setProviders] = useState<AuthProvider[]>([])
  const [domains, setDomains] = useState<LoginDomain[]>([])
  const [pending, setPending] = useState<PendingIdentity[]>([])
  const [identitySources, setIdentitySources] = useState<IdentitySource[]>([])
  const [forceSso, setForceSso] = useState(false)
  const [breakGlassCount, setBreakGlassCount] = useState(0)
  const [editing, setEditing] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [newDomain, setNewDomain] = useState('')
  const deleteProviderConfirm = useConfirmation<AuthProvider>()
  const rejectPendingConfirm = useConfirmation<PendingIdentity>()
  const removeDomainConfirm = useConfirmation<LoginDomain>()

  useEffect(() => {
    loadData()
  }, [])

  const setActiveTab = (tab: string) => {
    setSearchParams({ tab }, { replace: true })
  }

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [provs, doms, pend, settings, sources] = await Promise.all([
        listAuthProviders(),
        listLoginDomains(),
        listPendingIdentities(),
        getIdentitySettings(),
        listIdentitySources(),
      ])
      setProviders(provs)
      setDomains(doms)
      setPending(pend)
      setIdentitySources(sources)
      if (settings) {
        setForceSso(settings.force_sso)
        setBreakGlassCount(settings.break_glass_admin_count)
      }
    } catch (e: any) {
      setError(e?.message || 'Load failed')
    } finally {
      setLoading(false)
    }
  }

  const startAdd = () => {
    setEditingId(null)
    setEditing(true)
  }

  const startEdit = (providerId: number) => {
    setEditingId(providerId)
    setEditing(true)
  }

  const onSaved = async () => {
    setEditing(false)
    setEditingId(null)
    await loadData()
  }

  const removeProvider = async (provider: AuthProvider) => {
    deleteProviderConfirm.setLoading(true)
    try {
      await deleteAuthProvider(provider.id)
      showSuccess(t('settings.identityTab.deleteSuccess'))
      deleteProviderConfirm.close()
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.deleteFailed'))
      deleteProviderConfirm.setLoading(false)
    }
  }

  const toggleProvider = async (p: AuthProvider) => {
    try {
      if (p.enabled) {
        await disableAuthProvider(p.id)
      } else {
        await enableAuthProvider(p.id)
      }
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.saveFailed'))
    }
  }

  const addDomain = async () => {
    const d = newDomain.trim().toLowerCase()
    if (!d) return
    try {
      await addLoginDomains([d])
      setNewDomain('')
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.domainClaimed'))
    }
  }

  const removeDomain = async (domain: LoginDomain) => {
    removeDomainConfirm.setLoading(true)
    try {
      await removeLoginDomain(domain.id)
      removeDomainConfirm.close()
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.saveFailed'))
      removeDomainConfirm.setLoading(false)
    }
  }

  const toggleForceSso = async (value: boolean) => {
    try {
      const s = await updateIdentitySettings(value)
      setForceSso(s.force_sso)
      setBreakGlassCount(s.break_glass_admin_count)
      showSuccess(
        value ? t('settings.identityTab.forceSsoEnabled') : t('settings.identityTab.forceSsoDisabled')
      )
    } catch (e: any) {
      const code = e?.response?.data?.code
      if (code === 'SSO_FORCE_SSO_NO_BREAK_GLASS') {
        showError(t('settings.identityTab.forceSsoNoBreakGlass'))
      } else {
        showError(e?.response?.data?.detail || t('settings.identityTab.forceSsoEnableFailed'))
      }
    }
  }

  const approvePending = async (id: number) => {
    try {
      await approvePendingIdentity(id)
      showSuccess(t('settings.identityTab.approveSuccess'))
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.saveFailed'))
    }
  }

  const updateSourcePolicy = async (source: IdentitySource, bind_policy: FirstLoginPolicy) => {
    try {
      await updateIdentitySourceBindPolicy(source.id, bind_policy)
      showSuccess(t('settings.identityTab.saveSuccess'))
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.saveFailed'))
    }
  }

  const rejectPending = async (identity: PendingIdentity) => {
    rejectPendingConfirm.setLoading(true)
    try {
      await rejectPendingIdentity(identity.id)
      showSuccess(t('settings.identityTab.rejectSuccess'))
      rejectPendingConfirm.close()
      await loadData()
    } catch (e: any) {
      showError(e?.response?.data?.detail || t('settings.identityTab.saveFailed'))
      rejectPendingConfirm.setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }

  return (
    <SettingsPageShell>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value={TAB_SOURCES}>{t('settings.identityTab.tabSources')}</TabsTrigger>
          <TabsTrigger value={TAB_LOGIN}>{t('settings.identityTab.tabLoginRules')}</TabsTrigger>
          <TabsTrigger value={TAB_REQUESTS} className="gap-2">
            {t('settings.identityTab.tabRequests')}
            {pending.length > 0 ? (
              <Badge variant="secondary" className="h-5 min-w-5 px-1.5 text-xs">
                {pending.length}
              </Badge>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value={TAB_SOURCES} className="mt-4">
          <IdentitySourcesPanel
            sources={identitySources}
            providers={providers}
            onUpdatePolicy={updateSourcePolicy}
            onConfigureProvider={startEdit}
            onToggleProvider={toggleProvider}
            onDeleteProvider={(p) => deleteProviderConfirm.open(p)}
            onAddProvider={startAdd}
          />
        </TabsContent>

        <TabsContent value={TAB_LOGIN} className="mt-4">
          <SettingsSection
            title={t('settings.identityTab.tabLoginRules')}
            description={t('settings.identityTab.loginAccessDesc')}
          >
            <IdentityLoginRulesPanel
              domains={domains}
              newDomain={newDomain}
              onNewDomainChange={setNewDomain}
              onAddDomain={addDomain}
              onRemoveDomain={(d) => removeDomainConfirm.open(d)}
              forceSso={forceSso}
              breakGlassCount={breakGlassCount}
              onToggleForceSso={toggleForceSso}
              t={t}
            />
          </SettingsSection>
        </TabsContent>

        <TabsContent value={TAB_REQUESTS} className="mt-4">
          <SettingsSection
            title={t('settings.identityTab.tabRequests')}
            description={t('settings.identityTab.pendingDesc')}
          >
            <IdentityPendingPanel
              pending={pending}
              onApprove={approvePending}
              onReject={(p) => rejectPendingConfirm.open(p)}
              t={t}
            />
          </SettingsSection>
        </TabsContent>
      </Tabs>

      <ProviderForm
        open={editing}
        onOpenChange={(o) => {
          setEditing(o)
          if (!o) setEditingId(null)
        }}
        editingId={editingId}
        existing={editingId !== null ? (providers.find((p) => p.id === editingId) ?? null) : null}
        onSaved={onSaved}
      />

      <ConfirmationDialog
        open={deleteProviderConfirm.isOpen}
        item={deleteProviderConfirm.item}
        isLoading={deleteProviderConfirm.isLoading}
        title={t('common.delete')}
        description={(item) =>
          t('settings.identityTab.confirmDeleteProvider', { name: item.display_name })
        }
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={removeProvider}
        onCancel={deleteProviderConfirm.close}
      />
      <ConfirmationDialog
        open={rejectPendingConfirm.isOpen}
        item={rejectPendingConfirm.item}
        isLoading={rejectPendingConfirm.isLoading}
        title={t('settings.identityTab.reject')}
        description={(item) =>
          t('settings.identityTab.confirmRejectPending', { name: item.email || item.external_subject })
        }
        confirmText={t('settings.identityTab.reject')}
        isDangerous
        onConfirm={rejectPending}
        onCancel={rejectPendingConfirm.close}
      />
      <ConfirmationDialog
        open={removeDomainConfirm.isOpen}
        item={removeDomainConfirm.item}
        isLoading={removeDomainConfirm.isLoading}
        title={t('common.delete')}
        description={(item) =>
          t('settings.identityTab.confirmRemoveDomain', { name: item.domain })
        }
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={removeDomain}
        onCancel={removeDomainConfirm.close}
      />
    </SettingsPageShell>
  )
}
