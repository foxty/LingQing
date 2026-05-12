import { HitlPayload, Message, SessionMetrics } from '@/types'
import i18n from '@/i18n/config'
import {
  isHitlApprovalOpen,
  resolveHitlToolStatus,
  type HitlStatusMap,
} from '@/lib/hitlStatus'

export type ToolCallProgressStatus = 'running' | 'completed' | 'hitl_pending'

export interface StreamingToolCallState {
  id: string
  name: string
  args?: Record<string, any>
  status: ToolCallProgressStatus
  startedAt?: string
  endedAt?: string
}

export interface TurnToolCallItem {
  toolCall: {
    id: string
    name: string
    args: Record<string, any>
  }
  resultMessage?: Message
  status?: ToolCallProgressStatus
  hitl?: HitlPayload
}

export type TurnProcessItem =
  | {
      type: 'tool'
      key: string
      timestamp?: string
      order: number
      toolItem: TurnToolCallItem
    }
  | {
      type: 'approval'
      key: string
      timestamp?: string
      order: number
      approval: HitlPayload
    }
  | {
      type: 'message'
      key: string
      timestamp?: string
      order: number
      message: Message
    }

export interface AiTurn {
  id: string
  sessionId?: string
  finalMessage: Message
  metrics?: SessionMetrics
  processMessages: Message[]
  toolItems: TurnToolCallItem[]
  approvals: HitlPayload[]
  processItems: TurnProcessItem[]
  timestamp?: string
  hasPendingApproval: boolean
}

export type MessageRenderItem =
  | { type: 'human'; key: string; message: Message }
  | { type: 'ai-turn'; key: string; turn: AiTurn }

function humanMessageKey(message: Message): string {
  const timestamp = message.timestamp ?? 'unknown'
  const contentPrefix = message.content.slice(0, 48)
  return `human-${timestamp}-${contentPrefix}`
}

function aiTurnKey(turn: AiTurn): string {
  return `turn-${turn.id}`
}

function applyHitlStatusMap(
  processItems: TurnProcessItem[],
  hitlStatusMap?: HitlStatusMap
): void {
  if (!hitlStatusMap) {
    return
  }

  for (const item of processItems) {
    if (item.type === 'approval') {
      const status = hitlStatusMap[item.approval.proposal_id]
      if (status) {
        item.approval = { ...item.approval, status }
      }
      continue
    }

    if (item.type !== 'tool') {
      continue
    }

    const proposalId =
      item.toolItem.hitl?.proposal_id ||
      item.toolItem.resultMessage?.additional_kwargs?.hitl?.proposal_id
    if (!proposalId) {
      continue
    }

    item.toolItem.status = resolveHitlToolStatus(
      item.toolItem.hitl,
      item.toolItem.resultMessage,
      hitlStatusMap[proposalId]
    )
  }
}

function buildTurn(
  aiMessages: Message[],
  toolResultsMap: Map<string, Message>,
  turnIndex: number,
  hitlStatusMap?: HitlStatusMap
): AiTurn {
  let finalIndex = aiMessages.length - 1
  for (let index = aiMessages.length - 1; index >= 0; index -= 1) {
    if (aiMessages[index].content && aiMessages[index].content.trim().length > 0) {
      finalIndex = index
      break
    }
  }

  const finalMessage = aiMessages[finalIndex]
  const processMessages = aiMessages.filter(
    (msg, idx) => idx !== finalIndex && !msg.additional_kwargs?.hitl?.proposal_id
  )

  const processItems: TurnProcessItem[] = []
  const approvalItemIndex = new Map<string, number>()
  let processOrder = 0

  aiMessages.forEach((aiMsg, aiMessageIndex) => {
    const rawHitl = aiMsg.additional_kwargs?.hitl
    const normalizedHitl: HitlPayload | undefined = rawHitl?.proposal_id
      ? {
          ...rawHitl,
          tool_name: rawHitl.tool_name || aiMsg.additional_kwargs?.tool_name || aiMsg.tool_calls?.[0]?.name,
        }
      : undefined
    const hasHitl = !!normalizedHitl?.proposal_id

    // Intercepted HITL prompt is represented by approval card; skip duplicate process message.
    if (aiMessageIndex !== finalIndex && aiMsg.content?.trim() && !hasHitl) {
      processItems.push({
        type: 'message',
        key: `message-${turnIndex}-${processOrder}`,
        timestamp: aiMsg.timestamp,
        order: processOrder,
        message: aiMsg,
      })
      processOrder += 1
    }

    aiMsg.tool_calls?.forEach((toolCall) => {
      if (!toolCall.id) {
        return
      }

      const existingToolItem = processItems.find(
        (item) => item.type === 'tool' && item.toolItem.toolCall.id === toolCall.id
      )
      if (existingToolItem) {
        return
      }

      const resultMessage = toolResultsMap.get(toolCall.id)
      const toolItem: TurnToolCallItem = {
        toolCall: {
          id: toolCall.id,
          name: toolCall.name,
          args: toolCall.args || {},
        },
        resultMessage,
        hitl: hasHitl ? normalizedHitl : undefined,
        status: hasHitl
          ? resolveHitlToolStatus(
              normalizedHitl,
              resultMessage,
              normalizedHitl?.proposal_id
                ? hitlStatusMap?.[normalizedHitl.proposal_id]
                : undefined
            )
          : undefined,
      }

      processItems.push({
        type: 'tool',
        key: `tool-${toolCall.id}`,
        timestamp: toolItem.resultMessage?.timestamp || aiMsg.timestamp,
        order: processOrder,
        toolItem,
      })
      processOrder += 1
    })

    if (normalizedHitl?.proposal_id) {
      const existingIndex = approvalItemIndex.get(normalizedHitl.proposal_id)

      if (existingIndex !== undefined) {
        processItems.splice(existingIndex, 1)
        approvalItemIndex.delete(normalizedHitl.proposal_id)
      }

      processItems.push({
        type: 'approval',
        key: `approval-${normalizedHitl.proposal_id}`,
        timestamp: aiMsg.timestamp,
        order: processOrder,
        approval: normalizedHitl,
      })
      approvalItemIndex.set(normalizedHitl.proposal_id, processItems.length - 1)
      processOrder += 1
    }
  })

  // Backfill HITL metadata when tool_call and hitl are emitted in different AI messages.
  // Match by tool_name for all approvals so historical replay stays consistent.
  const approvalsByTool = new Map<string, HitlPayload[]>()
  for (const item of processItems) {
    if (item.type !== 'approval') {
      continue
    }
    if (!item.approval.tool_name) {
      continue
    }
    const queue = approvalsByTool.get(item.approval.tool_name) ?? []
    queue.push(item.approval)
    approvalsByTool.set(item.approval.tool_name, queue)
  }

  for (const item of processItems) {
    if (item.type !== 'tool' || item.toolItem.hitl?.proposal_id) {
      continue
    }
    const queue = approvalsByTool.get(item.toolItem.toolCall.name)
    if (queue && queue.length > 0) {
      const hitl = queue.shift()
      item.toolItem.hitl = hitl
      item.toolItem.status = resolveHitlToolStatus(
        hitl,
        item.toolItem.resultMessage,
        hitl?.proposal_id ? hitlStatusMap?.[hitl.proposal_id] : undefined
      )
    }
  }

  applyHitlStatusMap(processItems, hitlStatusMap)

  // Normalize tool status for UI rendering.
  for (const item of processItems) {
    if (item.type !== 'tool') {
      continue
    }
    if (!item.toolItem.status && item.toolItem.resultMessage) {
      item.toolItem.status = 'completed'
    }
  }

  const parseTimestamp = (value?: string): number | null => {
    if (!value) {
      return null
    }

    const parsed = Date.parse(value)
    return Number.isNaN(parsed) ? null : parsed
  }

  processItems.sort((left, right) => {
    const leftTime = parseTimestamp(left.timestamp)
    const rightTime = parseTimestamp(right.timestamp)

    if (leftTime !== null && rightTime !== null && leftTime !== rightTime) {
      return leftTime - rightTime
    }

    if (leftTime !== null && rightTime === null) {
      return -1
    }

    if (leftTime === null && rightTime !== null) {
      return 1
    }

    return left.order - right.order
  })

  const approvals = processItems
    .filter(
      (item): item is Extract<TurnProcessItem, { type: 'approval' }> => item.type === 'approval'
    )
    .map((item) => item.approval)

  const timelineToolItems = processItems
    .filter((item): item is Extract<TurnProcessItem, { type: 'tool' }> => item.type === 'tool')
    .map((item) => item.toolItem)

  const sessionId =
    finalMessage.session_id || [...aiMessages].reverse().find((msg) => msg.session_id)?.session_id
  const timestamp = finalMessage.timestamp || aiMessages[aiMessages.length - 1]?.timestamp
  const metrics = [...aiMessages]
    .reverse()
    .find(
      (msg): msg is Message & { metrics: SessionMetrics } =>
        !!msg.metrics && 'total_tokens' in msg.metrics
    )?.metrics
  const firstToolCallId = aiMessages
    .flatMap((msg) => msg.tool_calls ?? [])
    .find((toolCall) => toolCall.id)?.id

  return {
    id:
      sessionId ||
      `turn-${timestamp ?? firstToolCallId ?? finalMessage.content.slice(0, 32)}`,
    sessionId,
    finalMessage,
    metrics,
    processMessages,
    toolItems: timelineToolItems,
    approvals,
    processItems,
    timestamp,
    hasPendingApproval: approvals.some((item) =>
      isHitlApprovalOpen(hitlStatusMap?.[item.proposal_id] || item.status)
    ),
  }
}

export function buildMessageRenderItems(
  messages: Message[],
  hitlStatusMap?: HitlStatusMap
): MessageRenderItem[] {
  const toolResultsMap = new Map<string, Message>()
  const renderItems: MessageRenderItem[] = []
  let index = 0
  let turnIndex = 0

  while (index < messages.length) {
    const message = messages[index]

    if (message.role === 'human') {
      renderItems.push({
        type: 'human',
        key: humanMessageKey(message),
        message,
      })
      index += 1
      continue
    }

    if (message.role === 'tool') {
      if (message.tool_call_id) {
        toolResultsMap.set(message.tool_call_id, message)
      }
      index += 1
      continue
    }

    if (message.role === 'system') {
      index += 1
      continue
    }

    if (message.role === 'ai') {
      const turnAiMessages: Message[] = []
      let cursor = index

      while (cursor < messages.length && messages[cursor].role !== 'human') {
        const current = messages[cursor]
        if (current.role === 'ai') {
          turnAiMessages.push(current)
        }
        if (current.role === 'tool' && current.tool_call_id) {
          toolResultsMap.set(current.tool_call_id, current)
        }
        cursor += 1
      }

      if (turnAiMessages.length > 0) {
        turnIndex += 1
        const turn = buildTurn(turnAiMessages, toolResultsMap, turnIndex, hitlStatusMap)
        renderItems.push({
          type: 'ai-turn',
          key: aiTurnKey(turn),
          turn,
        })
      }

      index = cursor
      continue
    }

    index += 1
  }

  return renderItems
}

export function buildStreamingTurn(streaming: {
  content: string
  toolCalls: StreamingToolCallState[]
}): AiTurn | null {
  const hasContent = streaming.content.trim().length > 0

  const nowIso = new Date().toISOString()
  const timestamp = streaming.toolCalls[streaming.toolCalls.length - 1]?.startedAt || nowIso

  const processItems: TurnProcessItem[] = streaming.toolCalls.map((tool, index) => ({
    type: 'tool',
    key: `stream-tool-${tool.id}`,
    timestamp: tool.endedAt || tool.startedAt || timestamp,
    order: index,
    toolItem: {
      toolCall: {
        id: tool.id,
        name: tool.name,
        args: tool.args || {},
      },
      status: tool.status,
    },
  }))

  return {
    id: 'streaming-turn',
    finalMessage: {
      role: 'ai',
      content: hasContent ? streaming.content : i18n.t('workbench.thinking'),
      timestamp: nowIso,
    },
    processMessages: [],
    toolItems: processItems
      .filter((item): item is Extract<TurnProcessItem, { type: 'tool' }> => item.type === 'tool')
      .map((item) => item.toolItem),
    approvals: [],
    processItems,
    timestamp,
    hasPendingApproval: streaming.toolCalls.some((item) => item.status === 'hitl_pending'),
  }
}
