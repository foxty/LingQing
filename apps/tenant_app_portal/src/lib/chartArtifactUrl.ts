import { chartImageApiPath } from '@/lib/chartImagePath'
import type { Artifact } from '@/types'

/** Canonical chart image path for artifact panel / authenticated fetch. */
export function chartArtifactImageSrc(artifact: Artifact): string | null {
  if (artifact.url) {
    const apiPath = chartImageApiPath(artifact.url)
    if (apiPath) {
      return apiPath.startsWith('/') ? apiPath : `/${apiPath}`
    }
  }

  const metaChartId = artifact.metadata?.chart_id
  const chartId =
    typeof artifact.resource_id === 'number'
      ? artifact.resource_id
      : typeof metaChartId === 'number'
        ? metaChartId
        : null

  if (chartId == null) {
    return null
  }

  return `/charts/${chartId}/image.svg`
}

export function isChartArtifact(artifact: Artifact): boolean {
  return artifact.artifact_type === 'chart'
}

/** Portal embed routes (iframe-safe on the SPA origin). */
export function isEmbedArtifactUrl(url: string): boolean {
  return (
    /^\/reports\/\d+\/embed/.test(url) ||
    /^\/dashboards\/\d+\/embed/.test(url) ||
    /^\/scheduled-tasks\/\d+\/embed/.test(url) ||
    /^\/api\/apps\/\d+\/dev\/embed/.test(url)
  )
}
