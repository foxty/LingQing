import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import AgentSettingsForm, { emptyAgentConfig } from '@/components/agents/AgentSettingsForm'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useAgentSkillCatalog, useCreateAgent } from '@/hooks/useAgents'
import { useDocumentCollections } from '@/hooks/useDocumentCollections'
import {
  agentApiErrorMessage,
  type AgentCapabilityConfig,
  type CatalogAgent,
} from '@/lib/agentsApi'
import { listApiConnectors } from '@/lib/apiConnectorApi'
import { listDataSources } from '@/lib/dataSourceApi'
import { listRegistryProfiles } from '@/lib/llmConfigApi'
import { useQuery } from '@tanstack/react-query'

type AgentCreateDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultPrompt?: string
  onCreated: (agent: CatalogAgent) => void
}

export default function AgentCreateDrawer({
  open,
  onOpenChange,
  defaultPrompt = '',
  onCreated,
}: AgentCreateDrawerProps) {
  const { t } = useTranslation()
  const createMutation = useCreateAgent()
  const { data: skills = [] } = useAgentSkillCatalog()
  const { data: collections = [] } = useDocumentCollections()
  const { data: dataSources = [] } = useQuery({
    queryKey: ['agent-data-sources'],
    queryFn: async () => (await listDataSources(1, 100)).items ?? [],
    enabled: open,
  })
  const { data: connectors = [] } = useQuery({
    queryKey: ['agent-api-connectors'],
    queryFn: listApiConnectors,
    enabled: open,
  })
  const { data: llmProfiles = [] } = useQuery({
    queryKey: ['llm-profiles', 'llm'],
    queryFn: () => listRegistryProfiles('llm'),
    enabled: open,
  })

  const [formName, setFormName] = useState('')
  const [formPrompt, setFormPrompt] = useState('')
  const [formConfig, setFormConfig] = useState<AgentCapabilityConfig>(emptyAgentConfig())
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    setFormName('')
    setFormPrompt(defaultPrompt)
    setFormConfig(emptyAgentConfig())
    setFormError(null)
  }, [defaultPrompt, open])

  const saveCreate = async () => {
    const payload = {
      name: formName.trim(),
      system_prompt: formPrompt,
      config: formConfig,
    }
    try {
      setFormError(null)
      const created = await createMutation.mutateAsync(payload)
      onOpenChange(false)
      onCreated(created)
    } catch (error) {
      setFormError(agentApiErrorMessage(error, t('agents.saveFailed')))
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-[560px]">
        <SheetHeader className="border-b px-6 py-4">
          <SheetTitle>{t('agents.create')}</SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-6 py-4">
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
        </div>
        <SheetFooter className="border-t px-6 py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('agents.cancel')}
          </Button>
          <Button
            onClick={() => void saveCreate()}
            disabled={!formName.trim() || createMutation.isPending}
          >
            {t('agents.save')}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
