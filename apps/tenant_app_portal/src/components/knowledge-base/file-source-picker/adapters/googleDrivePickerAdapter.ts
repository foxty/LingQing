import { getDrivePickerConfig } from '@/lib/documentSyncApi'
import type { FolderPickResult } from '../types'

const GAPI_SCRIPT_URL = 'https://apis.google.com/js/api.js'

interface GooglePickerDocument {
  id: string
  name: string
}

interface GooglePickerBuilder {
  setAppId(appId: string): GooglePickerBuilder
  setOAuthToken(token: string): GooglePickerBuilder
  addView(view: unknown): GooglePickerBuilder
  setCallback(callback: (data: GooglePickerResponse) => void): GooglePickerBuilder
  build(): { setVisible(visible: boolean): void }
}

interface GooglePickerResponse {
  action: string
  docs?: GooglePickerDocument[]
}

interface GooglePickerNamespace {
  PickerBuilder: new () => GooglePickerBuilder
  ViewId: { FOLDERS: string }
  DocsView: new (viewId: string) => { setSelectFolderEnabled(enabled: boolean): unknown }
  Action: { PICKED: string; CANCEL: string }
  Response: { ACTION: string; DOCUMENTS: string }
}

declare global {
  interface Window {
    gapi?: {
      load: (
        api: string,
        options: { callback?: () => void; onerror?: () => void }
      ) => void
    }
    google?: {
      picker?: GooglePickerNamespace
    }
  }
}

let gapiLoadPromise: Promise<void> | null = null

function loadGapiScript(): Promise<void> {
  if (gapiLoadPromise) {
    return gapiLoadPromise
  }

  gapiLoadPromise = new Promise((resolve, reject) => {
    if (window.gapi) {
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = GAPI_SCRIPT_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google API script'))
    document.head.appendChild(script)
  })

  return gapiLoadPromise
}

function loadGooglePicker(): Promise<void> {
  return loadGapiScript().then(
    () =>
      new Promise((resolve, reject) => {
        if (!window.gapi) {
          reject(new Error('Google API is unavailable'))
          return
        }
        window.gapi.load('picker', {
          callback: () => resolve(),
          onerror: () => reject(new Error('Failed to load Google Picker')),
        })
      })
  )
}

export async function pickGoogleDriveFolder(connectionId: number): Promise<FolderPickResult | null> {
  await loadGooglePicker()

  const picker = window.google?.picker
  if (!picker) {
    throw new Error('Google Picker is unavailable')
  }

  const config = await getDrivePickerConfig(connectionId)

  return new Promise((resolve, reject) => {
    try {
      const folderView = new picker.DocsView(picker.ViewId.FOLDERS).setSelectFolderEnabled(true)

      const builder = new picker.PickerBuilder()
        .setAppId(config.app_id)
        .setOAuthToken(config.access_token)
        .addView(folderView)
        .setCallback((data) => {
          if (data.action === picker.Action.CANCEL) {
            resolve(null)
            return
          }
          if (data.action !== picker.Action.PICKED) {
            return
          }
          const doc = data.docs?.[0]
          if (!doc?.id || !doc.name) {
            reject(new Error('No folder selected'))
            return
          }
          resolve({ folderId: doc.id, folderName: doc.name })
        })

      builder.build().setVisible(true)
    } catch (error) {
      reject(error)
    }
  })
}
