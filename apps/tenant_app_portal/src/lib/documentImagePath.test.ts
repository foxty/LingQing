import { describe, expect, it } from 'vitest'
import { documentImageApiPath, isDocumentImageSrc } from './documentImagePath'

const HASH = 'a'.repeat(64)

describe('documentImageApiPath', () => {
  it('accepts tenant document image paths', () => {
    expect(documentImageApiPath(`/documents/1/images/${HASH}.png`)).toBe(
      `/documents/1/images/${HASH}.png`,
    )
    expect(documentImageApiPath(`/api/documents/14/images/${HASH}.jpeg`)).toBe(
      `/documents/14/images/${HASH}.jpeg`,
    )
  })

  it('rejects other image urls', () => {
    expect(documentImageApiPath('https://cdn.example.com/logo.png')).toBeNull()
    expect(documentImageApiPath('/static/charts/plot.png')).toBeNull()
    expect(documentImageApiPath(`/documents/1/images/not-a-hash.png`)).toBeNull()
  })

  it('isDocumentImageSrc mirrors path detection', () => {
    expect(isDocumentImageSrc(`/documents/1/images/${HASH}.png`)).toBe(true)
    expect(isDocumentImageSrc('https://cdn.example.com/x.png')).toBe(false)
  })
})
