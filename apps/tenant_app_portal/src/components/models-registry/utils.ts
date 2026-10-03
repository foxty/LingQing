import {
  catalogModelsForProvider,
  inferCatalogPresetKey,
  type CatalogProvider,
  type LLMModelProfile,
  type LLMProvider,
  type ModelProfileCategory,
} from '@/lib/llmConfigApi'

export function modelCountLabel(profiles: LLMModelProfile[], providerId: number): string {
  const linked = profiles.filter((profile) => profile.provider_id === providerId)
  const llmCount = linked.filter((profile) => profile.category === 'llm').length
  const embeddingCount = linked.filter((profile) => profile.category === 'embedding').length
  const parts: string[] = []
  if (llmCount) {
    parts.push(`${llmCount} LLM`)
  }
  if (embeddingCount) {
    parts.push(`${embeddingCount} Emb`)
  }
  return parts.join(' · ') || '—'
}

export function presetDisplayName(provider: LLMProvider, catalog: CatalogProvider[]): string {
  const presetKey = inferCatalogPresetKey(provider, catalog)
  if (!presetKey) {
    return '—'
  }
  const preset = catalog.find((item) => item.key === presetKey || item.provider === presetKey)
  return preset?.name || presetKey
}

export function unregisteredCatalogModels(
  provider: LLMProvider,
  profiles: LLMModelProfile[],
  catalog: CatalogProvider[]
) {
  const linked = profiles.filter((profile) => profile.provider_id === provider.id)
  return (['llm', 'embedding'] as ModelProfileCategory[]).flatMap((category) =>
    catalogModelsForProvider(provider, catalog, category).filter(
      (model) =>
        !linked.some(
          (profile) =>
            profile.model_id === model.model_id &&
            profile.category === (model.category === 'embedding' ? 'embedding' : 'llm')
        )
    )
  )
}

export function defaultBadgesForProfile(
  profileId: number,
  defaults: {
    agent_profile_id: number | null
    mini_agent_profile_id: number | null
    embedding_profile_id: number | null
  },
  t: (key: string) => string
): string[] {
  const badges: string[] = []
  if (defaults.agent_profile_id === profileId) {
    badges.push(t('settings.modelsRegistry.badgeAgentDefault'))
  }
  if (defaults.mini_agent_profile_id === profileId) {
    badges.push(t('settings.modelsRegistry.badgeMiniDefault'))
  }
  if (defaults.embedding_profile_id === profileId) {
    badges.push(t('settings.modelsRegistry.badgeEmbeddingDefault'))
  }
  return badges
}
