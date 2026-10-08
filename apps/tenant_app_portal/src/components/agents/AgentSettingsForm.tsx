import { Loader2 } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import MultiSelectField from '@/components/agents/MultiSelectField'
import SettingsSection from '@/components/SettingsSection'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { AgentCapabilityConfig, AgentSkillCatalogItem } from '@/lib/agentsApi'
import { usePlatformCapabilities } from '@/hooks/useAgents'
import type { LLMModelProfile } from '@/lib/llmConfigApi'

/** UI copy keys for platform capability ids returned by the catalog API. */
const PLATFORM_CAPABILITY_COPY: Record<string, { labelKey: string; hintKey: string }> = {
  scheduling: { labelKey: 'agents.platformScheduling', hintKey: 'agents.platformSchedulingHint' },
  reports: { labelKey: 'agents.platformReports', hintKey: 'agents.platformReportsHint' },
  workspace: { labelKey: 'agents.platformWorkspace', hintKey: 'agents.platformWorkspaceHint' },
}

const agentFormResources = {
  en: {
    name: 'Name',
    prompt: 'System prompt',
    sectionGeneral: 'General',
    sectionGeneralDesc: 'Name, model, and instructions for this agent.',
    sectionAccess: 'Access',
    sectionAccessDesc: 'Skills, platform features, and tenant resources.',
    platformFeatures: 'Platform features',
    platformCapabilitiesHint: 'Script-based skills may require Workspace.',
    platformScheduling: 'Scheduling',
    platformSchedulingHint: 'Create and manage scheduled tasks for this agent.',
    platformReports: 'Reports',
    platformReportsHint: 'Create and update file-backed reports.',
    platformWorkspace: 'Workspace',
    platformWorkspaceHint: 'Run sandbox scripts and use /workspace (needed for some script-based skills).',
    skills: 'Skills',
    skillsHelp: 'Packages loaded with load_skill during conversation.',
    knowledge: 'Knowledge bases',
    dataSources: 'Data sources',
    apis: 'API connectors',
    multiSelectAdd: 'Add…',
    multiSelectSearch: 'Search…',
    multiSelectEmpty: 'Nothing available to add.',
    multiSelectNoResults: 'No matches.',
    save: 'Save',
    saveSuccess: 'Agent saved',
    saveFailed: 'Failed to save agent',
    cancel: 'Cancel',
    modelProfile: 'Model',
    modelProfileHint: 'Override the tenant default LLM for this agent.',
    tenantDefaultModel: 'Tenant default',
  },
  zh: {
    name: '名称',
    prompt: '系统提示词',
    sectionGeneral: '常规',
    sectionGeneralDesc: '名称、模型与系统指令。',
    sectionAccess: '访问权限',
    sectionAccessDesc: '技能、平台功能与租户资源。',
    platformFeatures: '平台功能',
    platformCapabilitiesHint: '部分脚本类技能可能需要启用工作区。',
    platformScheduling: '定时任务',
    platformSchedulingHint: '为此智能体创建和管理定时任务。',
    platformReports: '报告',
    platformReportsHint: '创建和更新基于文件的报告。',
    platformWorkspace: '工作区',
    platformWorkspaceHint: '在沙箱中运行脚本并使用 /workspace（部分脚本类技能需要）。',
    skills: '技能',
    skillsHelp: '对话中通过 load_skill 加载的技能包。',
    knowledge: '知识库',
    dataSources: '数据源',
    apis: 'API 连接器',
    multiSelectAdd: '添加…',
    multiSelectSearch: '搜索…',
    multiSelectEmpty: '暂无可添加项。',
    multiSelectNoResults: '无匹配结果。',
    save: '保存',
    saveSuccess: '智能体已保存',
    saveFailed: '保存智能体失败',
    cancel: '取消',
    modelProfile: '模型',
    modelProfileHint: '覆盖租户默认 LLM，留空则使用租户默认。',
    tenantDefaultModel: '租户默认',
  },
} as const

for (const [lang, agents] of Object.entries(agentFormResources)) {
  i18n.addResourceBundle(lang, 'translation', { agents }, true, true)
}

export const emptyAgentConfig = (): AgentCapabilityConfig => ({
  default_tools: [],
  skills: [],
  knowledge_base_ids: [],
  data_source_ids: [],
  api_connector_ids: [],
  platform_capabilities: [],
  model_profile_id: null,
})

type AgentSettingsFormProps = {
  formName: string
  formPrompt: string
  formConfig: AgentCapabilityConfig
  formError: string | null
  skills: AgentSkillCatalogItem[]
  collections: { id: number; name: string }[]
  dataSources: { id: number; name: string }[]
  connectors: { id: number; name: string }[]
  llmProfiles: LLMModelProfile[]
  readOnly?: boolean
  saving?: boolean
  onNameChange: (value: string) => void
  onPromptChange: (value: string) => void
  onConfigChange: (config: AgentCapabilityConfig) => void
  onSave?: () => void
  onCancel?: () => void
  showActions?: boolean
}

export function agentConfigFromAgent(
  config: AgentCapabilityConfig | undefined
): AgentCapabilityConfig {
  return {
    ...emptyAgentConfig(),
    ...config,
    platform_capabilities: config?.platform_capabilities ?? [],
  }
}

export default function AgentSettingsForm({
  formName,
  formPrompt,
  formConfig,
  formError,
  skills,
  collections,
  dataSources,
  connectors,
  llmProfiles,
  readOnly = false,
  saving = false,
  onNameChange,
  onPromptChange,
  onConfigChange,
  onSave,
  onCancel,
  showActions = true,
}: AgentSettingsFormProps) {
  const { t } = useTranslation()
  const { data: platformCapabilities = [] } = usePlatformCapabilities()

  const skillOptions = useMemo(
    () =>
      skills.map((skill) => ({
        id: skill.name,
        label: skill.name,
        description: skill.description || skill.scope,
      })),
    [skills]
  )

  const collectionOptions = useMemo(
    () => collections.map((c) => ({ id: String(c.id), label: c.name })),
    [collections]
  )
  const dataSourceOptions = useMemo(
    () => dataSources.map((s) => ({ id: String(s.id), label: s.name })),
    [dataSources]
  )
  const connectorOptions = useMemo(
    () => connectors.map((c) => ({ id: String(c.id), label: c.name })),
    [connectors]
  )

  const platformOptions = useMemo(
    () =>
      platformCapabilities.map((id) => {
        const copy = PLATFORM_CAPABILITY_COPY[id]
        return {
          id,
          label: copy ? t(copy.labelKey) : id,
          description: copy ? t(copy.hintKey) : undefined,
        }
      }),
    [platformCapabilities, t]
  )

  const multiSelectMessages = {
    placeholder: t('agents.multiSelectAdd'),
    searchPlaceholder: t('agents.multiSelectSearch'),
    emptyOptionsMessage: t('agents.multiSelectEmpty'),
    noResultsMessage: t('agents.multiSelectNoResults'),
  }

  const showFormActions = showActions && !readOnly && onSave

  return (
    <div className="space-y-4">
      <SettingsSection title={t('agents.sectionGeneral')} description={t('agents.sectionGeneralDesc')}>
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="agent-name">{t('agents.name')}</Label>
              <Input
                id="agent-name"
                value={formName}
                onChange={(event) => onNameChange(event.target.value)}
                disabled={readOnly}
              />
            </div>
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
                  onConfigChange({
                    ...formConfig,
                    model_profile_id: value === 'tenant-default' ? null : Number(value),
                  })
                }
                disabled={readOnly}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tenant-default">{t('agents.tenantDefaultModel')}</SelectItem>
                  {llmProfiles.map((profile) => (
                    <SelectItem key={profile.id} value={String(profile.id)}>
                      {profile.name} ({profile.model_id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="agent-prompt">{t('agents.prompt')}</Label>
            <Textarea
              id="agent-prompt"
              value={formPrompt}
              onChange={(event) => onPromptChange(event.target.value)}
              rows={10}
              disabled={readOnly}
              className="font-mono text-sm"
            />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title={t('agents.sectionAccess')} description={t('agents.sectionAccessDesc')}>
        <div className="space-y-4">
          <MultiSelectField
            label={t('agents.skills')}
            help={t('agents.skillsHelp')}
            options={skillOptions}
            selectedIds={formConfig.skills}
            disabled={readOnly}
            onChange={(skillsSelected) => onConfigChange({ ...formConfig, skills: skillsSelected })}
            {...multiSelectMessages}
          />

          {platformOptions.length > 0 ? (
            <MultiSelectField
              label={t('agents.platformFeatures')}
              help={t('agents.platformCapabilitiesHint')}
              options={platformOptions}
              selectedIds={formConfig.platform_capabilities}
              disabled={readOnly}
              onChange={(capabilities) =>
                onConfigChange({ ...formConfig, platform_capabilities: capabilities })
              }
              {...multiSelectMessages}
            />
          ) : null}

          <MultiSelectField
            label={t('agents.knowledge')}
            options={collectionOptions}
            selectedIds={formConfig.knowledge_base_ids.map(String)}
            disabled={readOnly}
            onChange={(ids) =>
              onConfigChange({
                ...formConfig,
                knowledge_base_ids: ids.map(Number),
              })
            }
            {...multiSelectMessages}
          />
          <MultiSelectField
            label={t('agents.dataSources')}
            options={dataSourceOptions}
            selectedIds={formConfig.data_source_ids.map(String)}
            disabled={readOnly}
            onChange={(ids) =>
              onConfigChange({
                ...formConfig,
                data_source_ids: ids.map(Number),
              })
            }
            {...multiSelectMessages}
          />
          <MultiSelectField
            label={t('agents.apis')}
            options={connectorOptions}
            selectedIds={formConfig.api_connector_ids.map(String)}
            disabled={readOnly}
            onChange={(ids) =>
              onConfigChange({
                ...formConfig,
                api_connector_ids: ids.map(Number),
              })
            }
            {...multiSelectMessages}
          />
        </div>
      </SettingsSection>

      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

      {showFormActions ? (
        <div className="flex justify-end gap-2 pt-2">
          {onCancel ? (
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
              {t('agents.cancel')}
            </Button>
          ) : null}
          <Button type="button" onClick={onSave} disabled={!formName.trim() || saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {t('agents.save')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
