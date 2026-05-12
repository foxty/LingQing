import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import BindPolicySelect from '@/components/identity/BindPolicySelect'
import { ExternalLink, KeyRound, MessageSquare, Settings, Power, Trash2 } from 'lucide-react'
import type { AuthProvider, FirstLoginPolicy } from '@/lib/ssoApi'
import type { IdentitySource } from '@/lib/identityApi'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    identity: {
      sourcesPanel: {
        intro:
          'Two different ways people connect to your tenant. OIDC is for the login page; Slack is for agent conversations only.',
        oidcTitle: 'Portal sign-in (OIDC)',
        oidcPurpose:
          'Identity providers shown as SSO buttons on the LingQing login page (Google, Okta, Entra, etc.).',
        oidcEmpty: 'No OIDC provider configured.',
        slackTitle: 'Slack workspace',
        slackPurpose:
          'Not a login provider. Controls how Slack users are mapped to tenant accounts when they message agent bots.',
        slackNotLoginBadge: 'Not for portal sign-in',
        slackEmpty: 'No Slack workspace linked yet. Connect a bot on an agent to create one.',
        slackSetupCta: 'Set up Slack bots on Agents',
        configure: 'Configure credentials',
        enableProvider: 'Enable provider',
        disableProvider: 'Disable provider',
        deleteProvider: 'Delete provider',
        manageSlackBots: 'Manage Slack bots on Agents',
        colProvider: 'Provider',
        colIssuer: 'Issuer',
        colStatus: 'Status',
        colWorkspace: 'Workspace',
        colDetails: 'Details',
        colBindPolicy: 'Unknown user policy',
        colActions: 'Actions',
        slackTeam: 'Team {{teamId}}',
        slackBots: '{{count}} agent bot(s)',
        slackPending: 'Awaiting bot connection',
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
    identity: {
      sourcesPanel: {
        intro: '两种独立的身份接入方式：OIDC 用于登录页；Slack 仅用于智能体对话，不是登录入口。',
        oidcTitle: '门户登录（OIDC）',
        oidcPurpose: '显示在 LingQing 登录页上的 SSO 按钮（Google、Okta、Entra 等）。',
        oidcEmpty: '尚未配置 OIDC 提供商。',
        slackTitle: 'Slack 工作区',
        slackPurpose: '不是登录提供商。控制 Slack 用户通过智能体机器人发消息时如何映射到租户账户。',
        slackNotLoginBadge: '非门户登录',
        slackEmpty: '尚未关联 Slack 工作区。请在智能体上连接机器人后自动创建。',
        slackSetupCta: '前往智能体配置 Slack 机器人',
        configure: '配置凭证',
        enableProvider: '启用提供商',
        disableProvider: '禁用提供商',
        deleteProvider: '删除提供商',
        manageSlackBots: '在智能体中管理 Slack 机器人',
        colProvider: '提供商',
        colIssuer: 'Issuer',
        colStatus: '状态',
        colWorkspace: '工作区',
        colDetails: '详情',
        colBindPolicy: '未知用户策略',
        colActions: '操作',
        slackTeam: '团队 {{teamId}}',
        slackBots: '{{count}} 个智能体机器人',
        slackPending: '等待连接机器人',
      },
    },
  },
  true,
  true
)

type Props = {
  sources: IdentitySource[]
  providers: AuthProvider[]
  onUpdatePolicy: (source: IdentitySource, bind_policy: FirstLoginPolicy) => void
  onConfigureProvider: (providerId: number) => void
  onToggleProvider: (provider: AuthProvider) => void
  onDeleteProvider: (provider: AuthProvider) => void
  onAddProvider: () => void
}

function providerForSource(source: IdentitySource, providers: AuthProvider[]) {
  if (!source.linked_auth_provider_id) return null
  return providers.find((p) => p.id === source.linked_auth_provider_id) ?? null
}

function slackTeamId(source: IdentitySource): string | null {
  if (!source.source_key.startsWith('slack:')) return null
  const scope = source.source_key.slice('slack:'.length)
  return scope.startsWith('tenant:') ? null : scope
}

function slackDetails(source: IdentitySource, t: (key: string, opts?: Record<string, unknown>) => string) {
  const teamId = slackTeamId(source)
  const parts: string[] = []
  if (teamId) {
    parts.push(t('identity.sourcesPanel.slackTeam', { teamId }))
  } else if (source.source_key.includes(':tenant:')) {
    parts.push(t('identity.sourcesPanel.slackPending'))
  }
  if (source.linked_slack_endpoint_count > 0) {
    parts.push(t('identity.sourcesPanel.slackBots', { count: source.linked_slack_endpoint_count }))
  }
  return parts.join(' · ') || '—'
}

function IconActionButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}

function CategoryBlock({
  icon,
  title,
  purpose,
  badge,
  headerAction,
  children,
}: {
  icon: React.ReactNode
  title: string
  purpose: string
  badge?: React.ReactNode
  headerAction?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <div className="flex items-start justify-between gap-4 border-b border-border/60 p-4">
        <div className="flex min-w-0 flex-1 gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border bg-muted/40">
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{title}</h3>
              {badge}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{purpose}</p>
          </div>
        </div>
        {headerAction ? <div className="shrink-0">{headerAction}</div> : null}
      </div>
      <div>{children}</div>
    </div>
  )
}

export default function IdentitySourcesPanel({
  sources,
  providers,
  onUpdatePolicy,
  onConfigureProvider,
  onToggleProvider,
  onDeleteProvider,
  onAddProvider,
}: Props) {
  const { t } = useTranslation()

  const loginSources = sources.filter((s) => s.source_kind === 'login_provider')
  const slackSources = sources.filter((s) => s.source_kind === 'channel_workspace')

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t('identity.sourcesPanel.intro')}</p>

      <CategoryBlock
        icon={<KeyRound className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} />}
        title={t('identity.sourcesPanel.oidcTitle')}
        purpose={t('identity.sourcesPanel.oidcPurpose')}
        headerAction={
          <Button size="sm" onClick={onAddProvider}>
            {t('settings.identityTab.addProvider')}
          </Button>
        }
      >
        {loginSources.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">{t('identity.sourcesPanel.oidcEmpty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10">{t('identity.sourcesPanel.colProvider')}</TableHead>
                  <TableHead className="h-10">{t('identity.sourcesPanel.colIssuer')}</TableHead>
                  <TableHead className="h-10 w-[100px]">{t('identity.sourcesPanel.colStatus')}</TableHead>
                  <TableHead className="h-10 min-w-[200px]">{t('identity.sourcesPanel.colBindPolicy')}</TableHead>
                  <TableHead className="h-10 text-right">{t('identity.sourcesPanel.colActions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loginSources.map((source) => {
                  const provider = providerForSource(source, providers)
                  return (
                    <TableRow key={source.id}>
                      <TableCell className="py-3 font-medium">{source.display_name}</TableCell>
                      <TableCell className="py-3 max-w-[240px]">
                        <code className="block truncate text-xs text-muted-foreground">
                          {provider?.config.issuer ?? source.source_key}
                        </code>
                      </TableCell>
                      <TableCell className="py-3">
                        {provider ? (
                          <Badge
                            variant={provider.enabled ? 'secondary' : 'outline'}
                            className="text-xs font-normal"
                          >
                            {provider.enabled
                              ? t('settings.identityTab.enabled')
                              : t('settings.identityTab.disabled')}
                          </Badge>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="py-3">
                        <BindPolicySelect
                          value={source.bind_policy}
                          onChange={(bind_policy) => onUpdatePolicy(source, bind_policy)}
                          className="w-full min-w-[180px]"
                        />
                      </TableCell>
                      <TableCell className="py-3 text-right">
                        {provider ? (
                          <div className="flex justify-end gap-0.5">
                            <IconActionButton
                              label={t('identity.sourcesPanel.configure')}
                              onClick={() => onConfigureProvider(provider.id)}
                            >
                              <Settings className="h-4 w-4" />
                            </IconActionButton>
                            <IconActionButton
                              label={
                                provider.enabled
                                  ? t('identity.sourcesPanel.disableProvider')
                                  : t('identity.sourcesPanel.enableProvider')
                              }
                              onClick={() => onToggleProvider(provider)}
                            >
                              <Power className="h-4 w-4" />
                            </IconActionButton>
                            <IconActionButton
                              label={t('identity.sourcesPanel.deleteProvider')}
                              onClick={() => onDeleteProvider(provider)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </IconActionButton>
                          </div>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CategoryBlock>

      <CategoryBlock
        icon={<MessageSquare className="h-5 w-5 text-muted-foreground" strokeWidth={1.75} />}
        title={t('identity.sourcesPanel.slackTitle')}
        purpose={t('identity.sourcesPanel.slackPurpose')}
        badge={
          <Badge variant="outline" className="text-xs font-normal">
            {t('identity.sourcesPanel.slackNotLoginBadge')}
          </Badge>
        }
        headerAction={
          <Button variant="outline" size="sm" asChild>
            <Link to="/agents">{t('identity.sourcesPanel.slackSetupCta')}</Link>
          </Button>
        }
      >
        {slackSources.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">{t('identity.sourcesPanel.slackEmpty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-10">{t('identity.sourcesPanel.colWorkspace')}</TableHead>
                  <TableHead className="h-10">{t('identity.sourcesPanel.colDetails')}</TableHead>
                  <TableHead className="h-10 min-w-[200px]">{t('identity.sourcesPanel.colBindPolicy')}</TableHead>
                  <TableHead className="h-10 w-[88px] text-right">{t('identity.sourcesPanel.colActions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {slackSources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell className="py-3 font-medium">{source.display_name}</TableCell>
                    <TableCell className="py-3 text-sm text-muted-foreground">
                      {slackDetails(source, t)}
                    </TableCell>
                    <TableCell className="py-3">
                      <BindPolicySelect
                        value={source.bind_policy}
                        onChange={(bind_policy) => onUpdatePolicy(source, bind_policy)}
                        className="w-full min-w-[180px]"
                      />
                    </TableCell>
                    <TableCell className="py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                        asChild
                      >
                        <Link
                          to="/agents"
                          aria-label={t('identity.sourcesPanel.manageSlackBots')}
                          title={t('identity.sourcesPanel.manageSlackBots')}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CategoryBlock>
    </div>
  )
}
