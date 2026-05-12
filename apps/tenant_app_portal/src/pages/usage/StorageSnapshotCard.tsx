import i18n from '@/i18n/config'
import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import SettingsSection from '@/components/SettingsSection'
import { formatDate } from '@/lib/dateTime'

i18n.addResourceBundle('en', 'translation', {
  settings: {
    usageTab: {
      storageSnapshot: 'Storage Snapshot',
      storageDesc: 'Storage usage breakdown',
      updatedAt: ' (Updated: {{date}})',
      totalStorage: 'Total Storage',
      docStorage: 'Document Storage',
      dbStorage: 'Database Storage',
      vectorDbStorage: 'Vector DB Storage',
      notAvailable: 'N/A',
    }
  }
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  settings: {
    usageTab: {
      storageSnapshot: '存储快照',
      storageDesc: '存储使用明细',
      updatedAt: '（更新于: {{date}}）',
      totalStorage: '总存储',
      docStorage: '文档存储',
      dbStorage: '数据库存储',
      vectorDbStorage: '向量数据库存储',
      notAvailable: '不可用',
    }
  }
}, true, true)

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let unitIndex = 0

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }

  return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`
}

interface StorageSnapshotCardProps {
  totalStorageBytes: number
  updatedAt?: string
}

export default function StorageSnapshotCard({
  totalStorageBytes,
  updatedAt,
}: StorageSnapshotCardProps) {
  const { t } = useTranslation()
  const pieOption = useMemo<EChartsOption | null>(() => {
    const documentStorageBytes = totalStorageBytes
    const databaseStorageBytes = null
    const vectorStorageBytes = null

    if (
      databaseStorageBytes === null ||
      vectorStorageBytes === null ||
      (documentStorageBytes === 0 && databaseStorageBytes === 0 && vectorStorageBytes === 0)
    ) {
      return null
    }

    return {
      tooltip: {
        trigger: 'item',
        formatter: (param: any) => {
          const name = param?.name || '-'
          const value = Number(param?.value || 0)
          const percent = Number(param?.percent || 0)
          return `${name}: ${formatBytes(value)} (${percent.toFixed(1)}%)`
        },
      },
      legend: {
        bottom: 0,
      },
      series: [
        {
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          label: {
            show: true,
            formatter: '{b}: {d}%',
          },
          data: [
            {
              name: t('settings.usageTab.docStorage'),
              value: documentStorageBytes,
            },
            {
              name: t('settings.usageTab.dbStorage'),
              value: databaseStorageBytes,
            },
            {
              name: t('settings.usageTab.vectorDbStorage'),
              value: vectorStorageBytes,
            },
          ],
        },
      ],
    }
  }, [totalStorageBytes])

  return (
    <SettingsSection
      title={t('settings.usageTab.storageSnapshot')}
      description={`${t('settings.usageTab.storageDesc')}${updatedAt ? t('settings.usageTab.updatedAt', { date: formatDate(updatedAt) }) : ''}`}
    >
      <div className="space-y-3 text-sm">
        {pieOption ? (
          <div className="h-[300px] w-full">
            <ReactECharts option={pieOption} style={{ height: '100%', width: '100%' }} />
          </div>
        ) : null}
        <div className="flex items-center justify-between border-b pb-2">
          <span className="text-muted-foreground">{t('settings.usageTab.totalStorage')}</span>
          <span className="font-medium">{formatBytes(totalStorageBytes)}</span>
        </div>
        <div className="flex items-center justify-between border-b pb-2">
          <span className="text-muted-foreground">{t('settings.usageTab.docStorage')}</span>
          <span className="font-medium">{formatBytes(totalStorageBytes)}</span>
        </div>
        <div className="flex items-center justify-between border-b pb-2">
          <span className="text-muted-foreground">{t('settings.usageTab.dbStorage')}</span>
          <span className="font-medium">{t('settings.usageTab.notAvailable')}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t('settings.usageTab.vectorDbStorage')}</span>
          <span className="font-medium">{t('settings.usageTab.notAvailable')}</span>
        </div>
      </div>
    </SettingsSection>
  )
}
