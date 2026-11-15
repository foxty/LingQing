/** Shared contract for optional secret updates (create / edit / saved test). */

export type SecretFieldMode = 'create' | 'edit'

export type SecretFieldBinding = {
  mode: SecretFieldMode
  stored: boolean
  editing: boolean
  draft: string
}

/** Payload value: undefined = omit (server keeps stored); string = new secret. */
export function secretPayloadValue(binding: SecretFieldBinding): string | undefined {
  const trimmed = binding.draft.trim()
  if (binding.mode === 'create') {
    return trimmed || undefined
  }
  if (!binding.stored) {
    return trimmed || undefined
  }
  if (!binding.editing) {
    return undefined
  }
  return trimmed || undefined
}

export function validateSecretRequired(binding: SecretFieldBinding, message: string): string | null {
  if (binding.mode === 'edit' && binding.stored && !binding.editing) {
    return null
  }
  if (secretPayloadValue(binding)) {
    return null
  }
  return message
}

export function validateSecretWhenEditing(binding: SecretFieldBinding, message: string): string | null {
  if (!binding.editing) {
    return null
  }
  if (binding.draft.trim()) {
    return null
  }
  return message
}

export function applySecretKey(
  record: Record<string, unknown>,
  key: string,
  binding: SecretFieldBinding,
): Record<string, unknown> {
  const value = secretPayloadValue(binding)
  const next = { ...record }
  if (value === undefined) {
    delete next[key]
    return next
  }
  next[key] = value
  return next
}

export function applyNestedSecretKey(
  record: Record<string, unknown>,
  parentKey: string,
  key: string,
  binding: SecretFieldBinding,
): Record<string, unknown> {
  const value = secretPayloadValue(binding)
  const next = { ...record }
  const block = { ...((next[parentKey] as Record<string, unknown>) || {}) }
  if (value === undefined) {
    delete block[key]
  } else {
    block[key] = value
  }
  if (Object.keys(block).length === 0) {
    delete next[parentKey]
  } else {
    next[parentKey] = block
  }
  return next
}

export function isSecretSatisfiedForTest(binding: SecretFieldBinding): boolean {
  if (binding.mode === 'create') {
    return Boolean(binding.draft.trim())
  }
  if (binding.stored && !binding.editing) {
    return true
  }
  return Boolean(binding.draft.trim())
}