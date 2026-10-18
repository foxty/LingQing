import DocumentProse from '@/components/DocumentProse'
import { mergeMarkdownComponents } from '@/components/markdown/markdownComponents'
import { preprocessMarkdown } from '@/lib/utils'
import { cn } from '@/lib/utils'
import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type MarkdownDocumentProps = {
  content: string
  /** Compact spacing for intermediate chat steps; final replies use default document typography. */
  density?: 'default' | 'compact'
  className?: string
  components?: Partial<Components>
}

export default function MarkdownDocument({
  content,
  density = 'default',
  className,
  components,
}: MarkdownDocumentProps) {
  const merged = mergeMarkdownComponents(components)

  return (
    <DocumentProse
      className={cn(
        density === 'compact' && 'prose-sm prose-p:my-1 prose-pre:my-1',
        density === 'default' && 'prose-p:my-2 prose-pre:my-2',
        className
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={merged}>
        {preprocessMarkdown(content)}
      </ReactMarkdown>
    </DocumentProse>
  )
}
