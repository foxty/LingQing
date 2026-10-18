import { MarkdownImage } from '@/components/markdown/MarkdownImage'
import {
  chartArtifactImageSrc,
  isChartArtifact,
  isEmbedArtifactUrl,
} from '@/lib/chartArtifactUrl'
import { Artifact } from '@/types'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'

i18n.addResourceBundle('en', 'translation', {
  components: {
    artifactRenderer: {
      noPreview: 'No preview available for this artifact',
      chartLoadFailed: 'Could not load chart image',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    artifactRenderer: {
      noPreview: '此产物暂无预览',
      chartLoadFailed: '无法加载图表',
    },
  },
}, true, true)

interface ArtifactRendererProps {
  artifact: Artifact
  /** Disable pointer events during drag to avoid iframe capturing mouse events */
  isDragging?: boolean
}

export default function ArtifactRenderer({ artifact, isDragging = false }: ArtifactRendererProps) {
  const { t } = useTranslation()

  if (isChartArtifact(artifact)) {
    const chartSrc = chartArtifactImageSrc(artifact)
    return (
      <div className="flex h-full flex-col overflow-auto bg-background p-4">
        {chartSrc ? (
          <div className="flex min-h-0 flex-1 items-start justify-center">
            <MarkdownImage src={chartSrc} alt={artifact.title} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t('components.artifactRenderer.chartLoadFailed')}
          </div>
        )}
      </div>
    )
  }

  const embedUrl = artifact.url && isEmbedArtifactUrl(artifact.url) ? artifact.url : null

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-hidden">
        {embedUrl ? (
          <iframe
            src={embedUrl}
            className={`h-full w-full border-0 ${isDragging ? 'pointer-events-none' : ''}`}
            title={artifact.title}
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <p className="text-sm">{t('components.artifactRenderer.noPreview')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
