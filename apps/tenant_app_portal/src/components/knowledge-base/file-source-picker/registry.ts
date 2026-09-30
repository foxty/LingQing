import { pickGoogleDriveFolder } from '@/components/knowledge-base/file-source-picker/adapters/googleDrivePickerAdapter'
import type { FileSourceProvider, FolderPickResult } from './types'

export type FileSourcePickerAdapter = (connectionId: number) => Promise<FolderPickResult | null>

const adapters: Record<FileSourceProvider, FileSourcePickerAdapter> = {
  google_drive: pickGoogleDriveFolder,
}

export function getFileSourcePickerAdapter(provider: FileSourceProvider): FileSourcePickerAdapter {
  const adapter = adapters[provider]
  if (!adapter) {
    throw new Error(`Unsupported file source provider: ${provider}`)
  }
  return adapter
}
