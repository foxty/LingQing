import { useEffect, useMemo, useState, type MouseEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import {
  Bot,
  ChevronRight,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Settings,
  Share2,
  ThumbsUp,
  Trash2,
} from 'lucide-react'
import { Can } from '@/components/Can'
import AgentSettingsForm from '@/components/agents/AgentSettingsForm'
import { emptyAgentConfig } from '@/components/agents/AgentSettingsForm'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import { ConfirmationDialog } from '@/components/ConfirmationDialog'
import EmptyState from '@/components/EmptyState'
import { useConfirmation } from '@/hooks/useConfirmation'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/hooks/useAuth'
import {
  useAgentSkillCatalog,
  useAgents,
  useCreateAgent,
  useDeleteAgent,
} from '@/hooks/useAgents'
import { useDocumentCollections } from '@/hooks/useDocumentCollections'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import {
  SYSTEM_AGENT_ONE_ID,
  agentApiErrorMessage,
  type AgentCapabilityConfig,
  type CatalogAgent,
} from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDataSources } from '@/lib/dataSourceApi'
import { listRegistryProfiles } from '@/lib/llmConfigApi'
import { listSlackIntegrations, type SlackIntegration } from '@/lib/slackApi'
import { actionRules, routeRules } from '@/lib/permissionRules'
import { useQuery } from '@tanstack/react-query'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agents: {
      pageTitle: 'Agents',
      description: 'Purpose-specific assistants with assigned tools, skills, and knowledge.',
      create: 'New agent',
      viewFeedback: 'Feedback',
      openChat: 'Open in conversation',
      share: 'Share',
      settings: 'Settings',
      delete: 'Delete',
      system: 'Built-in',
      empty: 'No custom agents yet',
      emptyHint: 'Create an agent for a specific job, then open it in conversation.',
      onlyBuiltIn: 'Only the built-in assistant is available. Create one for a specific job.',
      deleteTitle: 'Delete agent',
      deleteDesc: 'Delete "{{name}}"? Existing conversations stay, but this agent can no longer be used.',
      slackStatusConnected: 'Slack connected',
      slackStatusDisabled: 'Slack disabled',
      rowActions: 'Agent actions',
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
      pageTitle: '智能体',
      description: '为特定任务分配工具、技能与知识库的助手。',
      create: '新建智能体',
      viewFeedback: '反馈分析',
      openChat: '在对话中打开',
      share: '共享',
      settings: '设置',
      delete: '删除',
      system: '内置',
      empty: '暂无自定义智能体',
      emptyHint: '先创建一个面向具体任务的智能体，再到对话中使用。',
      onlyBuiltIn: '目前只有内置助手。创建一个面向具体任务的智能体。',
      deleteTitle: '删除智能体',
      deleteDesc: '确定删除“{{name}}”？历史对话会保留，但该智能体不可再用。',
      slackStatusConnected: 'Slack 已连接',
      slackStatusDisabled: 'Slack 已禁用',
      rowActions: '智能体操作',
    },
  },
  true,
  true
)

export default function AgentsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { hasAny } = useAuth()
  const { data: agents = [], isLoading } = useAgents()
  const { data: skills = [] } = useAgentSkillCatalog()
  const { data: collections = [] } = useDocumentCollections()
  const { data: dataSources = [] } = useQuery({
    queryKey: ['agent-data-sources'],
    queryFn: async () => (await listDataSources(1, 100)).items ?? [],
  })
  const { data: connectors = [] } = useQuery({
    queryKey: ['agent-api-connectors'],
    queryFn: listApiConnectors,
  })
  const { data: slackIntegrations = [] } = useQuery({
    queryKey: ['slack-integrations'],
    queryFn: listSlackIntegrations,
  })
  const slackByAgentId = useMemo(
    () => new Map(slackIntegrations.map((integration) => [integration.agent_id, integration])),
    [slackIntegrations]
  )
  const createMutation = useCreateAgent()
  const deleteMutation = useDeleteAgent()
  const canCreate = hasAny(actionRules.canCreateAgent())
  const canViewFeedback = hasAny(routeRules.canAccessAgentFeedback())

  const [creating, setCreating] = useState(false)
  const [sharing, setSharing] = useState<CatalogAgent | null>(null)
  const deleteConfirm = useConfirmation<CatalogAgent>()
  const [formName, setFormName] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formConfig, setFormConfig] = useState<AgentCapabilityConfig>(emptyAgentConfig())
  const [formError, setFormError] = useState<string | null>(null)
  const { data: llmProfiles = [] } = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
    enabled: creating,
  })

  const systemAgent = agents.find((agent) => agent.id === SYSTEM_AGENT_ONE_ID)
  const customAgents = agents.filter((agent) => !agent.is_system)

  const openCreate = () => {
    setFormName('')
    setFormPrompt(systemAgent?.system_prompt || '')
    setFormConfig(emptyAgentConfig())
    setFormError(null)
    setCreating(true)
  }

  useEffect(() => {
    if (searchParams.get('new') !== '1' || !canCreate) {
      return
    }
    openCreate()
    const next = new URLSearchParams(searchParams)
    next.delete('new')
    setSearchParams(next, { replace: true })
  }, [canCreate, searchParams, setSearchParams])

  const saveCreate = async () => {
    const payload = {
      name: formName.trim(),
      system_prompt: formPrompt,
      config: formConfig,
    }
    try {
      setFormError(null)
      const created = await createMutation.mutateAsync(payload)
      setCreating(false)
      navigate(`/agents/${created.id}?tab=settings`)
    } catch (error) {
      setFormError(agentApiErrorMessage(error, t('agents.saveFailed')))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t('agents.pageTitle')}</h1>
          <p className="text-sm text-muted-foreground">{t('agents.description')}</p>
        </div>
        <div className="flex items-center gap-2">
          {canViewFeedback ? (
            <Button variant="outline" asChild>
              <Link to="/agents/feedback">
                <ThumbsUp className="mr-2 h-4 w-4" />
                {t('agents.viewFeedback')}
              </Link>
            </Button>
          ) : null}
          <Can any={actionRules.canCreateAgent()}>
            <Button onClick={openCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {t('agents.create')}
            </Button>
          </Can>
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-muted-foreground">{t('common.loading')}</div>
      ) : agents.length === 0 ? (
        <EmptyState
          title={t('agents.empty')}
          description={t('agents.emptyHint')}
          action={
            canCreate ? (
              <Button onClick={openCreate}>
                <Plus className="mr-2 h-4 w-4" />
                {t('agents.create')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {customAgents.length === 0 && canCreate ? (
            <p className="text-sm text-muted-foreground sm:col-span-2">{t('agents.onlyBuiltIn')}</p>
          ) : null}
          {agents.map((agent) => (
            <AgentCatalogCard
              key={agent.id}
              agent={agent}
              slackIntegration={slackByAgentId.get(agent.id)}
              onOpen={() => navigate(`/agents/${agent.id}`)}
              onChat={(event) => {
                event.stopPropagation()
                navigate(`/workbench?agent=${agent.id}`)
              }}
              onSettings={(event) => {
                event.stopPropagation()
                navigate(`/agents/${agent.id}?tab=settings`)
              }}
              onShare={(event) => {
                event.stopPropagation()
                setSharing(agent)
              }}
              onDelete={(event) => {
                event.stopPropagation()
                deleteConfirm.open(agent)
              }}
            />
          ))}
        </div>
      )}

      <Dialog open={creating} onOpenChange={(open) => !open && setCreating(false)}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('agents.create')}</DialogTitle>
          </DialogHeader>
          <AgentSettingsForm
            formName={formName}
            formPrompt={formPrompt}
            formConfig={formConfig}
            formError={formError}
            skills={skills}
            collections={collections}
            dataSources={dataSources}
            connectors={connectors}
            llmProfiles={llmProfiles}
            saving={createMutation.isPending}
            showActions={false}
            onNameChange={setFormName}
            onPromptChange={setFormPrompt}
            onConfigChange={setFormConfig}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(false)}>
              {t('agents.cancel')}
            </Button>
            <Button
              onClick={() => void saveCreate()}
              disabled={!formName.trim() || createMutation.isPending}
            >
              {t('agents.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {sharing ? (
        <ResourceAclShareDialog
          open={Boolean(sharing)}
          onOpenChange={(open) => !open && setSharing(null)}
          resourceType={ACL_SHARE_RESOURCE_TYPES.AGENT}
          resourceId={sharing.id}
          resourceTitle={sharing.name}
        />
      ) : null}

      <ConfirmationDialog
        open={deleteConfirm.isOpen}
        item={deleteConfirm.item}
        isLoading={deleteConfirm.isLoading}
        title={t('agents.deleteTitle')}
        description={(agent) => t('agents.deleteDesc', { name: agent.name })}
        confirmText={t('common.delete')}
        isDangerous
        onConfirm={async (agent) => {
          deleteConfirm.setLoading(true)
          try {
            await deleteMutation.mutateAsync(agent.id)
            deleteConfirm.close()
          } catch {
            deleteConfirm.setLoading(false)
          }
        }}
        onCancel={deleteConfirm.close}
      />
    </div>
  )
}

function AgentCatalogCard({
  agent,
  slackIntegration,
  onOpen,
  onChat,
  onSettings,
  onShare,
  onDelete,
}: {
  agent: CatalogAgent
  slackIntegration: SlackIntegration | undefined
  onOpen: () => void
  onChat: (event: MouseEvent) => void
  onSettings: (event: MouseEvent) => void
  onShare: (event: MouseEvent) => void
  onDelete: (event: MouseEvent) => void
}) {
  const { t } = useTranslation()
  const showOverflow =
    (!agent.is_system && agent.can_manage) || (!agent.is_system && agent.can_write)

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen()
        }
      }}
      className="group flex cursor-pointer flex-col rounded-md border p-4 transition-colors hover:bg-muted/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 shrink-0" />
            <h2 className="truncate text-base font-medium">{agent.name}</h2>
            {agent.is_system ? (
              <span className="text-xs text-muted-foreground">{t('agents.system')}</span>
            ) : null}
          </div>
          <p className="line-clamp-2 text-sm text-muted-foreground">
            {agent.description || agent.system_prompt}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {slackIntegration ? (
              <Badge variant={slackIntegration.enabled ? 'default' : 'secondary'}>
                {slackIntegration.enabled
                  ? t('agents.slackStatusConnected')
                  : t('agents.slackStatusDisabled')}
              </Badge>
            ) : null}
          </div>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>

      <div className="mt-4 flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
        <Button size="sm" onClick={onChat}>
          <MessageSquare className="mr-2 h-4 w-4" />
          {t('agents.openChat')}
        </Button>
        {showOverflow ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="outline" aria-label={t('agents.rowActions')}>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onSettings}>
                <Settings className="mr-2 h-4 w-4" />
                {t('agents.settings')}
              </DropdownMenuItem>
              {!agent.is_system && agent.can_manage ? (
                <DropdownMenuItem onClick={onShare}>
                  <Share2 className="mr-2 h-4 w-4" />
                  {t('agents.share')}
                </DropdownMenuItem>
              ) : null}
              {!agent.is_system && agent.can_write ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={onDelete}>
                    <Trash2 className="mr-2 h-4 w-4" />
                    {t('agents.delete')}
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </div>
  )
}
