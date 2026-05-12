import type { Document } from '@/types'

export type PipelineBadgeState = 'ready' | 'queued' | 'running' | 'waiting' | 'error'

export interface PipelineStatusView {
  state: PipelineBadgeState
  labelKey: string
}

export function getParsePipelineStatus(doc: Document): PipelineStatusView {
  if (doc.status === 'failed' || doc.parseError) {
    return { state: 'error', labelKey: 'knowledgeBase.statusError' }
  }
  if (doc.status === 'processing') {
    return { state: 'running', labelKey: 'knowledgeBase.statusParsing' }
  }
  if (doc.parsedAt) {
    return { state: 'ready', labelKey: 'knowledgeBase.statusParsed' }
  }
  return { state: 'waiting', labelKey: 'knowledgeBase.statusPending' }
}

export function getIndexPipelineStatus(doc: Document): PipelineStatusView {
  if (
    doc.vectorStatus === 'failed' ||
    doc.vectorStatus === 'permanent_failed' ||
    doc.lastVectorSyncError
  ) {
    return { state: 'error', labelKey: 'knowledgeBase.statusError' }
  }
  if (doc.vectorStatus === 'indexing') {
    return { state: 'running', labelKey: 'knowledgeBase.statusIndexing' }
  }
  if (doc.vectorStatus === 'stale' || doc.vectorStatus === 'pending') {
    return { state: 'queued', labelKey: 'knowledgeBase.statusQueued' }
  }
  if (doc.vectorStatus === 'indexed' && doc.lastVectorSyncedAt) {
    return { state: 'ready', labelKey: 'knowledgeBase.statusIndexed' }
  }
  return { state: 'waiting', labelKey: 'knowledgeBase.statusPending' }
}
