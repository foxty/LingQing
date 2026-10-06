import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Bot, Loader2 } from 'lucide-react'
import AgentFeedbackPanel from '@/components/agents/AgentFeedbackPanel'
import AgentSettingsForm, { agentConfigFromAgent } from '@/components/agents/AgentSettingsForm'
import AgentSlackIntegrationSection from '@/components/agents/AgentSlackIntegrationSection'
import ContainerDetailHeader from '@/components/ContainerDetailHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/hooks/useAuth'
import {
  useAgent,
  useAgentSkillCatalog,
  useUpdateAgent,
} from '@/hooks/useAgents'
import { useDocumentCollections } from '@/hooks/useDocumentCollections'
import { agentApiErrorMessage, type AgentCapabilityConfig } from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDataSources } from '@/lib/dataSourceApi'
import { listRegistryProfiles } from '@/lib/llmConfigApi'
import { PERMISSIONS, routeRules } from '@/lib/permissionRules'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useFeedbackStats } from '@/hooks/useMessageFeedbackAnalysis'

const TAB_OVERVIEW = 'overview'
const TAB_SETTINGS = 'settings'
const TAB_INTEGRATIONS = 'integrations'
const TAB_FEEDBACK = 'feedback'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    agentDetail: {
      parentLabel: 'Agents',
      notFound: 'Agent not found',
      invalidId: 'Invalid agent ID',
      loadFailed: 'Failed to load agent',
      tabOverview: 'Overview',
      tabSettings: 'Settings',
      tabIntegrations: 'Integrations',
      tabFeedback: 'Feedback',
      readOnlySettings: 'Built-in agents cannot be edited here.',
      totalFeedback: 'Total feedback',
      positiveRate: 'Positive rate',
      viewAllFeedback: 'View all feedback',
    },
    agents: {
      system: 'Built-in',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    agentDetail: {
      parentLabel: '智能体',
      notFound: '未找到智能体',
      invalidId: '无效的智能体 ID',
      loadFailed: '加载智能体失败',
      tabOverview: '概览',
      tabSettings: '设置',
      tabIntegrations: '集成',
      tabFeedback: '反馈',
      readOnlySettings: '内置智能体无法在此编辑。',
      totalFeedback: '反馈总数',
      positiveRate: '好评率',
      viewAllFeedback: '查看全部反馈',
    },
    agents: {
      system: '内置',
    },
  },
  true,
  true
)

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default function AgentDetailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { agentId: agentIdParam } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const { hasAny } = useAuth()

  const agentId = agentIdParam ? Number(agentIdParam) : NaN
  const activeTab = searchParams.get('tab') ?? TAB_OVERVIEW

  const canManageTenantSlack = hasAny([PERMISSIONS.AUTH_PROVIDERS_MANAGE])
  const canViewFeedback = hasAny(routeRules.canAccessAgentFeedback())

  const { data: agent, isLoading, isError } = useAgent(Number.isFinite(agentId) ? agentId : undefined)
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
  const { data: llmProfiles = [] } = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
  })
  const updateMutation = useUpdateAgent()

  const [formName, setFormName] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formConfig, setFormConfig] = useState<AgentCapabilityConfig>(agentConfigFromAgent(undefined))
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!agent) {
      return
    }
    setFormName(agent.name)
    setFormPrompt(agent.system_prompt)
    setFormConfig(agentConfigFromAgent(agent.config))
    setFormError(null)
  }, [agent])

  if (!Number.isFinite(agentId)) {
    return <Navigate to="/agents" replace />
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        {t('common.loading')}
      </div>
    )
  }

  if (isError || !agent) {
    return (
      <div className="space-y-4">
        <ContainerDetailHeader
          parentLabel={t('agentDetail.parentLabel')}
          onParentNavigate={() => navigate('/agents')}
          title={t('agentDetail.notFound')}
        />
        <Alert variant="destructive">
          <AlertDescription>{t('agentDetail.loadFailed')}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const canManageSlack = agent.is_system ? canManageTenantSlack : agent.can_manage
  const canEdit = !agent.is_system && agent.can_write

  const tabs = [
    { id: TAB_OVERVIEW, label: t('agentDetail.tabOverview'), visible: true },
    { id: TAB_SETTINGS, label: t('agentDetail.tabSettings'), visible: true },
    { id: TAB_INTEGRATIONS, label: t('agentDetail.tabIntegrations'), visible: canManageSlack },
    { id: TAB_FEEDBACK, label: t('agentDetail.tabFeedback'), visible: canViewFeedback },
  ].filter((tab) => tab.visible)

  const resolvedTab = tabs.some((tab) => tab.id === activeTab) ? activeTab : TAB_OVERVIEW

  const setTab = (tab: string) => {
    const next = new URLSearchParams(searchParams)
    if (tab === TAB_OVERVIEW) {
      next.delete('tab')
    } else {
      next.set('tab', tab)
    }
    setSearchParams(next, { replace: true })
  }

  const saveSettings = async () => {
    if (!canEdit) {
      return
    }
    try {
      setFormError(null)
      const updated = await updateMutation.mutateAsync({
        agentId: agent.id,
        payload: {
          name: formName.trim(),
          system_prompt: formPrompt,
          config: formConfig,
        },
      })
      setFormConfig(agentConfigFromAgent(updated.config))
    } catch (error) {
      setFormError(agentApiErrorMessage(error, t('agents.saveFailed')))
    }
  }

  return (
    <div className="space-y-4">
      <ContainerDetailHeader
        parentLabel={t('agentDetail.parentLabel')}
        onParentNavigate={() => navigate('/agents')}
        title={agent.name}
        meta={
          agent.is_system ? (
            <Badge variant="secondary">{t('agents.system')}</Badge>
          ) : null
        }
      />

      <Tabs value={resolvedTab} onValueChange={setTab}>
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={TAB_OVERVIEW} className="mt-4 space-y-4">
          <OverviewTab agentId={agent.id} canViewFeedback={canViewFeedback} description={agent.description || agent.system_prompt} />
        </TabsContent>

        <TabsContent value={TAB_SETTINGS} className="mt-4">
          {agent.is_system ? (
            <Alert>
              <AlertDescription>{t('agentDetail.readOnlySettings')}</AlertDescription>
            </Alert>
          ) : null}
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
            readOnly={!canEdit}
            saving={updateMutation.isPending}
            showActions={canEdit}
            onNameChange={setFormName}
            onPromptChange={setFormPrompt}
            onConfigChange={setFormConfig}
            onSave={() => void saveSettings()}
          />
        </TabsContent>

        {canManageSlack ? (
          <TabsContent value={TAB_INTEGRATIONS} className="mt-4">
            <AgentSlackIntegrationSection
              agentId={agent.id}
              canManage={canManageSlack}
              embedded
              onChanged={() => {
                queryClient.invalidateQueries({ queryKey: ['slack-integrations'] })
              }}
            />
          </TabsContent>
        ) : null}

        {canViewFeedback ? (
          <TabsContent value={TAB_FEEDBACK} className="mt-4">
            <AgentFeedbackPanel
              agentId={agent.id}
              showAgentFilter={false}
              showAgentColumn={false}
            />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  )
}

function OverviewTab({
  agentId,
  canViewFeedback,
  description,
}: {
  agentId: number
  canViewFeedback: boolean
  description: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const statsQuery = useFeedbackStats({ agent_id: agentId })

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-2 pt-6">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Bot className="h-4 w-4" />
            {t('agents.prompt')}
          </div>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{description}</p>
        </CardContent>
      </Card>

      {canViewFeedback ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">{t('agentDetail.totalFeedback')}</p>
              {statsQuery.isLoading ? (
                <Loader2 className="mt-2 h-5 w-5 animate-spin text-muted-foreground" />
              ) : (
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {statsQuery.data?.total_count ?? 0}
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">{t('agentDetail.positiveRate')}</p>
              {statsQuery.isLoading ? (
                <Loader2 className="mt-2 h-5 w-5 animate-spin text-muted-foreground" />
              ) : (
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {formatPercent(statsQuery.data?.positive_rate ?? 0)}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {canViewFeedback ? (
        <Button variant="outline" onClick={() => navigate(`/agents/${agentId}?tab=feedback`)}>
          {t('agentDetail.viewAllFeedback')}
        </Button>
      ) : null}
    </div>
  )
}
