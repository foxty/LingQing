import DocumentProse from '@/components/DocumentProse'
import EmptyState from '@/components/EmptyState'
import ResourceAclShareDialog from '@/components/ResourceAclShareDialog'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useNotification } from '@/hooks/useNotification'
import { useReportDetail } from '@/hooks/useReports'
import { ACL_SHARE_RESOURCE_TYPES } from '@/lib/aclSharesApi'
import { formatDate } from '@/lib/dateTime'
import { preprocessMarkdown } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Calendar, Copy, Share2 } from 'lucide-react'

i18n.addResourceBundle('en', 'translation', {
  report: {
    contentCopied: 'Content copied to clipboard',
    copyFailed: 'Failed to copy content',
    notFound: 'Report not found',
    author: 'By {{name}}',
    sourceSession: 'Source session',
    share: 'Share',
    copy: 'Copy',
    loadFailed: 'Could not load this report',
    loadFailedHint: 'It may have been deleted, or you do not have access. Return to the report list.',
    backToReports: 'Back to reports',
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  report: {
    contentCopied: '内容已复制到剪贴板',
    copyFailed: '复制内容失败',
    notFound: '未找到报告',
    author: '作者：{{name}}',
    sourceSession: '来源会话',
    share: '分享',
    copy: '复制',
    loadFailed: '无法加载此报告',
    loadFailedHint: '报告可能已删除，或你没有访问权限。请返回报告列表。',
    backToReports: '返回报告列表',
  }
}, true, true)
import ReactMarkdown from 'react-markdown'
import { isValidElement, useMemo, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import DOMPurify from 'dompurify'

function normalizeTitle(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase()
}

function titlesMatch(a: string, b: string): boolean {
  return normalizeTitle(a) === normalizeTitle(b)
}

function extractText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (isValidElement(node)) return extractText(node.props.children)
  return ''
}

function stripLeadingMarkdownTitle(content: string, pageTitle: string): string {
  const lines = content.split('\n')
  let index = 0
  while (index < lines.length && lines[index].trim() === '') index += 1
  if (index >= lines.length) return content

  const match = lines[index].match(/^#\s+(.+)\s*$/)
  if (!match || !titlesMatch(match[1], pageTitle)) return content

  const rest = lines.slice(index + 1)
  while (rest.length > 0 && rest[0].trim() === '') rest.shift()
  return rest.join('\n')
}

function stripDuplicateTitleFromHtml(html: string, pageTitle: string): string {
  if (typeof document === 'undefined') return html
  const container = document.createElement('div')
  container.innerHTML = html
  const heading = container.querySelector('h1')
  if (heading && titlesMatch(heading.textContent ?? '', pageTitle)) {
    heading.remove()
  }
  return container.innerHTML
}

function createMarkdownComponents(pageTitle: string) {
  let skippedDuplicateTitle = false
  return {
    h1: ({ children, ...props }: { children?: ReactNode }) => {
      const text = extractText(children)
      if (!skippedDuplicateTitle && titlesMatch(text, pageTitle)) {
        skippedDuplicateTitle = true
        return null
      }
      return <h1 {...props}>{children}</h1>
    },
  }
}

function renderReportContent(content: string, format: string, pageTitle: string) {
  switch (format.toLowerCase()) {
    case 'html':
      // Sanitize HTML to prevent XSS attacks (defense in depth - backend also sanitizes)
      const sanitizedHtml = DOMPurify.sanitize(content, {
        ALLOWED_TAGS: [
          'p',
          'br',
          'hr',
          'h1',
          'h2',
          'h3',
          'h4',
          'h5',
          'h6',
          'ul',
          'ol',
          'li',
          'dl',
          'dt',
          'dd',
          'table',
          'thead',
          'tbody',
          'tr',
          'th',
          'td',
          'div',
          'span',
          'section',
          'article',
          'header',
          'footer',
          'nav',
          'main',
          'a',
          'strong',
          'em',
          'b',
          'i',
          'u',
          'strike',
          'code',
          'pre',
          'blockquote',
          'img',
          'figure',
          'figcaption',
        ],
        ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'id'],
      })
      const html = stripDuplicateTitleFromHtml(sanitizedHtml, pageTitle)
      return <DocumentProse dangerouslySetInnerHTML={{ __html: html }} />
    case 'plaintext':
      return <pre className="document-plain">{content}</pre>
    case 'markdown':
    default: {
      const markdown = stripLeadingMarkdownTitle(preprocessMarkdown(content), pageTitle)
      const components = createMarkdownComponents(pageTitle)
      return (
        <DocumentProse className="prose-pre:overflow-x-auto">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {markdown}
          </ReactMarkdown>
        </DocumentProse>
      )
    }
  }
}

function normalizeMarkdownUrls(content: string, baseUrl: string): string {
  return content.replace(/(!?\[[^\]]*\]\()([^\s)]+)(\))/g, (_match, prefix, rawUrl, suffix) => {
    if (/^(https?:|mailto:|tel:|data:|#)/i.test(rawUrl)) {
      return `${prefix}${rawUrl}${suffix}`
    }

    try {
      const absoluteUrl = new URL(rawUrl, baseUrl).toString()
      return `${prefix}${absoluteUrl}${suffix}`
    } catch {
      return `${prefix}${rawUrl}${suffix}`
    }
  })
}

export default function ReportPage() {
  const { t } = useTranslation()
  const { reportId } = useParams()
  const location = useLocation()
  const { showSuccess, showError } = useNotification()
  const { user } = useAuth()
  const [shareDialogOpen, setShareDialogOpen] = useState(false)

  const id = useMemo(() => {
    if (!reportId) return null
    const parsed = Number(reportId)
    return Number.isFinite(parsed) ? parsed : null
  }, [reportId])

  const isEmbedView = location.pathname.endsWith('/embed')

  const query = useReportDetail(id)

  const handleCopyContent = async () => {
    const content = query.data?.content
    if (!content) return
    try {
      const normalizedContent = normalizeMarkdownUrls(content, window.location.origin)
      await navigator.clipboard.writeText(normalizedContent)
      showSuccess(t('report.contentCopied'))
    } catch {
      showError(t('report.copyFailed'))
    }
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
        {t('common.loading')}
      </div>
    )
  }

  if (query.isError || !query.data) {
    return (
      <div className="p-4">
        <EmptyState
          title={t('report.loadFailed')}
          description={t('report.loadFailedHint')}
          action={
            <Button variant="outline" asChild>
              <Link to="/artifacts/reports">{t('report.backToReports')}</Link>
            </Button>
          }
        />
      </div>
    )
  }

  const report = query.data
  const reportOwner = report.owner_username ?? report.owner_id
  const canCopyMarkdownContent = report.format.toLowerCase() === 'markdown'
  const isOwner = !!user?.username && report.owner_username === user.username

  return (
    <div className="px-6 py-6 lg:px-10">
      <article className="w-full">
        <header className="mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <h1 className="document-title text-[32px] font-semibold tracking-tight">{report.title}</h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                {formatDate(report.created_at)}
              </span>
              {reportOwner ? <span>{t('report.author', { name: reportOwner })}</span> : null}
              {report.source_thread_id && (
                <span className="inline-flex items-center gap-2">
                  <span>{t('report.sourceSession')}</span>
                  <Link
                    to={`/workbench/${report.source_thread_id}`}
                    className="font-mono underline underline-offset-2 hover:text-foreground"
                  >
                    {report.source_thread_id}
                  </Link>
                </span>
              )}
            </div>
          </div>
          {!isEmbedView && (
            <div className="flex shrink-0 items-center gap-2">
              <Button onClick={() => setShareDialogOpen(true)}>
                <Share2 className="mr-1.5 h-4 w-4" />
                {t('report.share')}
              </Button>
              {isOwner && canCopyMarkdownContent && (
                <Button variant="outline" onClick={handleCopyContent}>
                  <Copy className="mr-1.5 h-4 w-4" />
                  {t('report.copy')}
                </Button>
              )}
            </div>
          )}
        </header>
        {renderReportContent(report.content, report.format, report.title)}
      </article>

      <ResourceAclShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        resourceType={ACL_SHARE_RESOURCE_TYPES.REPORT}
        resourceId={report.id}
        resourceTitle={report.title}
      />
    </div>
  )
}
