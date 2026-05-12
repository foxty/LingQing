import { vi } from 'vitest'

vi.mock('@/i18n/config', () => ({
  default: {
    t: (key: string) => key,
    language: 'en',
  },
}))
