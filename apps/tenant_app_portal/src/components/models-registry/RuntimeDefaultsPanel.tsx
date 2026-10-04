import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { LLMDefaults, LLMModelProfile, LLMProvider } from '@/lib/llmConfigApi'
import { useTranslation } from 'react-i18next'
import { modelsRegistryKey, registerModelsRegistryI18n } from './i18n'

interface RuntimeDefaultsPanelProps {
  defaults: LLMDefaults
  llmProfiles: LLMModelProfile[]
  embeddingProfiles: LLMModelProfile[]
  providers: LLMProvider[]
  busy: boolean
  onChange: (defaults: LLMDefaults) => void
  onSave: () => void
}

function profileOptionLabel(profile: LLMModelProfile, providers: LLMProvider[]) {
  const providerName =
    providers.find((provider) => provider.id === profile.provider_id)?.display_name ||
    `#${profile.provider_id}`
  return `${providerName} › ${profile.model_id}`
}

export default function RuntimeDefaultsPanel({
  defaults,
  llmProfiles,
  embeddingProfiles,
  providers,
  busy,
  onChange,
  onSave,
}: RuntimeDefaultsPanelProps) {
  registerModelsRegistryI18n()
  const { t } = useTranslation()

  return (
    <div className="max-w-2xl space-y-4">
      <div className="grid gap-4">
        <DefaultSelect
          label={t(modelsRegistryKey('agentDefault'))}
          value={defaults.agent_profile_id}
          options={llmProfiles}
          providers={providers}
          onChange={(value) => onChange({ ...defaults, agent_profile_id: value })}
        />
        <DefaultSelect
          label={t(modelsRegistryKey('miniDefault'))}
          value={defaults.mini_agent_profile_id}
          options={llmProfiles}
          providers={providers}
          onChange={(value) => onChange({ ...defaults, mini_agent_profile_id: value })}
        />
        <DefaultSelect
          label={t(modelsRegistryKey('embeddingDefault'))}
          value={defaults.embedding_profile_id}
          options={embeddingProfiles}
          providers={providers}
          onChange={(value) => onChange({ ...defaults, embedding_profile_id: value })}
        />
      </div>
      <Button onClick={onSave} disabled={busy}>
        {t(modelsRegistryKey('save'))}
      </Button>
    </div>
  )
}

function DefaultSelect({
  label,
  value,
  options,
  providers,
  onChange,
}: {
  label: string
  value: number | null
  options: LLMModelProfile[]
  providers: LLMProvider[]
  onChange: (value: number | null) => void
}) {
  const { t } = useTranslation()

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select
        value={value === null ? 'unset' : String(value)}
        onValueChange={(next) => onChange(next === 'unset' ? null : Number(next))}
      >
        <SelectTrigger>
          <SelectValue placeholder={t(modelsRegistryKey('tenantDefault'))} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="unset">{t(modelsRegistryKey('tenantDefault'))}</SelectItem>
          {options.map((profile) => (
            <SelectItem key={profile.id} value={String(profile.id)}>
              {profileOptionLabel(profile, providers)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
