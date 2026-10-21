/**
 * Pure helpers for the + attach artifact picker (keyboard nav, chip ids).
 */

export type MentionPickerKeyAction =
  | { type: 'none' }
  | { type: 'close' }
  | { type: 'move'; nextIndex: number }
  | { type: 'select'; index: number }

export function reduceMentionPickerKeyDown(options: {
  open: boolean
  resultCount: number
  activeIndex: number
  key: string
}): MentionPickerKeyAction {
  const { open, resultCount, activeIndex, key } = options

  if (!open) {
    return { type: 'none' }
  }

  if (key === 'Escape') {
    return { type: 'close' }
  }

  if (resultCount === 0) {
    return { type: 'none' }
  }

  if (key === 'ArrowDown') {
    return { type: 'move', nextIndex: (activeIndex + 1) % resultCount }
  }

  if (key === 'ArrowUp') {
    return { type: 'move', nextIndex: (activeIndex - 1 + resultCount) % resultCount }
  }

  if (key === 'Enter') {
    return { type: 'select', index: activeIndex }
  }

  return { type: 'none' }
}

export function mentionResourceChipId(artifactId: number): string {
  return `artifact-${artifactId}`
}

export function filterUnselectedMentionResults<T extends { artifact_id: number }>(
  items: T[],
  selectedIds: ReadonlySet<string>
): T[] {
  return items.filter((item) => !selectedIds.has(mentionResourceChipId(item.artifact_id)))
}
