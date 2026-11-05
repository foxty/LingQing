import {
  catalogModelsForProvider,
  inferCatalogPresetKey,
  type CatalogModel,
  type CatalogProvider,
  type LLMModelProfile,
  type LLMProvider,
  type ModelProfileCategory,
} from '@/lib/llmConfigApi'

export type ReasoningOptionDraft = {
  value: string
  name: string
}

export function parseOptionalFloat(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

export function parseOptionalInt(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number.parseInt(trimmed, 10)
  return Number.isFinite(parsed) ? parsed : undefined
}

export function profileDefaultThinkingEffort(profile: LLMModelProfile): string {
  const options = profile.reasoning_config?.thinking_effort_options ?? []
  const values = options.map((option) => option.value)
  const explicit = profile.reasoning_config?.default_thinking_effort?.trim()
  if (explicit && values.includes(explicit)) {
    return explicit
  }
  return values[0] ?? ''
}

export function profileReasoningOptionDrafts(profile: LLMModelProfile): ReasoningOptionDraft[] {
  const options = profile.reasoning_config?.thinking_effort_options ?? []
  if (!options.length) {
    return [{ value: '', name: '' }]
  }
  return options.map((option) => ({
    value: option.value,
    name: option.name === option.value ? '' : option.name,
  }))
}

/** Short operator-facing text from provider connection-test failures. */
export function summarizeConnectionTestMessage(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) {
    return trimmed
  }

  const withoutPrefix = trimmed.replace(/^Connection test failed:\s*/i, '')

  const jsonStart = withoutPrefix.indexOf('{')
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(withoutPrefix.slice(jsonStart)) as {
        error?: { message?: string }
        message?: string
      }
      const nested = parsed.error?.message ?? parsed.message
      if (typeof nested === 'string' && nested.trim()) {
        return nested.trim()
      }
    } catch {
      // fall through
    }
  }

  const codeMatch = withoutPrefix.match(/Error code:\s*\d+\s*-\s*(.+)/i)
  if (codeMatch?.[1]) {
    return summarizeConnectionTestMessage(codeMatch[1])
  }

  return withoutPrefix.length > 280 ? `${withoutPrefix.slice(0, 277)}…` : withoutPrefix
}

export function catalogModelHasReasoningControl(model: CatalogModel): boolean {
  return model.metadata?.supports_thinking === true
}

export function profileReasoningControlBadge(
  profile: LLMModelProfile,
  t: (key: string) => string
): string | null {
  if (profile.category !== 'llm') {
    return null
  }
  if (profile.reasoning_config?.supports_thinking === true) {
    return t('settings.modelsRegistry.badgeReasoningControl')
  }
  return null
}

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
