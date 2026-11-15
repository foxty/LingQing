/**
 * Generic helpers for API ``masked_fields`` (approach A).
 * Resource-specific dot paths belong at the call site — not here.
 */

import { isDisplayMask } from '@/lib/secretWire'

export function hasMaskedFieldPath(
  maskedFields: readonly string[] | undefined,
  path: string,
): boolean {
  return (maskedFields ?? []).includes(path)
}

/** User connection GET: ``secrets.{key}`` entries. */
export function secretKeysFromMaskedFields(maskedFields: readonly string[] | undefined): string[] {
  const keys: string[] = []
  for (const path of maskedFields ?? []) {
    if (path.startsWith('secrets.')) {
      keys.push(path.slice('secrets.'.length))
    }
  }
  return keys
}

/** BYOT GET: which secret leaves are stored (from ``masked_fields``). */
export function configuredSecretKeysFromConnection(status: {
  masked_fields?: string[]
}): string[] {
  return secretKeysFromMaskedFields(status.masked_fields)
}

/** Inline partial mask from GET config/auth JSON — preview text only (not “stored” detection). */
export function getSecretMaskedPreview(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) {
    return null
  }
  if (isDisplayMask(value)) {
    return value
  }
  return null
}