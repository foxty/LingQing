/**
 * Custom hook for thread management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listThreads, createThread, deleteThread, updateThreadTitle, getThread } from '@/lib/threadsApi'
import { convertApiThreadToThread } from '@/types'
import type { ChatThread } from '@/types'

export function useThread(threadId?: string | null, enabled = true) {
  return useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => getThread(threadId!),
    enabled: Boolean(threadId) && enabled,
    retry: false,
  })
}

export function useThreads(agentId?: number) {
  const queryClient = useQueryClient()

  // List threads
  const {
    data: threads = [],
    isLoading,
    isFetched,
    error,
    refetch,
  } = useQuery<ChatThread[]>({
    queryKey: ['threads', agentId ?? 'all'],
    queryFn: async () => {
      try {
        const apiThreads = await listThreads(agentId)
        return apiThreads.map(convertApiThreadToThread)
      } catch (err) {
        console.error('[useThreads] Query failed:', err)
        throw err
      }
    },
    staleTime: 30000, // 30 seconds
  })

  // Show error in console if query failed
  if (error) {
    console.error('[useThreads] Query error:', error)
  }

  // Create thread mutation
  const createThreadMutation = useMutation({
    mutationFn: ({
      agentId,
      title,
      firstMessage,
    }: {
      agentId: number
      title?: string
      firstMessage?: string
    }) => createThread(agentId, title, firstMessage),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    },
  })

  // Delete thread mutation
  const deleteThreadMutation = useMutation({
    mutationFn: (threadId: string) => deleteThread(threadId),
    onSuccess: async (_void, threadId) => {
      queryClient.setQueriesData<ChatThread[]>({ queryKey: ['threads'] }, (current) =>
        current?.filter((thread) => thread.id !== threadId)
      )
      await queryClient.cancelQueries({ queryKey: ['thread', threadId] })
      queryClient.removeQueries({ queryKey: ['thread', threadId] })
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    },
  })

  // Update thread title mutation
  const updateThreadTitleMutation = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      updateThreadTitle(threadId, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['threads'] })
    },
  })

  return {
    threads,
    isLoading,
    isFetched,
    error,
    refetch,
    createThread: createThreadMutation.mutateAsync,
    deleteThread: deleteThreadMutation.mutateAsync,
    updateThreadTitle: updateThreadTitleMutation.mutateAsync,
    isCreating: createThreadMutation.isPending,
    isDeleting: deleteThreadMutation.isPending,
    isUpdating: updateThreadTitleMutation.isPending,
  }
}
