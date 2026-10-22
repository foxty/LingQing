import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import AsyncMultiSelectField from '@/components/agents/AsyncMultiSelectField'
import MultiSelectField from '@/components/agents/MultiSelectField'
import { useAuth } from '@/hooks/useAuth'
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
import {
  filterAgentSkillIds,
  type AgentAttachmentAccessItem,
  type AgentCapabilityConfig,
  type AgentFormFieldErrors,
  type AgentSkillCatalogItem,
} from '@/lib/agentsApi'
import {
  AGENT_ATTACHMENT_RESOURCE,
  attachmentLabelKey,
  buildAttachmentLabelMap,
  searchAgentAttachmentPicker,
  selectedAttachmentOptions,
  type AgentAttachmentPickerKind,
} from '@/lib/agentAttachmentPicker'
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
    promptHelp:
      'Role-specific instructions only. Platform rules (tools, workspace, skills, security) are applied automatically.',
    rolePromptPlaceholder:
      'Describe this agent\'s role, tone, and domain focus. Platform behavior is included automatically.',
    sectionGeneral: 'General',
    sectionGeneralDesc: 'Name, model, and role instructions for this agent.',
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
    multiSelectLoading: 'Searching…',
    save: 'Save',
    saveSuccess: 'Agent saved',
    saveFailed: 'Failed to save agent',
    cancel: 'Cancel',
    modelProfile: 'Model',
    modelProfileHint: 'Override the tenant default LLM for this agent.',
    tenantDefaultModel: 'Tenant default',
    validation: {
      nameRequired: 'Name is required.',
      promptRequired: 'System prompt is required.',
    },
  },
  zh: {
    name: '名称',
    prompt: '系统提示词',
    promptHelp: '仅填写角色与领域指令。平台通用规则（工具、工作区、技能、安全等）会自动附加。',
    rolePromptPlaceholder: '描述该智能体的角色、语气与领域。平台通用行为会自动包含。',
    sectionGeneral: '常规',
    sectionGeneralDesc: '名称、模型与角色指令。',
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
    multiSelectLoading: '搜索中…',
    save: '保存',
    saveSuccess: '智能体已保存',
    saveFailed: '保存智能体失败',
    cancel: '取消',
    modelProfile: '模型',
    modelProfileHint: '覆盖租户默认 LLM，留空则使用租户默认。',
    tenantDefaultModel: '租户默认',
    validation: {
      nameRequired: '请填写名称。',
      promptRequired: '请填写系统提示词。',
    },
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
  fieldErrors?: AgentFormFieldErrors
  skills: AgentSkillCatalogItem[]
  attachmentAccess?: AgentAttachmentAccessItem[]
  /** Resets picker label cache when switching agents or after save. */
  formResourceKey?: string
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
  config: AgentCapabilityConfig | undefined,
  availableSkillNames?: Iterable<string>
): AgentCapabilityConfig {
  const merged = {
    ...emptyAgentConfig(),
    ...config,
    platform_capabilities: config?.platform_capabilities ?? [],
  }
  if (availableSkillNames) {
    merged.skills = filterAgentSkillIds(merged.skills, new Set(availableSkillNames))
  }
  return merged
}

export default function AgentSettingsForm({
  formName,
  formPrompt,
  formConfig,
  formError,
  fieldErrors = {},
  skills,
  attachmentAccess,
  formResourceKey,
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
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const tenantId = user?.tenantId ?? 0
  const { data: platformCapabilities = [] } = usePlatformCapabilities()
  const [extraLabels, setExtraLabels] = useState<Record<string, string>>({})

  useEffect(() => {
    setExtraLabels({})
  }, [formResourceKey])

  const attachmentLabelMap = useMemo(
    () => buildAttachmentLabelMap(attachmentAccess),
    [attachmentAccess]
  )

  const rememberPickedLabel = useCallback((resourceType: string, option: { id: string; label: string }) => {
    const id = Number(option.id)
    if (!Number.isFinite(id)) {
      return
    }
    setExtraLabels((prev) => ({
      ...prev,
      [attachmentLabelKey(resourceType, id)]: option.label,
    }))
  }, [])

  const makeAttachmentSearch = useCallback(
    (kind: AgentAttachmentPickerKind) => (query: string) =>
      searchAgentAttachmentPicker(queryClient, tenantId, kind, query),
    [queryClient, tenantId]
  )

  const searchDataSources = useMemo(
    () => makeAttachmentSearch('data_source'),
    [makeAttachmentSearch]
  )
  const searchCollections = useMemo(
    () => makeAttachmentSearch('document_collection'),
    [makeAttachmentSearch]
  )
  const searchConnectors = useMemo(
    () => makeAttachmentSearch('api_connector'),
    [makeAttachmentSearch]
  )

  const skillOptions = useMemo(
    () =>
      skills.map((skill) => ({
        id: skill.name,
        label: skill.name,
        description: skill.description || skill.scope,
      })),
    [skills]
  )

  const knowledgeSelectedOptions = useMemo(
    () =>
      selectedAttachmentOptions(
        formConfig.knowledge_base_ids,
        AGENT_ATTACHMENT_RESOURCE.knowledge,
        attachmentLabelMap,
        extraLabels
      ),
    [attachmentLabelMap, extraLabels, formConfig.knowledge_base_ids]
  )
  const dataSourceSelectedOptions = useMemo(
    () =>
      selectedAttachmentOptions(
        formConfig.data_source_ids,
        AGENT_ATTACHMENT_RESOURCE.dataSource,
        attachmentLabelMap,
        extraLabels
      ),
    [attachmentLabelMap, extraLabels, formConfig.data_source_ids]
  )
  const connectorSelectedOptions = useMemo(
    () =>
      selectedAttachmentOptions(
        formConfig.api_connector_ids,
        AGENT_ATTACHMENT_RESOURCE.apiConnector,
        attachmentLabelMap,
        extraLabels
      ),
    [attachmentLabelMap, extraLabels, formConfig.api_connector_ids]
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
    loadingMessage: t('agents.multiSelectLoading'),
  }

  const showFormActions = showActions && !readOnly && onSave

  return (
    <div className="space-y-4">
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}

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
                errorMsg={fieldErrors.name}
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
            <p className="text-sm text-muted-foreground">{t('agents.promptHelp')}</p>
            <Textarea
              id="agent-prompt"
              value={formPrompt}
              onChange={(event) => onPromptChange(event.target.value)}
              rows={10}
              disabled={readOnly}
              className="font-mono text-sm"
              placeholder={t('agents.rolePromptPlaceholder')}
              errorMsg={fieldErrors.systemPrompt}
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

          <AsyncMultiSelectField
            label={t('agents.knowledge')}
            selectedOptions={knowledgeSelectedOptions}
            selectedIds={formConfig.knowledge_base_ids.map(String)}
            disabled={readOnly}
            searchOptions={searchCollections}
            onPickOption={(option) => rememberPickedLabel(AGENT_ATTACHMENT_RESOURCE.knowledge, option)}
            onChange={(ids) =>
              onConfigChange({
                ...formConfig,
                knowledge_base_ids: ids.map(Number),
              })
            }
            {...multiSelectMessages}
          />
          <AsyncMultiSelectField
            label={t('agents.dataSources')}
            selectedOptions={dataSourceSelectedOptions}
            selectedIds={formConfig.data_source_ids.map(String)}
            disabled={readOnly}
            searchOptions={searchDataSources}
            onPickOption={(option) => rememberPickedLabel(AGENT_ATTACHMENT_RESOURCE.dataSource, option)}
            onChange={(ids) =>
              onConfigChange({
                ...formConfig,
                data_source_ids: ids.map(Number),
              })
            }
            {...multiSelectMessages}
          />
          <AsyncMultiSelectField
            label={t('agents.apis')}
            selectedOptions={connectorSelectedOptions}
            selectedIds={formConfig.api_connector_ids.map(String)}
            disabled={readOnly}
            searchOptions={searchConnectors}
            onPickOption={(option) => rememberPickedLabel(AGENT_ATTACHMENT_RESOURCE.apiConnector, option)}
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

      {showFormActions ? (
        <div className="flex justify-end gap-2 pt-2">
          {onCancel ? (
            <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
              {t('agents.cancel')}
            </Button>
          ) : null}
          <Button
            type="button"
            onClick={onSave}
            disabled={!formName.trim() || !formPrompt.trim() || saving}
          >
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {t('agents.save')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
