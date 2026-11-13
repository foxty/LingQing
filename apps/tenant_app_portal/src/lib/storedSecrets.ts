/** Matches API redaction for persisted secrets (see catalog_sync.API_SECRET_PLACEHOLDER). */
export const STORED_SECRET_PLACEHOLDER = '***'

/** Shown in password inputs when a secret exists server-side (displays as bullets). */
export const SAVED_SECRET_FORM_MASK = '********'

export function isStoredSecretPlaceholder(value: unknown): boolean {
  return value === STORED_SECRET_PLACEHOLDER
}

export function isSavedSecretFormMask(value: unknown): boolean {
  return value === SAVED_SECRET_FORM_MASK || value === STORED_SECRET_PLACEHOLDER
}

export function hasStoredMetadataSyncPassword(config: Record<string, unknown> | undefined): boolean {
  const block = config?.metadata_sync
  if (!block || typeof block !== 'object') return false
  return isStoredSecretPlaceholder((block as Record<string, unknown>).password)
}

export function hasStoredSharedPassword(config: Record<string, unknown> | undefined): boolean {
  return isStoredSecretPlaceholder(config?.password)
}
