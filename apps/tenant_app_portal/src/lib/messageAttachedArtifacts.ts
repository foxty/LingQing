import type { AttachedArtifact, Message } from '@/types'

type MessageMetadata = Message['message_metadata']

/** Attached artifacts on a human message (current + legacy metadata key). */
export function getMessageAttachedArtifacts(
  metadata: MessageMetadata | undefined
): AttachedArtifact[] | undefined {
  if (!metadata) return undefined
  const current = metadata.attached_artifacts
  if (current && current.length > 0) {
    return current
  }
  const legacy = metadata.context_resources
  if (legacy && legacy.length > 0) {
    return legacy
  }
  return current ?? legacy
}
