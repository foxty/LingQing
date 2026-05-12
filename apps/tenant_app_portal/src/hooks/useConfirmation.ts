import { useState } from 'react'

export interface ConfirmationState<T> {
  isOpen: boolean
  item: T | null
  isLoading: boolean
}

export interface UseConfirmationReturn<T> {
  isOpen: boolean
  item: T | null
  isLoading: boolean
  open: (item: T) => void
  close: () => void
  setLoading: (loading: boolean) => void
}

/**
 * Hook for managing confirmation dialog state
 * Generic to support any item type (single or batch delete, etc.)
 */
export function useConfirmation<T>(initialItem: T | null = null): UseConfirmationReturn<T> {
  const [isOpen, setIsOpen] = useState(false)
  const [item, setItem] = useState<T | null>(initialItem)
  const [isLoading, setLoading] = useState(false)

  const open = (newItem: T) => {
    setItem(newItem)
    setIsOpen(true)
  }

  const close = () => {
    setIsOpen(false)
    setItem(initialItem)
    setLoading(false)
  }

  return {
    isOpen,
    item,
    isLoading,
    open,
    close,
    setLoading,
  }
}
