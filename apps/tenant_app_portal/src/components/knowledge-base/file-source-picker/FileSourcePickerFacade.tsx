import { getFileSourcePickerAdapter } from './registry'
import type { FileSourceProvider, FolderPickResult } from './types'

export async function openFileSourcePicker(
  provider: FileSourceProvider,
  connectionId: number
): Promise<FolderPickResult | null> {
  const adapter = getFileSourcePickerAdapter(provider)
  return adapter(connectionId)
}
