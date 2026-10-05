import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { useNotification } from '@/hooks/useNotification'
import { useClearMessageFeedback, useSubmitMessageFeedback } from '@/hooks/useMessageFeedback'
import type { MessageFeedback } from '@/types'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    workbench: {
      feedbackHelpful: 'Helpful',
      feedbackNotHelpful: 'Not helpful',
      feedbackCommentTitle: 'What was wrong?',
      feedbackCommentPlaceholder: 'Optional — tell us what was incorrect or unhelpful',
      feedbackSubmit: 'Submit',
      feedbackSkip: 'Skip',
      feedbackFailed: 'Failed to save feedback',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    workbench: {
      feedbackHelpful: '有帮助',
      feedbackNotHelpful: '无帮助',
      feedbackCommentTitle: '哪里不对？',
      feedbackCommentPlaceholder: '可选 — 说明错误或不足之处',
      feedbackSubmit: '提交',
      feedbackSkip: '跳过',
      feedbackFailed: '保存反馈失败',
    },
  },
  true,
  true
)

interface MessageFeedbackButtonsProps {
  threadId?: string
  messageId?: string
  feedback?: MessageFeedback
  onFeedbackChange?: (feedback: MessageFeedback | undefined) => void
}

export default function MessageFeedbackButtons({
  threadId,
  messageId,
  feedback,
  onFeedbackChange,
}: MessageFeedbackButtonsProps) {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const [commentOpen, setCommentOpen] = useState(false)
  const [comment, setComment] = useState('')

  const submitMutation = useSubmitMessageFeedback(threadId, (result) => {
    onFeedbackChange?.(result)
  })
  const clearMutation = useClearMessageFeedback(threadId, () => {
    onFeedbackChange?.(undefined)
  })

  if (!threadId || !messageId) {
    return null
  }

  const handleError = () => {
    showError(t('workbench.feedbackFailed'))
  }

  const submitRating = async (rating: 'positive' | 'negative', optionalComment?: string) => {
    try {
      if (feedback?.rating === rating && !optionalComment) {
        await clearMutation.mutateAsync(messageId)
        return
      }
      await submitMutation.mutateAsync({
        messageId,
        rating,
        comment: optionalComment,
      })
    } catch {
      handleError()
    }
  }

  const handlePositive = () => {
    void submitRating('positive')
  }

  const handleNegative = () => {
    if (feedback?.rating === 'negative') {
      void submitRating('negative')
      return
    }
    setComment(feedback?.comment || '')
    setCommentOpen(true)
  }

  const handleCommentSubmit = () => {
    setCommentOpen(false)
    void submitRating('negative', comment.trim() || undefined)
  }

  const isPending = submitMutation.isPending || clearMutation.isPending

  return (
    <>
      <div className="inline-flex items-center gap-0.5">
        <button
          type="button"
          disabled={isPending}
          onClick={handlePositive}
          className={`inline-flex h-6 w-6 items-center justify-center rounded-sm transition-colors hover:bg-secondary ${
            feedback?.rating === 'positive'
              ? 'text-primary'
              : 'text-muted-foreground hover:text-foreground'
          }`}
          title={t('workbench.feedbackHelpful')}
          aria-label={t('workbench.feedbackHelpful')}
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={handleNegative}
          className={`inline-flex h-6 w-6 items-center justify-center rounded-sm transition-colors hover:bg-secondary ${
            feedback?.rating === 'negative'
              ? 'text-destructive'
              : 'text-muted-foreground hover:text-foreground'
          }`}
          title={t('workbench.feedbackNotHelpful')}
          aria-label={t('workbench.feedbackNotHelpful')}
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </button>
      </div>

      <Dialog open={commentOpen} onOpenChange={setCommentOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('workbench.feedbackCommentTitle')}</DialogTitle>
          </DialogHeader>
          <Textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder={t('workbench.feedbackCommentPlaceholder')}
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCommentOpen(false)}>
              {t('workbench.feedbackSkip')}
            </Button>
            <Button onClick={handleCommentSubmit}>{t('workbench.feedbackSubmit')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
