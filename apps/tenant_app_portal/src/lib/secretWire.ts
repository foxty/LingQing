/**
 * Wire + display contract for secrets (mirror apps/shared/utils/secret_wire.py).
 * Keep vectors in sync with tests/unit/shared/utils/test_secret_wire.py.
 *
 * Merge (server): null/empty only — omit keys on PATCH when unchanged.
 * GET: partial masks in JSON when available; ``masked_fields`` is the stored-secret source of truth.
 */

/**
 * Same string as a 3-char ``maskSecretForDisplay`` preview — strip in custom JSON only
 * (``isDisplayMask`` excludes this constant on purpose).
 */
export const API_SECRET_PLACEHOLDER = '***'

export function maskSecretForDisplay(value: string): string {
  if (!value) {
    return ''
  }
  if (value.length <= 4) {
    return '*'.repeat(value.length)
  }
  return value.slice(0, 2) + '*'.repeat(value.length - 4) + value.slice(-2)
}

export function isDisplayMask(value: string): boolean {
  if (!value || value === API_SECRET_PLACEHOLDER) {
    return false
  }
  if (value.length <= 4) {
    return [...value].every((ch) => ch === '*')
  }
  if (value.startsWith('*')) {
    return false
  }
  const middle = value.slice(2, -2)
  if (middle.length < 1) {
    return false
  }
  return [...middle].every((ch) => ch === '*')
}

/** Server merge semantics — unchanged only when null/empty. */
export function isUnchangedSecretOnWire(value: unknown): boolean {
  if (value == null) {
    return true
  }
  if (typeof value !== 'string') {
    return false
  }
  return !value.trim()
}

/**
 * Strip leaves before PATCH when sanitizing JSON text (e.g. custom ``extra_config``).
 * Structured secret fields use ``secretPayloadValue`` / ``masked_fields`` instead.
 */
export function shouldStripSecretLeafOnSubmit(value: string): boolean {
  if (isUnchangedSecretOnWire(value)) {
    return true
  }
  const trimmed = value.trim()
  if (trimmed === API_SECRET_PLACEHOLDER) {
    return true
  }
  return isDisplayMask(trimmed)
}

export function omitUnchangedSecretsDeep<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => omitUnchangedSecretsDeep(item)) as T
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (typeof child === 'string' && shouldStripSecretLeafOnSubmit(child)) {
        continue
      }
      out[key] = omitUnchangedSecretsDeep(child)
    }
    return out as T
  }
  return value
}