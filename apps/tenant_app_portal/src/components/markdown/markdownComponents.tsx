import { MarkdownImage } from '@/components/markdown/MarkdownImage'
import { isNumericMarkdownCell } from '@/lib/markdownReading'
import { cn } from '@/lib/utils'
import type { Components } from 'react-markdown'
import { isValidElement, type ReactNode } from 'react'

function cellText(children: ReactNode): string {
  if (children == null || typeof children === 'boolean') return ''
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(cellText).join('')
  if (isValidElement(children)) return cellText(children.props.children)
  return ''
}

function tableCellClassName(children: ReactNode, extra?: string) {
  const numeric = isNumericMarkdownCell(cellText(children))
  return cn(
    'border border-border px-3 py-2 align-top',
    numeric ? 'text-right tabular-nums' : 'text-left',
    extra
  )
}

export const baseMarkdownComponents: Components = {
  img: ({ src, alt }) => <MarkdownImage src={src} alt={alt} />,
  table: ({ children, ...props }) => (
    <div className="markdown-table-scroll my-4 min-w-0 max-w-full overflow-x-auto">
      <table className="w-max border-collapse text-sm" {...props}>
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th {...props} className={tableCellClassName(children, 'bg-muted/30 font-semibold whitespace-nowrap')}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td {...props} className={tableCellClassName(children, 'whitespace-nowrap')}>
      {children}
    </td>
  ),
}

export function mergeMarkdownComponents(overrides?: Partial<Components>): Components {
  return { ...baseMarkdownComponents, ...overrides }
}
