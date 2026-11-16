import { describe, expect, it } from 'vitest'
import {
  DEFAULT_DATETIME_FORMAT,
  DATETIME_FORMAT_IDS,
  isDateTimeFormatId,
  resolveDateTimeFormat,
} from '@/lib/datetimeFormats'

describe('datetimeFormats', () => {
  it('exposes stable format id list', () => {
    expect([...DATETIME_FORMAT_IDS].sort()).toEqual([
      'locale',
      'mdy_hm_12',
      'ymd',
      'ymd_hms_12',
      'ymd_hms_24',
    ])
  })

  it('isDateTimeFormatId recognizes allowed values', () => {
    expect(isDateTimeFormatId('ymd')).toBe(true)
    expect(isDateTimeFormatId('locale')).toBe(true)
    expect(isDateTimeFormatId('iso')).toBe(false)
  })

  it('resolveDateTimeFormat falls back for missing or invalid', () => {
    expect(resolveDateTimeFormat(undefined)).toBe(DEFAULT_DATETIME_FORMAT)
    expect(resolveDateTimeFormat(null)).toBe(DEFAULT_DATETIME_FORMAT)
    expect(resolveDateTimeFormat('unknown')).toBe(DEFAULT_DATETIME_FORMAT)
    expect(resolveDateTimeFormat('ymd_hms_12')).toBe('ymd_hms_12')
  })
})
