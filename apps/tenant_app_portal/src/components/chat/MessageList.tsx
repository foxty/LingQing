import type { ReactNode } from 'react'
import { Message } from '@/types'
import HumanMessage from './HumanMessage'
import AiTurnMessage from './AiTurnMessage'
import { AiTurn, buildMessageRenderItems, type MessageRenderItem } from '@/lib/chatTurns'
import { useHitlStatusMap } from '@/hooks/useHitlStatusMap'
import { TurnGroup } from '@/components/chat/TurnGroup'

interface MessageListProps {
  messages: Message[]
  threadId?: string
  streamingTurn?: AiTurn | null
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
}

export default function MessageList({
  messages,
  threadId,
  streamingTurn,
  onHitlApprovedContinue,
  onHitlRejected,
}: MessageListProps) {
  const { data: hitlStatusMap } = useHitlStatusMap(messages)
  const renderItems = buildMessageRenderItems(messages, hitlStatusMap)
  const activeTurnKey =
    [...renderItems]
      .reverse()
      .find((item) => item.type === 'ai-turn' && item.turn.hasPendingApproval)?.key || null

  const renderItem = (item: MessageRenderItem) => {
    if (item.type === 'human') {
      return (
        <div key={item.key} data-message-key={item.key}>
          <HumanMessage message={item.message} />
        </div>
      )
    }
    if (item.type === 'ai-turn') {
      return (
        <div key={item.key} data-message-key={item.key}>
          <AiTurnMessage
            turn={item.turn}
            threadId={threadId}
            defaultProcessOpen={item.key === activeTurnKey}
            onHitlApprovedContinue={onHitlApprovedContinue}
            onHitlRejected={onHitlRejected}
          />
        </div>
      )
    }
    return null
  }

  const groupedNodes: ReactNode[] = []
  let index = 0
  let turnGroupIndex = 0
  while (index < renderItems.length) {
    const item = renderItems[index]
    if (item.type === 'human') {
      const groupItems: MessageRenderItem[] = [item]
      index += 1
      while (index < renderItems.length && renderItems[index].type === 'ai-turn') {
        groupItems.push(renderItems[index])
        index += 1
      }
      const groupKey = `turn-group-${turnGroupIndex}-${item.key}`
      turnGroupIndex += 1
      groupedNodes.push(
        <TurnGroup key={groupKey}>{groupItems.map((groupItem) => renderItem(groupItem))}</TurnGroup>
      )
      continue
    }
    groupedNodes.push(renderItem(item))
    index += 1
  }

  return (
    <>
      {groupedNodes}

      {streamingTurn && (
        <AiTurnMessage
          key="streaming-turn"
          turn={streamingTurn}
          threadId={threadId}
          defaultProcessOpen
          isStreaming
          onHitlApprovedContinue={onHitlApprovedContinue}
          onHitlRejected={onHitlRejected}
        />
      )}
    </>
  )
}
