import { AiTurn, TurnProcessItem } from '@/lib/chatTurns'
import { SessionMetrics } from '@/types'

export const AI_TURN_BUBBLE_WIDTH = 'w-full min-w-[min(92%,18rem)] max-w-[min(92%,42rem)]'

type ToolProcessItem = Extract<TurnProcessItem, { type: 'tool' }>
type ApprovalProcessItem = Extract<TurnProcessItem, { type: 'approval' }>
type MessageProcessItem = Extract<TurnProcessItem, { type: 'message' }>

export type ProcessRenderGroup =
  | { type: 'tools'; items: ToolProcessItem[]; keys: string[] }
  | { type: 'approval'; item: ApprovalProcessItem; index: number }
  | { type: 'message'; item: MessageProcessItem; index: number }

export function groupProcessItems(processItems: TurnProcessItem[]): ProcessRenderGroup[] {
  const groups: ProcessRenderGroup[] = []
  let toolBuffer: { items: ToolProcessItem[]; keys: string[] } | null = null

  const flushTools = () => {
    if (toolBuffer && toolBuffer.items.length > 0) {
      groups.push({ type: 'tools', items: toolBuffer.items, keys: toolBuffer.keys })
      toolBuffer = null
    }
  }

  processItems.forEach((item, index) => {
    if (item.type === 'tool') {
      if (item.toolItem.hitl?.proposal_id) {
        return
      }
      if (!toolBuffer) {
        toolBuffer = { items: [], keys: [] }
      }
      toolBuffer.items.push(item)
      toolBuffer.keys.push(item.key || `tool-${index}`)
      return
    }

    flushTools()
    if (item.type === 'approval') {
      groups.push({ type: 'approval', item, index })
    } else if (item.type === 'message') {
      groups.push({ type: 'message', item, index })
    }
  })

  flushTools()
  return groups
}

export function isSessionMetrics(metrics: unknown): metrics is SessionMetrics {
  return (
    typeof metrics === 'object' &&
    metrics !== null &&
    'session_id' in metrics &&
    'total_tokens' in metrics
  )
}

function countTimelineToolItems(turn: AiTurn): number {
  return turn.toolItems.filter((item) => !item.hitl?.proposal_id).length
}

export function getProcessBadges(turn: AiTurn, t: (key: string) => string): string[] {
  const badges: string[] = []
  const toolCount = countTimelineToolItems(turn)

  if (toolCount > 0) {
    badges.push(`${t('workbench.toolCalls')} ${toolCount}`)
  }
  if (turn.approvals.length > 0) {
    badges.push(`${t('workbench.toolApprovals')} ${turn.approvals.length}`)
  }
  if (turn.processMessages.length > 0) {
    badges.push(`${t('workbench.toolInterimResponses')} ${turn.processMessages.length}`)
  }

  return badges
}