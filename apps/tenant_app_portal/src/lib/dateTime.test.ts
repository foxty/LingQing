import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  calendarDateKey,
  formatChatTimestamp,
  formatInstant,
  resolveTimeZone,
} from '@/lib/dateTime'

/** 2024-06-15 12:30:00 UTC */
const SAMPLE_ISO = '2024-06-15T12:30:00.000Z'

describe('resolveTimeZone', () => {
  it('returns trimmed valid IANA zone', () => {
    expect(resolveTimeZone('  Asia/Shanghai  ')).toBe('Asia/Shanghai')
  })

  it('falls back when zone is invalid', () => {
    const fallback = resolveTimeZone(null)
    expect(fallback).toBeTruthy()
    expect(resolveTimeZone('Not/A_Zone')).toBe(fallback)
  })
})

describe('calendarDateKey', () => {
  it('maps UTC instant to calendar date in zone', () => {
    const date = new Date('2024-06-15T20:00:00.000Z')
    expect(calendarDateKey(date, 'Asia/Shanghai')).toBe('2024-06-16')
    expect(calendarDateKey(date, 'America/New_York')).toBe('2024-06-15')
  })
})

describe('formatInstant', () => {
  it('formats ymd preset with fixed zone', () => {
    const out = formatInstant(SAMPLE_ISO, {
      formatId: 'ymd',
      timeZone: 'UTC',
      locale: 'en-US',
      precision: 'datetime',
    })
    expect(out).toBe('2024-06-15')
  })

  it('formats ymd_hms_24 with fixed zone', () => {
    const out = formatInstant(SAMPLE_ISO, {
      formatId: 'ymd_hms_24',
      timeZone: 'UTC',
      locale: 'en-US',
      precision: 'datetime',
    })
    expect(out).toMatch(/^2024-06-15 \d{2}:\d{2}:\d{2}$/)
    expect(out).toContain('12:30:00')
  })

  it('respects precision date for locale format', () => {
    const out = formatInstant(SAMPLE_ISO, {
      formatId: 'locale',
      timeZone: 'UTC',
      locale: 'en-US',
      precision: 'date',
    })
    expect(out).toMatch(/06\/15\/2024|6\/15\/24|2024/)
  })

  it('returns fallback for invalid input', () => {
    expect(formatInstant('not-a-date', { fallback: 'n/a' })).toBe('n/a')
  })
})

describe('formatChatTimestamp', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-06-15T15:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows time-only for today in zone', () => {
    const sameDay = '2024-06-15T12:30:00.000Z'
    const out = formatChatTimestamp(sameDay, {
      timeZone: 'UTC',
      formatId: 'ymd_hms_24',
      locale: 'en-US',
    })
    expect(out).not.toContain('2024-06-15')
    expect(out).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('shows full datetime when not today in zone', () => {
    const otherDay = '2024-06-10T12:30:00.000Z'
    const out = formatChatTimestamp(otherDay, {
      timeZone: 'UTC',
      formatId: 'ymd_hms_24',
      locale: 'en-US',
    })
    expect(out).toContain('2024-06-10')
  })
})
