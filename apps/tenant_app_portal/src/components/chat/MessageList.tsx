import { Message } from '@/types'
import HumanMessage from './HumanMessage'
import AiTurnMessage from './AiTurnMessage'
import { AiTurn, buildMessageRenderItems } from '@/lib/chatTurns'
import { useHitlStatusMap } from '@/hooks/useHitlStatusMap'

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

  return (
    <>
      {renderItems.map((item) => {
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
      })}

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
