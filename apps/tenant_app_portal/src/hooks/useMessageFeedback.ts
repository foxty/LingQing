import { useMutation } from '@tanstack/react-query'
import { clearMessageFeedback, submitMessageFeedback } from '@/lib/feedbackApi'
import type { MessageFeedback } from '@/types'

export function useSubmitMessageFeedback(
  threadId: string | undefined,
  onSuccess?: (feedback: MessageFeedback) => void
) {
  return useMutation({
    mutationFn: async ({
      messageId,
      rating,
      comment,
    }: {
      messageId: string
      rating: 'positive' | 'negative'
      comment?: string
    }) => {
      if (!threadId) {
        throw new Error('Thread ID is required')
      }
      return submitMessageFeedback(threadId, messageId, { rating, comment })
    },
    onSuccess,
  })
}

export function useClearMessageFeedback(threadId: string | undefined, onSuccess?: () => void) {
  return useMutation({
    mutationFn: async (messageId: string) => {
      if (!threadId) {
        throw new Error('Thread ID is required')
      }
      await clearMessageFeedback(threadId, messageId)
    },
    onSuccess,
  })
}
