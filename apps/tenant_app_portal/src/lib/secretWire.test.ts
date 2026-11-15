import { describe, expect, it } from 'vitest'
import {
  API_SECRET_PLACEHOLDER,
  isDisplayMask,
  isUnchangedSecretOnWire,
  maskSecretForDisplay,
  omitUnchangedSecretsDeep,
  shouldStripSecretLeafOnSubmit,
} from './secretWire'

const UNCHANGED_WIRE_VECTORS: [unknown, boolean][] = [
  [null, true],
  ['', true],
  ['   ', true],
  [API_SECRET_PLACEHOLDER, false],
  ['********', false],
  [maskSecretForDisplay('secretkey'), false],
  ['new-secret', false],
  ['my*pass*word', false],
]

describe('secret wire contract', () => {
  it.each(UNCHANGED_WIRE_VECTORS)('isUnchangedSecretOnWire(%j) → %s', (value, expected) => {
    expect(isUnchangedSecretOnWire(value)).toBe(expected)
  })

  it('mask round-trip', () => {
    const masked = maskSecretForDisplay('dapiabcdefghij')
    expect(masked.startsWith('da')).toBe(true)
    expect(masked.endsWith('ij')).toBe(true)
    expect(isDisplayMask(masked)).toBe(true)
    expect(isDisplayMask(API_SECRET_PLACEHOLDER)).toBe(false)
  })

  it('shouldStripSecretLeafOnSubmit', () => {
    const masked = maskSecretForDisplay('secret')
    expect(shouldStripSecretLeafOnSubmit('')).toBe(true)
    expect(shouldStripSecretLeafOnSubmit(API_SECRET_PLACEHOLDER)).toBe(true)
    expect(shouldStripSecretLeafOnSubmit('********')).toBe(true)
    expect(shouldStripSecretLeafOnSubmit(masked)).toBe(true)
    expect(shouldStripSecretLeafOnSubmit('real-secret')).toBe(false)
  })

  it('omitUnchangedSecretsDeep strips masked leaves', () => {
    const masked = maskSecretForDisplay('my-secret-key-12345')
    const input = { username: 'admin', app_secret: masked }
    expect(omitUnchangedSecretsDeep(input)).toEqual({ username: 'admin' })
  })
})
