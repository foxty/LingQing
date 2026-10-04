import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface SettingsPageShellProps {
  children: ReactNode
  className?: string
}

/** Consistent vertical rhythm for every `/settings/*` route canvas. */
export default function SettingsPageShell({ children, className }: SettingsPageShellProps) {
  return <div className={cn('space-y-6', className)}>{children}</div>
}
