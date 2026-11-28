import { describe, expect, it } from 'vitest'

import type { ApiConnector } from '@/lib/apiConnectorApi'
import { isPackInstalledForTenant, packIdFromRef } from '@/lib/packConnectorUtils'

describe('packIdFromRef', () => {
  it('strips major suffix from pack_ref', () => {
    expect(packIdFromRef('slack-user@1')).toBe('slack-user')
    expect(packIdFromRef('github-user@2')).toBe('github-user')
  })

  it('returns null for empty input', () => {
    expect(packIdFromRef(null)).toBeNull()
    expect(packIdFromRef('')).toBeNull()
  })
})

describe('isPackInstalledForTenant', () => {
  const connectors = [{ pack_ref: 'slack-user@1' }, { pack_ref: null }] as ApiConnector[]

  it('matches pack_id against connector pack_ref', () => {
    expect(isPackInstalledForTenant(connectors, 'slack-user')).toBe(true)
    expect(isPackInstalledForTenant(connectors, 'github-user')).toBe(false)
  })
})
