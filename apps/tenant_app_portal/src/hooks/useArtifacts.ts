/**
 * Custom hook for managing artifacts in a thread
 * Handles loading, displaying, and updating artifacts
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { listThreadArtifacts } from '@/lib/threadsApi'
import { Artifact } from '@/types'

interface UseArtifactsReturn {
  // Display state
  artifacts: Artifact[] // All artifacts (historical + newly added)
  selectedArtifact: Artifact | null // Currently selected artifact (controls both panel & context banner)
  artifactsPanelWidth: number
  loading: boolean

  // Display actions
  reloadArtifacts: () => Promise<Artifact[]>
  selectArtifact: (artifact: Artifact) => void
  clearSelection: () => void
  updatePanelWidth: (width: number) => void
}

const STORAGE_KEY_PREFIX = 'selectedArtifact_'

/**
 * Hook for managing thread artifacts
 *
 * Features:
 * - Auto-loads historical artifacts when thread changes
 * - Handles both historical and newly generated artifacts
 * - Manages panel width for resizing
 * - Prevents duplicate artifacts
 * - Unified selectedArtifact controls both Artifacts Panel and Context Banner
 * - Persists selection in localStorage per thread
 */
export function useArtifacts(threadId: string | null): UseArtifactsReturn {
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null)
  const [artifactsPanelWidth, setArtifactsPanelWidth] = useState(() => {
    if (typeof window !== 'undefined') {
      return Math.min(Math.max(window.innerWidth * 0.42, 360), 900)
    }
    return 400;
  })
  const [loading, setLoading] = useState(false)
  const hasLoadedRef = useRef(false)

  const getStorageKey = useCallback(() => {
    return threadId ? `${STORAGE_KEY_PREFIX}${threadId}` : null
  }, [threadId])

  const loadSelectedArtifactFromStorage = useCallback((artifactsList: Artifact[]) => {
    if (!threadId) {
      setSelectedArtifact(null)
      return
    }

    const storageKey = getStorageKey()
    if (!storageKey) {
      setSelectedArtifact(null)
      return
    }

    try {
      const storedArtifactId = localStorage.getItem(storageKey)
      if (storedArtifactId) {
        const artifactId = parseInt(storedArtifactId, 10)
        const foundArtifact = artifactsList.find(art => art.id === artifactId)
        if (foundArtifact) {
          setSelectedArtifact(foundArtifact)
          return
        }
        // If artifact not found, clear the storage
        localStorage.removeItem(storageKey)
      }
    } catch (error) {
      console.warn('Failed to load selected artifact from localStorage:', error)
    }
    
    setSelectedArtifact(null)
  }, [threadId, getStorageKey])

  const saveSelectedArtifactToStorage = useCallback((artifact: Artifact | null) => {
    if (!threadId) return
    
    const storageKey = getStorageKey()
    if (!storageKey) return

    try {
      if (artifact) {
        localStorage.setItem(storageKey, artifact.id.toString())
      } else {
        localStorage.removeItem(storageKey)
      }
    } catch (error) {
      console.warn('Failed to save selected artifact to localStorage:', error)
    }
  }, [threadId, getStorageKey])

  const reloadArtifacts = useCallback(async (): Promise<Artifact[]> => {
    if (!threadId) {
      setArtifacts([])
      setSelectedArtifact(null)
      return []
    }

    setLoading(true)
    try {
      const data = await listThreadArtifacts(threadId)
      setArtifacts(data)
      
      // Only load from storage after initial load or when explicitly reloading
      // This prevents auto-selection during normal thread switching
      if (hasLoadedRef.current) {
        loadSelectedArtifactFromStorage(data)
      } else {
        // On first load, don't auto-select anything unless restored from storage
        loadSelectedArtifactFromStorage(data)
        hasLoadedRef.current = true
      }
      
      return data
    } catch (err) {
      console.error('Failed to load artifacts:', err)
      setArtifacts([])
      setSelectedArtifact(null)
      return []
    } finally {
      setLoading(false)
    }
  }, [threadId, loadSelectedArtifactFromStorage])

  // Load historical artifacts from API when thread changes
  useEffect(() => {
    hasLoadedRef.current = false
    void reloadArtifacts()
  }, [reloadArtifacts])

  const selectArtifact = useCallback((artifact: Artifact) => {
    setSelectedArtifact(artifact)
    saveSelectedArtifactToStorage(artifact)
  }, [saveSelectedArtifactToStorage])

  const clearSelection = useCallback(() => {
    setSelectedArtifact(null)
    saveSelectedArtifactToStorage(null)
  }, [saveSelectedArtifactToStorage])

  const updatePanelWidth = useCallback((width: number) => {
    setArtifactsPanelWidth(width)
  }, [])

  return {
    artifacts,
    selectedArtifact,
    artifactsPanelWidth,
    loading,
    reloadArtifacts,
    selectArtifact,
    clearSelection,
    updatePanelWidth,
  }
}