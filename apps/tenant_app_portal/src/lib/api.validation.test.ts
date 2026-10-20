import { describe, expect, it } from 'vitest'
import {
  formatFastApiValidationDetail,
  getApiErrorMessage,
  mapFastApiValidationToFields,
  normalizeApiErrorPayload,
} from './api'

describe('FastAPI validation errors', () => {
  it('formats validation detail arrays into a user-facing message', () => {
    const detail = [
      {
        type: 'string_too_short',
        loc: ['body', 'system_prompt'],
        msg: 'String should have at least 1 character',
        input: '',
      },
    ]
    expect(formatFastApiValidationDetail(detail)).toBe('String should have at least 1 character')
    expect(normalizeApiErrorPayload({ detail }).message).toBe(
      'String should have at least 1 character'
    )
  })

  it('maps validation loc segments to form fields', () => {
    const detail = [
      {
        loc: ['body', 'system_prompt'],
        msg: 'String should have at least 1 character',
      },
      {
        loc: ['body', 'name'],
        msg: 'String should have at least 1 character',
      },
    ]
    expect(
      mapFastApiValidationToFields(detail, {
        name: 'name',
        system_prompt: 'systemPrompt',
      })
    ).toEqual({
      systemPrompt: 'String should have at least 1 character',
      name: 'String should have at least 1 character',
    })
  })

  it('reads preserved validation_errors on axios-shaped errors', () => {
    const err = {
      response: {
        data: {
          message: 'String should have at least 1 character',
          validation_errors: [
            {
              loc: ['body', 'system_prompt'],
              msg: 'String should have at least 1 character',
            },
          ],
        },
      },
    }
    expect(getApiErrorMessage(err, 'fallback')).toBe('String should have at least 1 character')
  })
})
