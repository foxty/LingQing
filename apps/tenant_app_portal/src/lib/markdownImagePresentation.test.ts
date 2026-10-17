import { describe, expect, it } from 'vitest'
import {
  markdownImageExpandedClassName,
  markdownImageInlineClassName,
  markdownImagePlaceholderClassName,
} from '@/lib/markdownImagePresentation'

describe('markdownImagePresentation', () => {
  it('applies unified inline classes for auth-backed markdown images', () => {
    const inline = markdownImageInlineClassName()
    expect(inline).toContain('65vh')
    expect(inline).toContain('w-full')
    expect(inline).toContain('cursor-zoom-in')
  })

  it('merges optional className', () => {
    expect(markdownImageInlineClassName('extra-class')).toContain('extra-class')
  })

  it('placeholder and expanded classes are stable', () => {
    expect(markdownImagePlaceholderClassName()).toContain('animate-pulse')
    expect(markdownImageExpandedClassName()).toContain('88vh')
  })
})
