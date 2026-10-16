import type { CatalogProvider, LLMDefaults, LLMModelProfile, LLMProvider } from '@/lib/llmConfigApi'
import { inferCatalogPresetKey } from '@/lib/llmConfigApi'
import type { AgentCapabilityConfig } from '@/lib/agentsApi'

export function catalogEntryForModelKey(
  catalog: CatalogProvider[],
  catalogModelKey: string | null | undefined
) {
  if (!catalogModelKey) {
    return null
  }
  for (const provider of catalog) {
    const model = provider.models.find((item) => item.key === catalogModelKey)
    if (model) {
      return { provider, model }
    }
  }
  return null
}

export function profileSupportsThinkingControl(
  profile: LLMModelProfile | undefined,
  provider: LLMProvider | undefined,
  catalog: CatalogProvider[]
): boolean {
  if (!profile || profile.category !== 'llm') {
    return false
  }
  const byKey = catalogEntryForModelKey(catalog, profile.catalog_model_key)
  if (byKey?.model.metadata?.supports_thinking === true) {
    return true
  }
  if (!provider) {
    return false
  }
  const presetKey = inferCatalogPresetKey(provider, catalog)
  const preset = catalog.find((item) => item.key === presetKey || item.provider === presetKey)
  if (!preset) {
    return false
  }
  const model = preset.models.find((item) => item.model_id === profile.model_id)
  return model?.metadata?.supports_thinking === true
}

export function resolveAgentLlmProfile(
  agentConfig: AgentCapabilityConfig | undefined,
  defaults: LLMDefaults,
  profiles: LLMModelProfile[]
): LLMModelProfile | undefined {
  const profileId = agentConfig?.model_profile_id ?? defaults.agent_profile_id
  if (profileId == null) {
    return undefined
  }
  return profiles.find((profile) => profile.id === profileId && profile.category === 'llm')
}

export function agentSupportsThinkingEffortControl(input: {
  agentConfig: AgentCapabilityConfig | undefined
  defaults: LLMDefaults
  profiles: LLMModelProfile[]
  providers: LLMProvider[]
  catalog: CatalogProvider[]
}): boolean {
  const profile = resolveAgentLlmProfile(input.agentConfig, input.defaults, input.profiles)
  if (!profile) {
    return false
  }
  const provider = input.providers.find((item) => item.id === profile.provider_id)
  return profileSupportsThinkingControl(profile, provider, input.catalog)
}
