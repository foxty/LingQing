import { describe, expect, it } from 'vitest'
import {
  TIMEZONE_QUICK_PICKS,
  filterIanaTimeZones,
  isValidIanaTimeZone,
} from '@/lib/timezones'

const SAMPLE_ZONES = [
  'UTC',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Europe/Berlin',
  'America/New_York',
  'Pacific/Auckland',
]

describe('isValidIanaTimeZone', () => {
  it('accepts known zones', () => {
    expect(isValidIanaTimeZone('Asia/Shanghai')).toBe(true)
    expect(isValidIanaTimeZone('UTC')).toBe(true)
  })

  it('rejects empty and invalid', () => {
    expect(isValidIanaTimeZone('')).toBe(false)
    expect(isValidIanaTimeZone('   ')).toBe(false)
    expect(isValidIanaTimeZone('Invalid/Zone')).toBe(false)
  })
})

describe('filterIanaTimeZones', () => {
  it('returns quick picks when query is empty', () => {
    const result = filterIanaTimeZones('', 'Asia/Shanghai', SAMPLE_ZONES)
    for (const pick of TIMEZONE_QUICK_PICKS) {
      if (SAMPLE_ZONES.includes(pick)) {
        expect(result).toContain(pick)
      }
    }
    expect(result).toContain('Asia/Shanghai')
  })

  it('filters by substring and caps results', () => {
    const manyAsia = Array.from({ length: 100 }, (_, i) => `Asia/City${i}`)
    const result = filterIanaTimeZones('asia', undefined, manyAsia)
    expect(result.length).toBeLessThanOrEqual(80)
    expect(result.every((z) => z.toLowerCase().includes('asia'))).toBe(true)
  })
})
