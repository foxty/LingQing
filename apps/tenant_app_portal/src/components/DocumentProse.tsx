import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export default function DocumentProse({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('document-prose prose max-w-none dark:prose-invert', className)} {...props} />
}
