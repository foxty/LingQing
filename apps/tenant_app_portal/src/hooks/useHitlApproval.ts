import { useCallback, useState } from 'react'
import {
  approveHitlApproval,
  getHitlApproval,
  rejectHitlApproval,
  type HitlApprovalActionResponse,
} from '@/lib/hitlApi'

export function useHitlApproval() {
  const [loading, setLoading] = useState(false)

  const approve = useCallback(
    async (
      proposalId: string,
      version: number,
      comment?: string
    ): Promise<HitlApprovalActionResponse> => {
      setLoading(true)
      try {
        return await approveHitlApproval(proposalId, { version, comment })
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const reject = useCallback(
    async (
      proposalId: string,
      version: number,
      comment?: string
    ): Promise<HitlApprovalActionResponse> => {
      setLoading(true)
      try {
        return await rejectHitlApproval(proposalId, { version, comment })
      } finally {
        setLoading(false)
      }
    },
    []
  )

  const refresh = useCallback(async (proposalId: string) => {
    setLoading(true)
    try {
      return await getHitlApproval(proposalId)
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    loading,
    approve,
    reject,
    refresh,
  }
}
