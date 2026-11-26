/** Helpers for OAuth authorize-scope chip input (space/comma separated tokens). */

export function normalizeScopeToken(raw: string): string {
  return raw.trim()
}

export function splitScopeTokens(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map(normalizeScopeToken)
    .filter(Boolean)
}

export function addScopesUnique(current: string[], incoming: string[]): string[] {
  const next = new Set(current)
  for (const item of incoming) {
    const token = normalizeScopeToken(item)
    if (token) {
      next.add(token)
    }
  }
  return Array.from(next)
}

export function removeScope(current: string[], scope: string): string[] {
  return current.filter((item) => item !== scope)
}

export function filterScopeSuggestions(
  suggestions: readonly string[],
  selected: string[],
  query: string,
): string[] {
  const selectedSet = new Set(selected)
  const normalized = query.trim().toLowerCase()
  return suggestions.filter((scope) => {
    if (selectedSet.has(scope)) {
      return false
    }
    if (!normalized) {
      return true
    }
    return scope.toLowerCase().includes(normalized)
  })
}