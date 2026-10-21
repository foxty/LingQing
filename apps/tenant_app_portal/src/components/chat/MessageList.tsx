import { Message } from '@/types'
import HumanMessage from './HumanMessage'
import AiTurnMessage from './AiTurnMessage'
import { AiTurn, buildMessageRenderItems, resolvePositiveAgentId, resolveTurnAgentId } from '@/lib/chatTurns'
import { useHitlStatusMap } from '@/hooks/useHitlStatusMap'

interface MessageListProps {
  messages: Message[]
  threadId?: string
  streamingTurn?: AiTurn | null
  streamingAgentId?: number | null
  currentUserId?: number
  userNameById?: Map<number, string>
  agentNameById?: Map<number, string>
  onHitlApprovedContinue?: (proposalId: string) => void | Promise<void>
  onHitlRejected?: (proposalId: string) => void | Promise<void>
  fallbackAgentId?: number
}

function agentLabelForTurn(
  turn: AiTurn,
  agentNameById?: Map<number, string>,
  fallbackAgentId?: number
): string | undefined {
  const id = resolveTurnAgentId(turn) ?? resolvePositiveAgentId(fallbackAgentId)
  if (id == null) {
    return undefined
  }
  return agentNameById?.get(id) ?? `#${id}`
}

export default function MessageList({
  messages,
  threadId,
  streamingTurn,
  streamingAgentId,
  currentUserId,
  userNameById,
  agentNameById,
  onHitlApprovedContinue,
  onHitlRejected,
  fallbackAgentId,
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
              <HumanMessage
                message={item.message}
                currentUserId={currentUserId}
                userNameById={userNameById}
              />
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
                agentDisplayName={agentLabelForTurn(item.turn, agentNameById, fallbackAgentId)}
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
          agentDisplayName={agentLabelForTurn(
            {
              ...streamingTurn,
              agentId: streamingAgentId ?? streamingTurn.agentId,
            },
            agentNameById,
            fallbackAgentId
          )}
          onHitlApprovedContinue={onHitlApprovedContinue}
          onHitlRejected={onHitlRejected}
        />
      )}
    </>
  )
}
