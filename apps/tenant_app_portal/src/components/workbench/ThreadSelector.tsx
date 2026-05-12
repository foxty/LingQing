import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

i18n.addResourceBundle('en', 'translation', {
  components: {
    threadSelector: {
      newConversation: 'New conversation',
      loading: 'Loading...',
      selectConversation: 'Select a conversation',
      newThread: 'New',
      empty: 'No conversations yet',
      emptyHint: 'Start a new conversation with this agent.',
      deleteThread: 'Delete conversation',
      deleteTitle: 'Delete conversation',
      deleteDesc: 'Are you sure you want to delete "{{title}}"?',
      deleting: 'Deleting...',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    threadSelector: {
      newConversation: '新对话',
      loading: '加载中...',
      selectConversation: '选择对话',
      newThread: '新对话',
      empty: '暂无对话',
      emptyHint: '用此智能体开始一段新对话。',
      deleteThread: '删除对话',
      deleteTitle: '删除对话',
      deleteDesc: '确定要删除 “{{title}}” 吗？',
      deleting: '删除中...',
    },
  },
}, true, true)

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ChatThread } from '@/types'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'
import { ChevronDown, Loader2, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'

interface ThreadSelectorProps {
  threads: ChatThread[]
  currentThreadId: string | null
  isLoading?: boolean
  onSelectThread: (threadId: string) => void
  onCreateThread: () => void
  onDeleteThread: (threadId: string) => Promise<void>
}

export default function ThreadSelector({
  threads,
  currentThreadId,
  isLoading = false,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
}: ThreadSelectorProps) {
  const { t } = useTranslation()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [threadToDelete, setThreadToDelete] = useState<ChatThread | null>(null)
  const [isDeletingThread, setIsDeletingThread] = useState(false)

  const currentThread = useMemo(
    () => threads.find((thread) => thread.id === currentThreadId) || null,
    [threads, currentThreadId]
  )

  const getThreadTitle = (title: string | null) => title || t('components.threadSelector.newConversation')

  const formatThreadUpdatedAt = (updatedAt: string) => {
    try {
      return formatDistanceToNow(new Date(updatedAt), {
        addSuffix: true,
      })
    } catch {
      return updatedAt
    }
  }

  const handleSelectThread = (threadId: string) => {
    onSelectThread(threadId)
    setPickerOpen(false)
  }

  const handleCreateThread = () => {
    setPickerOpen(false)
    onCreateThread()
  }

  const handleDeleteThread = async () => {
    if (!threadToDelete) return

    setIsDeletingThread(true)
    try {
      await onDeleteThread(threadToDelete.id)
      setThreadToDelete(null)
    } catch (error) {
      console.error('Failed to delete thread:', error)
    } finally {
      setIsDeletingThread(false)
    }
  }

  const triggerLabel = isLoading
    ? t('components.threadSelector.loading')
    : currentThread
      ? getThreadTitle(currentThread.title)
      : t('components.threadSelector.selectConversation')

  return (
    <>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'flex h-9 min-w-0 flex-1 items-center justify-between rounded-md border border-input bg-background px-3 text-left text-sm',
                'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
              )}
              aria-label={t('components.threadSelector.selectConversation')}
            >
              <span className="min-w-0 flex-1 truncate">{triggerLabel}</span>
              <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 p-1">
            {isLoading ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                {t('components.threadSelector.loading')}
              </p>
            ) : threads.length === 0 ? (
              <div className="px-3 py-6 text-center">
                <p className="text-sm font-medium">{t('components.threadSelector.empty')}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('components.threadSelector.emptyHint')}</p>
              </div>
            ) : (
              <ul className="max-h-72 overflow-y-auto">
                {threads.map((thread) => {
                  const selected = thread.id === currentThreadId
                  return (
                    <li key={thread.id}>
                      <div
                        className={cn(
                          'flex items-center gap-1 rounded-md pr-1',
                          selected ? 'bg-accent' : 'hover:bg-accent'
                        )}
                      >
                        <button
                          type="button"
                          className="min-w-0 flex-1 rounded-md px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          onClick={() => handleSelectThread(thread.id)}
                        >
                          <p className="truncate text-sm">{getThreadTitle(thread.title)}</p>
                          <p className="text-xs text-muted-foreground">
                            {formatThreadUpdatedAt(thread.updatedAt)}
                          </p>
                        </button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0"
                          title={t('components.threadSelector.deleteThread')}
                          aria-label={t('components.threadSelector.deleteThread')}
                          onPointerDown={(event) => event.preventDefault()}
                          onClick={() => {
                            setPickerOpen(false)
                            setThreadToDelete(thread)
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </PopoverContent>
        </Popover>
        <Button
          variant="outline"
          size="sm"
          onClick={handleCreateThread}
          title={t('components.threadSelector.newConversation')}
          className="h-9 shrink-0 px-3"
        >
          <Plus className="h-4 w-4" />
          <span className="ml-1.5">{t('components.threadSelector.newThread')}</span>
        </Button>
      </div>

      <AlertDialog
        open={threadToDelete != null}
        onOpenChange={(open) => {
          if (!open && !isDeletingThread) {
            setThreadToDelete(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('components.threadSelector.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {threadToDelete
                ? t('components.threadSelector.deleteDesc', { title: getThreadTitle(threadToDelete.title) })
                : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeletingThread}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteThread}
              disabled={isDeletingThread}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeletingThread ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('components.threadSelector.deleting')}
                </>
              ) : (
                t('common.delete')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
