import { describe, expect, it } from 'vitest'

import {
  addScopesUnique,
  filterScopeSuggestions,
  removeScope,
  splitScopeTokens,
} from '@/lib/oauthScopeChips'

describe('oauthScopeChips', () => {
  it('splits paste into unique tokens', () => {
    expect(splitScopeTokens('sql offline_access  sql')).toEqual(['sql', 'offline_access', 'sql'])
  })

  it('adds scopes without duplicates', () => {
    expect(addScopesUnique(['sql'], ['offline_access', 'sql'])).toEqual(['sql', 'offline_access'])
  })

  it('removes one scope', () => {
    expect(removeScope(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('filters suggestions by query and selection', () => {
    const all = ['sql', 'offline_access', 'sql:read:restricted-query', 'sql:restricted-query'] as const
    expect(filterScopeSuggestions(all, ['sql'], 'offline')).toEqual(['offline_access'])
    expect(filterScopeSuggestions(all, [], 'sql')).toEqual(['sql', 'sql:read:restricted-query', 'sql:restricted-query'])
  })
})
