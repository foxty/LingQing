import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Bot, MessageSquare, Plus, Share2, Slack, ThumbsUp, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Can } from '@/components/Can'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import EmptyState from '@/components/EmptyState'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/hooks/useAuth'
import {
  useAgentSkillCatalog,
  useAgents,
  useCreateAgent,
  useDeleteAgent,
  useUpdateAgent,
} from '@/hooks/useAgents'
import { useDocumentCollections } from '@/hooks/useDocumentCollections'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import {
  PLATFORM_CAPABILITY_REPORTS,
  PLATFORM_CAPABILITY_SCHEDULING,
  SYSTEM_AGENT_ONE_ID,
  agentApiErrorMessage,
  type AgentCapabilityConfig,
  type AgentSkillCatalogItem,
  type CatalogAgent,
  type PlatformCapability,
} from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDataSources } from '@/lib/dataSourceApi'
import { listRegistryProfiles, type LLMModelProfile } from '@/lib/llmConfigApi'
import { listSlackIntegrations, type SlackIntegration } from '@/lib/slackApi'
import { actionRules, PERMISSIONS, routeRules } from '@/lib/permissionRules'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import AgentSlackIntegrationDialog from '@/components/agents/AgentSlackIntegrationDialog'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

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
      edit: 'Edit',
      delete: 'Delete',
      system: 'Built-in',
      empty: 'No custom agents yet',
      emptyHint: 'Create an agent for a specific job, then open it in conversation.',
      onlyBuiltIn: 'Only the built-in assistant is available. Create one for a specific job.',
      name: 'Name',
      prompt: 'System prompt',
      tools: 'Tools',
      toolsHint: 'Tools are derived from skills, attached resources, and enabled platform capabilities.',
      toolsEmpty: 'No tools yet. Assign a skill, resource, or platform capability.',
      platformCapabilities: 'Platform capabilities',
      platformScheduling: 'Scheduling',
      platformSchedulingHint: 'Create and manage scheduled tasks for this agent.',
      platformReports: 'Reports',
      platformReportsHint: 'Create and update file-backed reports.',
      skills: 'Skills',
      knowledge: 'Knowledge bases',
      dataSources: 'Data sources',
      apis: 'API connectors',
      save: 'Save',
      saveFailed: 'Failed to save agent',
      cancel: 'Cancel',
      deleteTitle: 'Delete agent',
      deleteFailed: 'Failed to delete agent',
      deleteDesc: 'Delete "{{name}}"? Existing conversations stay, but this agent can no longer be used.',
      slack: 'Slack',
      slackStatusConnected: 'Slack connected',
      slackStatusDisabled: 'Slack disabled',
      modelProfile: 'Model profile',
      modelProfileHint: 'Override the tenant default LLM for this agent.',
      tenantDefaultModel: 'Tenant default',
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
      edit: '编辑',
      delete: '删除',
      system: '内置',
      empty: '暂无自定义智能体',
      emptyHint: '先创建一个面向具体任务的智能体，再到对话中使用。',
      onlyBuiltIn: '目前只有内置助手。创建一个面向具体任务的智能体。',
      name: '名称',
      prompt: '系统提示词',
      tools: '工具',
      toolsHint: '工具由技能、已绑定资源以及启用的平台能力自动推导。',
      toolsEmpty: '暂无工具。请分配技能、资源或平台能力。',
      platformCapabilities: '平台能力',
      platformScheduling: '定时任务',
      platformSchedulingHint: '为此智能体创建和管理定时任务。',
      platformReports: '报告',
      platformReportsHint: '创建和更新基于文件的报告。',
      skills: '技能',
      knowledge: '知识库',
      dataSources: '数据源',
      apis: 'API 连接器',
      save: '保存',
      saveFailed: '保存智能体失败',
      cancel: '取消',
      deleteTitle: '删除智能体',
      deleteFailed: '删除智能体失败',
      deleteDesc: '确定删除“{{name}}”？历史对话会保留，但该智能体不可再用。',
      slack: 'Slack',
      slackStatusConnected: 'Slack 已连接',
      slackStatusDisabled: 'Slack 已禁用',
      modelProfile: '模型配置',
      modelProfileHint: '覆盖租户默认 LLM，留空则使用租户默认。',
      tenantDefaultModel: '租户默认',
    },
  },
  true,
  true
)

const emptyConfig = (): AgentCapabilityConfig => ({
  default_tools: [],
  skills: [],
  knowledge_base_ids: [],
  data_source_ids: [],
  api_connector_ids: [],
  platform_capabilities: [],
  model_profile_id: null,
})

export default function AgentsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { hasAny } = useAuth()
  const queryClient = useQueryClient()
  const canManageTenantSlack = hasAny([PERMISSIONS.AUTH_PROVIDERS_MANAGE])
  const canViewAgents = hasAny([PERMISSIONS.AGENTS_READ])
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
    enabled: canViewAgents,
  })
  const slackByAgentId = useMemo(
    () => new Map(slackIntegrations.map((integration) => [integration.agent_id, integration])),
    [slackIntegrations]
  )
  const createMutation = useCreateAgent()
  const updateMutation = useUpdateAgent()
  const deleteMutation = useDeleteAgent()
  const canCreate = hasAny(actionRules.canCreateAgent())
  const canViewFeedback = hasAny(routeRules.canAccessAgentFeedback())

  const [editing, setEditing] = useState<CatalogAgent | 'new' | null>(null)
  const [sharing, setSharing] = useState<CatalogAgent | null>(null)
  const [slackAgent, setSlackAgent] = useState<CatalogAgent | null>(null)
  const [formName, setFormName] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formConfig, setFormConfig] = useState<AgentCapabilityConfig>(emptyConfig())
  const [formError, setFormError] = useState<string | null>(null)
  const { data: llmProfiles = [] } = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
    enabled: editing !== null,
  })

  const systemAgent = agents.find((agent) => agent.id === SYSTEM_AGENT_ONE_ID)
  const customAgents = agents.filter((agent) => !agent.is_system)

  const canManageSlack = (agent: CatalogAgent) =>
    agent.is_system ? canManageTenantSlack : agent.can_manage

  const openCreate = () => {
    setFormName('')
    setFormPrompt(systemAgent?.system_prompt || '')
    setFormConfig(emptyConfig())
    setFormError(null)
    setEditing('new')
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

  const openEdit = (agent: CatalogAgent) => {
    setFormName(agent.name)
    setFormPrompt(agent.system_prompt)
    setFormConfig({
      ...emptyConfig(),
      ...agent.config,
      platform_capabilities: agent.config.platform_capabilities ?? [],
    })
    setFormError(null)
    setEditing(agent)
  }

  const toggleListValue = <T,>(list: T[], value: T) =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value]

  const save = async () => {
    const payload = {
      name: formName.trim(),
      system_prompt: formPrompt,
      config: formConfig,
    }
    try {
      setFormError(null)
      if (editing === 'new') {
        await createMutation.mutateAsync(payload)
      } else if (editing && !editing.is_system) {
        await updateMutation.mutateAsync({ agentId: editing.id, payload })
      }
      setEditing(null)
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
        <div className="grid gap-3">
          {customAgents.length === 0 && canCreate ? (
            <p className="text-sm text-muted-foreground">{t('agents.onlyBuiltIn')}</p>
          ) : null}
          {agents.map((agent) => (
            <div key={agent.id} className="rounded-md border p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Bot className="h-4 w-4" />
                    <h2 className="text-base font-medium">{agent.name}</h2>
                    {agent.is_system ? (
                      <span className="text-xs text-muted-foreground">{t('agents.system')}</span>
                    ) : null}
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-2">{agent.description || agent.system_prompt}</p>
                  <AgentSlackStatusBadge integration={slackByAgentId.get(agent.id)} />
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-2">
                  <Button
                    size="sm"
                    onClick={() => navigate(`/workbench?agent=${agent.id}`)}
                  >
                    <MessageSquare className="mr-2 h-4 w-4" />
                    {t('agents.openChat')}
                  </Button>
                  {canManageSlack(agent) ? (
                    <Button size="sm" variant="outline" onClick={() => setSlackAgent(agent)}>
                      <Slack className="mr-2 h-4 w-4" />
                      {t('agents.slack')}
                    </Button>
                  ) : null}
                  {!agent.is_system && agent.can_manage ? (
                    <Button size="sm" variant="outline" onClick={() => setSharing(agent)}>
                      <Share2 className="mr-2 h-4 w-4" />
                      {t('agents.share')}
                    </Button>
                  ) : null}
                  {!agent.is_system && agent.can_write ? (
                    <>
                      <Button size="sm" variant="outline" onClick={() => openEdit(agent)}>
                        {t('agents.edit')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          if (window.confirm(t('agents.deleteDesc', { name: agent.name }))) {
                            deleteMutation.mutate(agent.id)
                          }
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editing === 'new' ? t('agents.create') : t('agents.edit')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t('agents.name')}</Label>
              <Input value={formName} onChange={(event) => setFormName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>{t('agents.prompt')}</Label>
              <Textarea value={formPrompt} onChange={(event) => setFormPrompt(event.target.value)} rows={6} />
            </div>
            <CheckboxGroup
              label={t('agents.skills')}
              items={skills.map((skill) => ({ id: skill.name, label: `${skill.name} (${skill.scope})` }))}
              selected={formConfig.skills}
              onToggle={(id) =>
                setFormConfig((current) => ({
                  ...current,
                  skills: toggleListValue(current.skills, id),
                }))
              }
            />
            <PlatformCapabilitiesGroup
              label={t('agents.platformCapabilities')}
              selected={formConfig.platform_capabilities}
              onToggle={(capability) =>
                setFormConfig((current) => ({
                  ...current,
                  platform_capabilities: toggleListValue(current.platform_capabilities, capability),
                }))
              }
            />
            <CheckboxGroup
              label={t('agents.knowledge')}
              items={collections.map((collection) => ({ id: String(collection.id), label: collection.name }))}
              selected={formConfig.knowledge_base_ids.map(String)}
              onToggle={(id) =>
                setFormConfig((current) => ({
                  ...current,
                  knowledge_base_ids: toggleListValue(current.knowledge_base_ids, Number(id)),
                }))
              }
            />
            <CheckboxGroup
              label={t('agents.dataSources')}
              items={dataSources.map((source) => ({ id: String(source.id), label: source.name }))}
              selected={formConfig.data_source_ids.map(String)}
              onToggle={(id) =>
                setFormConfig((current) => ({
                  ...current,
                  data_source_ids: toggleListValue(current.data_source_ids, Number(id)),
                }))
              }
            />
            <CheckboxGroup
              label={t('agents.apis')}
              items={connectors.map((connector) => ({ id: String(connector.id), label: connector.name }))}
              selected={formConfig.api_connector_ids.map(String)}
              onToggle={(id) =>
                setFormConfig((current) => ({
                  ...current,
                  api_connector_ids: toggleListValue(current.api_connector_ids, Number(id)),
                }))
              }
            />
            <div className="space-y-2">
              <Label>{t('agents.modelProfile')}</Label>
              <p className="text-xs text-muted-foreground">{t('agents.modelProfileHint')}</p>
              <Select
                value={
                  formConfig.model_profile_id === null || formConfig.model_profile_id === undefined
                    ? 'tenant-default'
                    : String(formConfig.model_profile_id)
                }
                onValueChange={(value) =>
                  setFormConfig((current) => ({
                    ...current,
                    model_profile_id: value === 'tenant-default' ? null : Number(value),
                  }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tenant-default">{t('agents.tenantDefaultModel')}</SelectItem>
                  {llmProfiles.map((profile: LLMModelProfile) => (
                    <SelectItem key={profile.id} value={String(profile.id)}>
                      {profile.name} ({profile.model_id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DerivedToolsPreview config={formConfig} skills={skills} />
            {formError ? (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              {t('agents.cancel')}
            </Button>
            <Button onClick={save} disabled={!formName.trim() || createMutation.isPending || updateMutation.isPending}>
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

      <AgentSlackIntegrationDialog
        agent={slackAgent}
        canManage={slackAgent ? canManageSlack(slackAgent) : false}
        open={slackAgent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSlackAgent(null)
            queryClient.invalidateQueries({ queryKey: ['slack-integrations'] })
          }
        }}
        onChanged={() => queryClient.invalidateQueries({ queryKey: ['slack-integrations'] })}
      />
    </div>
  )
}

function AgentSlackStatusBadge({ integration }: { integration: SlackIntegration | undefined }) {
  const { t } = useTranslation()
  if (!integration) {
    return null
  }
  return (
    <Badge variant={integration.enabled ? 'default' : 'secondary'} className="mt-2">
      {integration.enabled ? t('agents.slackStatusConnected') : t('agents.slackStatusDisabled')}
    </Badge>
  )
}

const CORE_SKILL_TOOLS = ['load_skill', 'unload_skill', 'read_skill_file']
const KNOWLEDGE_TOOLS = ['search_documents', 'retrieve_resource_context']
const DATA_SOURCE_TOOLS = ['list_data_sources', 'search_data_assets', 'retrieve_resource_context']
const API_CONNECTOR_TOOLS = ['search_apis', 'retrieve_resource_context', 'api_connector']
const SCHEDULER_TOOLS = [
  'list_scheduled_tasks',
  'get_scheduled_task',
  'schedule_task',
  'update_scheduled_task',
  'cancel_scheduled_task',
]
const REPORT_TOOLS = ['create_report', 'get_report', 'update_report']

const PLATFORM_CAPABILITY_TOOLS: Record<PlatformCapability, string[]> = {
  [PLATFORM_CAPABILITY_SCHEDULING]: SCHEDULER_TOOLS,
  [PLATFORM_CAPABILITY_REPORTS]: REPORT_TOOLS,
}

function deriveBoundTools(config: AgentCapabilityConfig, skills: AgentSkillCatalogItem[]): string[] {
  const names: string[] = []
  const add = (name: string) => {
    if (name && !names.includes(name)) {
      names.push(name)
    }
  }
  if (config.skills.length > 0) {
    CORE_SKILL_TOOLS.forEach(add)
    for (const skillName of config.skills) {
      const skill = skills.find((item) => item.name === skillName)
      skill?.tools?.forEach(add)
    }
  }
  if (config.knowledge_base_ids.length > 0) {
    KNOWLEDGE_TOOLS.forEach(add)
  }
  if (config.data_source_ids.length > 0) {
    DATA_SOURCE_TOOLS.forEach(add)
  }
  if (config.api_connector_ids.length > 0) {
    API_CONNECTOR_TOOLS.forEach(add)
  }
  for (const capability of config.platform_capabilities ?? []) {
    PLATFORM_CAPABILITY_TOOLS[capability]?.forEach(add)
  }
  return names
}

function PlatformCapabilitiesGroup({
  label,
  selected,
  onToggle,
}: {
  label: string
  selected: PlatformCapability[]
  onToggle: (capability: PlatformCapability) => void
}) {
  const { t } = useTranslation()
  const items: { id: PlatformCapability; label: string; hint: string }[] = [
    {
      id: PLATFORM_CAPABILITY_SCHEDULING,
      label: t('agents.platformScheduling'),
      hint: t('agents.platformSchedulingHint'),
    },
    {
      id: PLATFORM_CAPABILITY_REPORTS,
      label: t('agents.platformReports'),
      hint: t('agents.platformReportsHint'),
    },
  ]
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="space-y-2 rounded-md border p-3">
        {items.map((item) => (
          <label key={item.id} className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={selected.includes(item.id)}
              onCheckedChange={() => onToggle(item.id)}
            />
            <span>
              <span className="font-medium">{item.label}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{item.hint}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}

function DerivedToolsPreview({
  config,
  skills,
}: {
  config: AgentCapabilityConfig
  skills: AgentSkillCatalogItem[]
}) {
  const { t } = useTranslation()
  const tools = deriveBoundTools(config, skills)
  return (
    <div className="space-y-2">
      <Label>{t('agents.tools')}</Label>
      <p className="text-xs text-muted-foreground">{t('agents.toolsHint')}</p>
      <div className="rounded-md border p-3">
        {tools.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('agents.toolsEmpty')}</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {tools.map((name) => (
              <span key={name} className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs">
                {name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function CheckboxGroup({
  label,
  items,
  selected,
  onToggle,
}: {
  label: string
  items: { id: string; label: string }[]
  selected: string[]
  onToggle: (id: string) => void
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">—</p>
        ) : (
          items.map((item) => (
            <label key={item.id} className="flex items-center gap-2 text-sm">
              <Checkbox checked={selected.includes(item.id)} onCheckedChange={() => onToggle(item.id)} />
              <span>{item.label}</span>
            </label>
          ))
        )}
      </div>
    </div>
  )
}
