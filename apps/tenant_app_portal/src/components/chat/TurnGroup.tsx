import type { ReactNode } from 'react'

interface TurnGroupProps {
  children: ReactNode
  className?: string
}

/** Visual grouping for one human message and its reply run(s). */
export function TurnGroup({ children, className }: TurnGroupProps) {
  return (
    <section
      className={`border-l-2 border-muted pl-3 space-y-3 ${className ?? ''}`.trim()}
      aria-label="conversation turn"
    >
      {children}
    </section>
  )
}
