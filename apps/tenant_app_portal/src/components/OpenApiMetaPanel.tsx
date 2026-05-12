import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    openApiMetaPanel: {
      title: 'API Metadata',
      name: 'Name',
      version: 'OpenAPI Version',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    openApiMetaPanel: {
      title: 'API 元数据',
      name: '名称',
      version: 'OpenAPI 版本',
    },
  },
}, true, true)

import { Badge } from '@/components/ui/badge'
import { ChevronDown, ExternalLink, Info } from 'lucide-react'

interface SchemaServer {
  url: string
  description?: string
}

interface SchemaMetadata {
  title?: string
  version?: string
  openapi_version?: string
  description?: string
  servers?: SchemaServer[]
  tags?: string[]
}

interface OpenApiMetaPanelProps {
  metadata: SchemaMetadata
}

export default function OpenApiMetaPanel({ metadata }: OpenApiMetaPanelProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (!metadata.title) return null

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Info className="h-4 w-4 text-muted-foreground" />
          {t('components.openApiMetaPanel.title')}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">{t('components.openApiMetaPanel.name')}</span>
              <span className="font-medium">{metadata.title}</span>
              {metadata.version && (
                <Badge variant="outline" className="ml-2 text-xs">
                  v{metadata.version}
                </Badge>
              )}
            </div>
            {metadata.openapi_version && (
              <div>
                <span className="text-muted-foreground">{t('components.openApiMetaPanel.version')}</span>
                <span>{metadata.openapi_version}</span>
              </div>
            )}
          </div>

          {metadata.description && (
            <p className="text-sm text-muted-foreground line-clamp-3">{metadata.description}</p>
          )}

          {metadata.servers && metadata.servers.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Servers
              </p>
              <div className="flex flex-wrap gap-2">
                {metadata.servers.map((s) => (
                  <a
                    key={s.url}
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 text-xs text-foreground hover:underline"
                  >
                    <ExternalLink className="h-3 w-3" />
                    {s.description ?? s.url}
                  </a>
                ))}
              </div>
            </div>
          )}

          {metadata.tags && metadata.tags.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Tags
              </p>
              <div className="flex flex-wrap gap-1">
                {metadata.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
