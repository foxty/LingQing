import type { HitlPayload, Message } from '@/types'
import { getHitlApproval } from '@/lib/hitlApi'

export type HitlRecordStatus = NonNullable<HitlPayload['status']>
export type HitlStatusMap = Record<string, HitlRecordStatus>

export function collectHitlProposalIds(messages: Message[]): string[] {
  const ids = new Set<string>()
  for (const message of messages) {
    const proposalId = message.additional_kwargs?.hitl?.proposal_id
    if (proposalId) {
      ids.add(proposalId)
    }
  }
  return [...ids]
}

export async function fetchHitlStatusMap(proposalIds: string[]): Promise<HitlStatusMap> {
  const entries = await Promise.all(
    proposalIds.map(async (proposalId) => {
      try {
        const approval = await getHitlApproval(proposalId)
        return [proposalId, approval.status] as const
      } catch {
        return null
      }
    })
  )

  return Object.fromEntries(
    entries.filter((entry): entry is readonly [string, HitlRecordStatus] => entry !== null)
  )
}

export function isHitlApprovalOpen(
  status: HitlRecordStatus | undefined
): boolean {
  return !status || status === 'pending' || status === 'approved'
}

export function resolveHitlToolStatus(
  hitl: HitlPayload | undefined,
  resultMessage: Message | undefined,
  statusFromRecord?: HitlRecordStatus
): 'completed' | 'hitl_pending' | undefined {
  const resultHitl = resultMessage?.additional_kwargs?.hitl
  if (resultHitl?.type === 'approval_result') {
    return 'completed'
  }

  const proposalId = hitl?.proposal_id || resultHitl?.proposal_id
  if (!proposalId) {
    return undefined
  }

  const status = statusFromRecord || hitl?.status || resultHitl?.status
  if (isHitlApprovalOpen(status)) {
    return 'hitl_pending'
  }

  return 'completed'
}
