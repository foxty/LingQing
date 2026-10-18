import { describe, expect, it } from 'vitest'
import { getMessageAttachedArtifacts } from '@/lib/messageAttachedArtifacts'

describe('getMessageAttachedArtifacts', () => {
  it('prefers attached_artifacts over legacy context_resources', () => {
    const result = getMessageAttachedArtifacts({
      attached_artifacts: [{ artifact_id: 1, artifact_type: 'report', title: 'A' }],
      context_resources: [{ artifact_id: 2, artifact_type: 'chart', title: 'B' }],
    })
    expect(result).toEqual([{ artifact_id: 1, artifact_type: 'report', title: 'A' }])
  })

  it('falls back to context_resources for older persisted messages', () => {
    const result = getMessageAttachedArtifacts({
      context_resources: [{ artifact_id: 9, artifact_type: 'report', title: 'Legacy' }],
    })
    expect(result).toEqual([{ artifact_id: 9, artifact_type: 'report', title: 'Legacy' }])
  })

  it('returns undefined when metadata is missing or empty', () => {
    expect(getMessageAttachedArtifacts(undefined)).toBeUndefined()
    expect(getMessageAttachedArtifacts({})).toBeUndefined()
  })
})
