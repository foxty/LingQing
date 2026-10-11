import { describe, expect, it } from 'vitest'
import { isStreamTransportError } from '@/lib/streamErrors'

describe('isStreamTransportError', () => {
  it('detects common browser transport failures', () => {
    expect(isStreamTransportError('network error')).toBe(true)
    expect(isStreamTransportError('Failed to fetch')).toBe(true)
    expect(isStreamTransportError('NetworkError when attempting to fetch resource.')).toBe(true)
  })

  it('treats backend error messages as non-transport', () => {
    expect(isStreamTransportError('Request timed out. Please try again.')).toBe(false)
    expect(isStreamTransportError('Rate limit exceeded. Please try again in a moment.')).toBe(false)
  })
})
