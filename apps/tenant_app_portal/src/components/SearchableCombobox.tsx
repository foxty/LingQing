import { Check, ChevronsUpDown, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export interface SearchableComboboxOption {
  value: string
  label: string
}

export interface SearchableComboboxProps {
  value: string
  onChange: (value: string) => void
  options?: SearchableComboboxOption[]
  placeholder: string
  searchPlaceholder: string
  emptyMessage: string
  loadingMessage?: string
  clearLabel?: string
  className?: string
  disabled?: boolean
  clearable?: boolean
  /** Allow committing the search box text when it is not an exact option value. */
  allowFreeform?: boolean
  freeformActionLabel?: (query: string) => string
  /** When set, options are loaded asynchronously (debounced) while the popover is open. */
  searchOptions?: (query: string) => Promise<SearchableComboboxOption[]>
  debounceMs?: number
}

function filterStaticOptions(options: SearchableComboboxOption[], query: string, value: string) {
  const q = query.trim().toLowerCase()
  if (!q) return options
  const filtered = options.filter(
    (opt) => opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q)
  )
  if (value && !filtered.some((o) => o.value === value)) {
    const selected = options.find((o) => o.value === value)
    if (selected) filtered.unshift(selected)
  }
  return filtered
}

export default function SearchableCombobox({
  value,
  onChange,
  options = [],
  placeholder,
  searchPlaceholder,
  emptyMessage,
  loadingMessage = '…',
  clearLabel,
  className,
  disabled = false,
  clearable = true,
  allowFreeform = false,
  freeformActionLabel,
  searchOptions,
  debounceMs = 250,
}: SearchableComboboxProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [asyncOptions, setAsyncOptions] = useState<SearchableComboboxOption[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const searchSeq = useRef(0)

  const selectedLabel = useMemo(() => {
    if (!value) return ''
    const fromStatic = options.find((o) => o.value === value)
    if (fromStatic) return fromStatic.label
    const fromAsync = asyncOptions.find((o) => o.value === value)
    if (fromAsync) return fromAsync.label
    return value
  }, [asyncOptions, options, value])

  const runAsyncSearch = useCallback(
    async (q: string) => {
      if (!searchOptions) return
      const seq = ++searchSeq.current
      setIsSearching(true)
      try {
        const next = await searchOptions(q)
        if (seq === searchSeq.current) {
          setAsyncOptions(next)
        }
      } catch {
        if (seq === searchSeq.current) {
          setAsyncOptions([])
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
    if (!open || !searchOptions) return
    const timer = window.setTimeout(() => void runAsyncSearch(query), debounceMs)
    return () => window.clearTimeout(timer)
  }, [debounceMs, open, query, runAsyncSearch, searchOptions])

  const listOptions = useMemo(() => {
    if (searchOptions) return asyncOptions
    return filterStaticOptions(options, query, value)
  }, [asyncOptions, options, query, searchOptions, value])

  const showFreeform =
    allowFreeform &&
    query.trim().length > 0 &&
    !listOptions.some((o) => o.value === query.trim() || o.label === query.trim())

  const clearSelection = (event: { stopPropagation: () => void }) => {
    event.stopPropagation()
    onChange('')
    setQuery('')
  }

  const commitFreeform = () => {
    const next = query.trim()
    if (!next) return
    onChange(next)
    setQuery('')
    setOpen(false)
  }

  return (
    <div className={cn('flex w-full min-w-0 items-center gap-1', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className="h-9 min-w-0 flex-1 justify-between font-normal"
          >
            <span className={cn('min-w-0 flex-1 truncate text-left', !selectedLabel && 'text-muted-foreground')}>
              {selectedLabel || placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          </Button>
        </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-2" align="start">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={searchPlaceholder}
          className="h-8"
          autoFocus
        />
        <div className="mt-2 max-h-60 space-y-0.5 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
          {clearable && value && clearLabel ? (
            <button
              type="button"
              className="mb-1 flex w-full rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-muted"
              onClick={() => {
                onChange('')
                setQuery('')
                setOpen(false)
              }}
            >
              {clearLabel}
            </button>
          ) : null}
          {showFreeform ? (
            <button
              type="button"
              className="mb-1 flex w-full rounded-md border border-dashed px-2 py-1.5 text-left text-sm hover:bg-muted"
              onClick={commitFreeform}
            >
              {freeformActionLabel?.(query.trim()) ?? query.trim()}
            </button>
          ) : null}
          {isSearching ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">{loadingMessage}</p>
          ) : listOptions.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">{emptyMessage}</p>
          ) : (
            listOptions.map((opt) => {
              const selected = opt.value === value
              return (
                <button
                  key={opt.value}
                  type="button"
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm',
                    'hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    selected && 'bg-muted'
                  )}
                  onClick={() => {
                    onChange(opt.value)
                    setQuery('')
                    setOpen(false)
                  }}
                >
                  {selected ? (
                    <Check className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
                  ) : (
                    <span className="inline-block h-3.5 w-3.5 shrink-0" aria-hidden />
                  )}
                  <span className="min-w-0 truncate font-mono text-xs">{opt.label}</span>
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
      </Popover>
      {clearable && value ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-9 w-9 shrink-0"
          aria-label={clearLabel ?? 'Clear'}
          disabled={disabled}
          onClick={(event) => clearSelection(event)}
        >
          <X className="h-4 w-4" />
        </Button>
      ) : null}
    </div>
  )
}