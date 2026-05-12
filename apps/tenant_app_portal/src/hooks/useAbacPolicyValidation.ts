import { useEffect, useState } from 'react'

import { validateExpression, type ValidateExpressionResponse } from '@/lib/abacPolicyApi'

export function useAbacPolicyValidation(expression: string, debounceMs = 300) {
  const [result, setResult] = useState<ValidateExpressionResponse | null>(null)
  const [isValidating, setIsValidating] = useState(false)

  useEffect(() => {
    if (!expression.trim()) {
      setResult(null)
      return
    }
    setIsValidating(true)
    const timer = setTimeout(async () => {
      try {
        const res = await validateExpression(expression)
        setResult(res)
      } catch {
        setResult({
          valid: false,
          errors: ['Validation request failed.'],
          human_readable: null,
        })
      } finally {
        setIsValidating(false)
      }
    }, debounceMs)
    return () => clearTimeout(timer)
  }, [expression, debounceMs])

  return { result, isValidating }
}
