import type { ChatThread } from '@/types'

export function workbenchThreadPath(thread: Pick<ChatThread, 'id' | 'threadKind'>): string {
  return `/workbench/${thread.id}`
}
