import type { SecretFieldBinding, SecretFieldMode } from '@/lib/sensitiveCredential'
import { useCallback, useEffect, useMemo, useState } from 'react'

export type SecretCredentialFieldHandle = SecretFieldBinding & {
  startEdit: () => void
  cancelEdit: () => void
  reset: () => void
  setDraft: (value: string) => void
}

export function useSecretCredentialField(
  mode: SecretFieldMode,
  stored: boolean,
  resetKey: string | number | boolean = false,
): SecretCredentialFieldHandle {
  const [editing, setEditing] = useState(mode === 'create' || !stored)
  const [draft, setDraft] = useState('')

  const reset = useCallback(() => {
    setEditing(mode === 'create' || !stored)
    setDraft('')
  }, [mode, stored])

  useEffect(() => {
    reset()
  }, [reset, resetKey])

  const startEdit = useCallback(() => {
    setEditing(true)
    setDraft('')
  }, [])

  const cancelEdit = useCallback(() => {
    setEditing(false)
    setDraft('')
  }, [])

  return useMemo(
    () => ({
      mode,
      stored,
      editing,
      draft,
      setDraft,
      startEdit,
      cancelEdit,
      reset,
    }),
    [mode, stored, editing, draft, startEdit, cancelEdit, reset],
  )
}