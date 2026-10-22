import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { MultiSelectOption } from '@/components/agents/MultiSelectField'
import {
  MultiSelectSelectionSurface,
  multiSelectTriggerClassName,
} from '@/components/agents/MultiSelectField'

type AsyncMultiSelectFieldProps = {
  label: string
  help?: string
  placeholder: string
  searchPlaceholder: string
  emptyOptionsMessage: string
  noResultsMessage: string
  loadingMessage: string
  selectedOptions: MultiSelectOption[]
  selectedIds: string[]
  disabled?: boolean
  onChange: (selectedIds: string[]) => void
  onPickOption?: (option: MultiSelectOption) => void
  searchOptions: (query: string) => Promise<MultiSelectOption[]>
  debounceMs?: number
}

export default function AsyncMultiSelectField({
  label,
  help,
  placeholder,
  searchPlaceholder,
  emptyOptionsMessage,
  noResultsMessage,
  loadingMessage,
  selectedOptions,
  selectedIds,
  disabled = false,
  onChange,
  onPickOption,
  searchOptions,
  debounceMs = 300,
}: AsyncMultiSelectFieldProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [results, setResults] = useState<MultiSelectOption[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const searchSeq = useRef(0)

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query), debounceMs)
    return () => window.clearTimeout(handle)
  }, [query, debounceMs])

  const runSearch = useCallback(
    async (q: string) => {
      const seq = ++searchSeq.current
      setIsSearching(true)
      try {
        const next = await searchOptions(q)
        if (seq === searchSeq.current) {
          setResults(next)
        }
      } catch {
        if (seq === searchSeq.current) {
          setResults([])
        }
      } finally {
        if (seq === searchSeq.current) {
          setIsSearching(false)
        }
      }
    },
    [searchOptions]
  )

  useEffect(() => {
    if (!open) {
      return
    }
    void runSearch(debouncedQuery)
  }, [open, debouncedQuery, runSearch])

  useEffect(() => {
    if (!open) {
      setQuery('')
      setDebouncedQuery('')
      setResults([])
      searchSeq.current += 1
      setIsSearching(false)
    }
  }, [open])

  const selectedSet = new Set(selectedIds)
  const availableOptions = results.filter((option) => !selectedSet.has(option.id))

  const addOption = (option: MultiSelectOption) => {
    if (selectedSet.has(option.id)) {
      return
    }
    onPickOption?.(option)
    onChange([...selectedIds, option.id])
    setQuery('')
  }

  const removeOption = (id: string) => {
    onChange(selectedIds.filter((item) => item !== id))
  }

  const listBody = isSearching ? (
    <p className="flex items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {loadingMessage}
    </p>
  ) : availableOptions.length === 0 ? (
    <p className="px-2 py-3 text-sm text-muted-foreground">
      {results.length === 0 && !debouncedQuery.trim() ? emptyOptionsMessage : noResultsMessage}
    </p>
  ) : (
    availableOptions.map((option) => (
      <button
        key={option.id}
        type="button"
        className={cn(
          'flex w-full flex-col items-start rounded-md px-2 py-1.5 text-left text-sm',
          'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
        )}
        onClick={() => addOption(option)}
      >
        <span className="font-medium">{option.label}</span>
        {option.description ? (
          <span className="text-xs text-muted-foreground line-clamp-2">{option.description}</span>
        ) : null}
      </button>
    ))
  )

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {help ? <p className="text-xs text-muted-foreground">{help}</p> : null}
      {disabled ? (
        <div className={cn(multiSelectTriggerClassName, 'cursor-default')}>
          <MultiSelectSelectionSurface
            selectedOptions={selectedOptions}
            placeholder={placeholder}
            disabled
          />
        </div>
      ) : (
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <div
              role="combobox"
              tabIndex={0}
              aria-expanded={open}
              className={cn(multiSelectTriggerClassName, 'cursor-pointer')}
            >
              <MultiSelectSelectionSurface
                selectedOptions={selectedOptions}
                placeholder={placeholder}
                onRemove={removeOption}
              />
            </div>
          </PopoverTrigger>
          <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              className="h-8"
            />
            <div className="mt-2 max-h-48 space-y-0.5 overflow-y-auto">{listBody}</div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}
