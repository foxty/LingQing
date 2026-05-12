import i18n from '@/i18n/config'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useDocumentParsed } from '@/hooks/useDocuments'
import { normalizeApiErrorPayload } from '@/lib/api'
import type { ApiParsedBlock } from '@/lib/documentsApi'
import { formatDate } from '@/lib/dateTime'
import { AuthDocumentImage } from '@/components/chat/AuthDocumentImage'
import type { Document } from '@/types'
import { useTranslation } from 'react-i18next'

i18n.addResourceBundle(
  'en',
  'translation',
  {
    knowledgeBase: {
      parsedPreview: 'Parsed content',
      parsedEmpty: 'No parsed content yet.',
      parsedTruncated: 'Showing first {{shown}} of {{total}} blocks.',
      parsedUnavailable: 'Unable to load parsed content.',
    },
  },
  true,
  true
)

i18n.addResourceBundle(
  'zh',
  'translation',
  {
    knowledgeBase: {
      parsedPreview: '解析内容',
      parsedEmpty: '还没有解析内容。',
      parsedTruncated: '仅显示前 {{shown}} / {{total}} 个块。',
      parsedUnavailable: '无法加载解析内容。',
    },
  },
  true,
  true
)

interface DocumentParsedPreviewProps {
  document: Document | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DocumentParsedPreview({
  document,
  open,
  onOpenChange,
}: DocumentParsedPreviewProps) {
  const { t } = useTranslation()
  const { data, isLoading, error } = useDocumentParsed(open ? (document?.id ?? null) : null)
  const errorMessage = error
    ? normalizeApiErrorPayload((error as { response?: { data?: unknown } }).response?.data).message
    : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="truncate">
            {document?.filename ?? t('knowledgeBase.parsedPreview')}
          </DialogTitle>
          <DialogDescription>
            {data?.parser ? `${data.parser}` : t('knowledgeBase.parsedPreview')}
            {data?.parsed_at ? ` · ${formatDate(data.parsed_at)}` : ''}
          </DialogDescription>
        </DialogHeader>

        {data && Object.keys(data.type_counts).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(data.type_counts).map(([type, count]) => (
              <Badge key={type} variant="outline">
                {type} {count}
              </Badge>
            ))}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto space-y-3 pr-1">
          {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
          {error && (
            <p className="text-sm text-destructive">
              {errorMessage || t('knowledgeBase.parsedUnavailable')}
            </p>
          )}
          {!isLoading && !errorMessage && data?.parse_error && (
            <p className="text-sm text-destructive break-words">{data.parse_error}</p>
          )}
          {!isLoading && !errorMessage && data && data.blocks.length === 0 && !data.parse_error && (
            <p className="text-sm text-muted-foreground">{t('knowledgeBase.parsedEmpty')}</p>
          )}
          {data?.truncated && (
            <p className="text-xs text-muted-foreground">
              {t('knowledgeBase.parsedTruncated', {
                shown: data.blocks.length,
                total: data.block_count,
              })}
            </p>
          )}
          {data?.blocks.map((block, index) => (
            <ParsedBlock
              key={`${block.type}-${index}`}
              block={block}
              documentId={data.document_id}
            />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ParsedBlock({ block, documentId }: { block: ApiParsedBlock; documentId: number }) {
  if (block.type === 'image' && block.uri) {
    const filename = block.uri.split('/').pop() ?? ''
    return (
      <figure className="space-y-1">
        <AuthDocumentImage
          src={`/documents/${documentId}/images/${filename}`}
          alt={block.caption ?? ''}
        />
        {block.caption ? (
          <figcaption className="text-xs text-muted-foreground">{block.caption}</figcaption>
        ) : null}
      </figure>
    )
  }
  const text = block.text?.trim() || block.caption?.trim()
  if (!text) {
    return null
  }
  if (block.type === 'heading') {
    return <h3 className="text-sm font-semibold">{text}</h3>
  }
  if (block.type === 'table') {
    return (
      <pre className="text-xs whitespace-pre-wrap break-words rounded-md border bg-muted/40 p-2 font-mono">
        {text}
      </pre>
    )
  }
  return <p className="text-sm whitespace-pre-wrap break-words text-foreground">{text}</p>
}
