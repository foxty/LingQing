import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
  PLATFORM_CAPABILITY_REPORTS,
  PLATFORM_CAPABILITY_SCHEDULING,
  type AgentCapabilityConfig,
  type AgentSkillCatalogItem,
  type PlatformCapability,
} from '@/lib/agentsApi'
import type { LLMModelProfile } from '@/lib/llmConfigApi'

const agentFormResources = {
  en: {
    name: 'Name',
    prompt: 'System prompt',
    tools: 'Tools',
    toolsHint: 'Always-on tools bound from skills, attached resources, and platform capabilities.',
    toolsSaveHint: 'The list below is computed on save. Skill-specific tools appear after load_skill at runtime.',
    toolsEmpty: 'No tools yet. Assign a skill, resource, or platform capability, then save.',
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
    saveSuccess: 'Agent saved',
    saveFailed: 'Failed to save agent',
    cancel: 'Cancel',
    modelProfile: 'Model profile',
    modelProfileHint: 'Override the tenant default LLM for this agent.',
    tenantDefaultModel: 'Tenant default',
  },
  zh: {
    name: '名称',
    prompt: '系统提示词',
    tools: '工具',
    toolsHint: '由技能、已绑定资源及平台能力绑定的常驻工具。',
    toolsSaveHint: '以下列表在保存时由服务端计算。技能专属工具在运行时通过 load_skill 加载。',
    toolsEmpty: '暂无工具。请分配技能、资源或平台能力后保存。',
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
    saveSuccess: '智能体已保存',
    saveFailed: '保存智能体失败',
    cancel: '取消',
    modelProfile: '模型配置',
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

function toggleListValue<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

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

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>{t('agents.name')}</Label>
        <Input
          value={formName}
          onChange={(event) => onNameChange(event.target.value)}
          disabled={readOnly}
        />
      </div>
      <div className="space-y-2">
        <Label>{t('agents.prompt')}</Label>
        <Textarea
          value={formPrompt}
          onChange={(event) => onPromptChange(event.target.value)}
          rows={6}
          disabled={readOnly}
        />
      </div>
      <CheckboxGroup
        label={t('agents.skills')}
        items={skills.map((skill) => ({ id: skill.name, label: `${skill.name} (${skill.scope})` }))}
        selected={formConfig.skills}
        disabled={readOnly}
        onToggle={(id) =>
          onConfigChange({
            ...formConfig,
            skills: toggleListValue(formConfig.skills, id),
          })
        }
      />
      <PlatformCapabilitiesGroup
        label={t('agents.platformCapabilities')}
        selected={formConfig.platform_capabilities}
        disabled={readOnly}
        onToggle={(capability) =>
          onConfigChange({
            ...formConfig,
            platform_capabilities: toggleListValue(formConfig.platform_capabilities, capability),
          })
        }
      />
      <CheckboxGroup
        label={t('agents.knowledge')}
        items={collections.map((collection) => ({ id: String(collection.id), label: collection.name }))}
        selected={formConfig.knowledge_base_ids.map(String)}
        disabled={readOnly}
        onToggle={(id) =>
          onConfigChange({
            ...formConfig,
            knowledge_base_ids: toggleListValue(formConfig.knowledge_base_ids, Number(id)),
          })
        }
      />
      <CheckboxGroup
        label={t('agents.dataSources')}
        items={dataSources.map((source) => ({ id: String(source.id), label: source.name }))}
        selected={formConfig.data_source_ids.map(String)}
        disabled={readOnly}
        onToggle={(id) =>
          onConfigChange({
            ...formConfig,
            data_source_ids: toggleListValue(formConfig.data_source_ids, Number(id)),
          })
        }
      />
      <CheckboxGroup
        label={t('agents.apis')}
        items={connectors.map((connector) => ({ id: String(connector.id), label: connector.name }))}
        selected={formConfig.api_connector_ids.map(String)}
        disabled={readOnly}
        onToggle={(id) =>
          onConfigChange({
            ...formConfig,
            api_connector_ids: toggleListValue(formConfig.api_connector_ids, Number(id)),
          })
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
      <DerivedToolsPreview tools={formConfig.default_tools} />
      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}
      {showActions && !readOnly && onSave ? (
        <div className="flex justify-end gap-2">
          {onCancel ? (
            <Button variant="outline" onClick={onCancel}>
              {t('agents.cancel')}
            </Button>
          ) : null}
          <Button onClick={onSave} disabled={!formName.trim() || saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {t('agents.save')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function PlatformCapabilitiesGroup({
  label,
  selected,
  disabled,
  onToggle,
}: {
  label: string
  selected: PlatformCapability[]
  disabled?: boolean
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
              disabled={disabled}
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

function DerivedToolsPreview({ tools }: { tools: string[] }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2">
      <Label>{t('agents.tools')}</Label>
      <p className="text-xs text-muted-foreground">{t('agents.toolsHint')}</p>
      <p className="text-xs text-muted-foreground">{t('agents.toolsSaveHint')}</p>
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
  disabled,
  onToggle,
}: {
  label: string
  items: { id: string; label: string }[]
  selected: string[]
  disabled?: boolean
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
              <Checkbox
                checked={selected.includes(item.id)}
                disabled={disabled}
                onCheckedChange={() => onToggle(item.id)}
              />
              <span>{item.label}</span>
            </label>
          ))
        )}
      </div>
    </div>
  )
}
