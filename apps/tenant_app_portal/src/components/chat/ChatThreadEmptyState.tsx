import './workbenchChatI18n'
import { Button } from '@/components/ui/button'
import type { ThreadLoadError } from '@/hooks/useChatHistory'
import { Bot, Loader2, LockKeyhole } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface ChatThreadEmptyStateProps {
  threadId?: string
  isLoadingHistory: boolean
  threadLoadError: ThreadLoadError | null
  agentAccessRevoked: boolean
  exampleQuestions: string[]
  inputDisabled: boolean
  onSendExample: (question: string) => void
}

export default function ChatThreadEmptyState({
  threadId,
  isLoadingHistory,
  threadLoadError,
  agentAccessRevoked,
  exampleQuestions,
  inputDisabled,
  onSendExample,
}: ChatThreadEmptyStateProps) {
  const { t } = useTranslation()

  const content = (() => {
    if (isLoadingHistory && threadId) {
      return {
        icon: <Loader2 className="mb-4 h-16 w-16 animate-spin text-muted-foreground" />,
        title: t('common.loading'),
        description: null as string | null,
      }
    }

    if (threadLoadError === 'forbidden') {
      return {
        icon: <LockKeyhole className="mb-4 h-16 w-16 text-muted-foreground" />,
        title: t('workbench.threadNotAccessible'),
        description: t('workbench.threadNotAccessibleDesc'),
      }
    }

    if (threadLoadError === 'not_found') {
      return {
        icon: <LockKeyhole className="mb-4 h-16 w-16 text-muted-foreground" />,
        title: t('workbench.threadNotFound'),
        description: t('workbench.threadNotFoundDesc'),
      }
    }

    if (threadLoadError === 'unknown') {
      return {
        icon: <Bot className="mb-4 h-16 w-16 text-muted-foreground" />,
        title: t('workbench.threadLoadFailed'),
        description: t('workbench.threadLoadFailedDesc'),
      }
    }

    if (agentAccessRevoked) {
      return {
        icon: <LockKeyhole className="mb-4 h-16 w-16 text-muted-foreground" />,
        title: t('workbench.agentAccessRevoked'),
        description: t('workbench.agentAccessRevokedDesc'),
      }
    }

    return {
      icon: <Bot className="mb-4 h-16 w-16 text-muted-foreground" />,
      title: t('workbench.startChat'),
      description: t('workbench.startChatDesc'),
    }
  })()

  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      {content.icon}
      <h2 className="mb-2 text-xl font-semibold">{content.title}</h2>
      {content.description ? (
        <p className="max-w-md text-muted-foreground">{content.description}</p>
      ) : null}
      {!threadLoadError && !agentAccessRevoked && exampleQuestions.length > 0 ? (
        <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
          {exampleQuestions.map((question) => (
            <Button
              key={question}
              type="button"
              variant="outline"
              size="sm"
              className="h-auto whitespace-normal text-left"
              disabled={inputDisabled}
              onClick={() => onSendExample(question)}
            >
              {question}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
