import { useCallback, useMemo } from 'react'
import {
  AGENT_MAX_LOOP_ITERATIONS_MAX,
  AGENT_MAX_LOOP_ITERATIONS_MIN,
  formatAgentMaxLoopInputValue,
  parseAgentMaxLoopInputChange,
} from '@/lib/agentsApi'

export const agentMaxLoopInputHtmlProps = {
  type: 'number' as const,
  min: AGENT_MAX_LOOP_ITERATIONS_MIN,
  max: AGENT_MAX_LOOP_ITERATIONS_MAX,
  inputMode: 'numeric' as const,
}

/**
 * Controlled max-loop field state for agent create/edit forms (string input ↔ nullable config value).
 */
export function useAgentMaxLoopIterationsField(
  value: number | null | undefined,
  onValueChange: (value: number | null) => void
) {
  const inputValue = useMemo(() => formatAgentMaxLoopInputValue(value), [value])

  const onInputChange = useCallback(
    (raw: string) => {
      const parsed = parseAgentMaxLoopInputChange(raw)
      if (parsed === undefined) {
        return
      }
      onValueChange(parsed)
    },
    [onValueChange]
  )

  return { inputValue, onInputChange, ...agentMaxLoopInputHtmlProps }
}