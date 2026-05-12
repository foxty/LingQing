import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { useEffect, useMemo } from 'react'

i18n.addResourceBundle('en', 'translation', {
  components: {
    dataSourceEditor: {
      selectDataSource: 'Select Data Source',
      readOnlySelect: 'Read-only SELECT queries only',
      validating: 'Validating...',
      validateSql: 'Validate & Preview',
      availableFilterVars: 'Available Filter Variables',
      filterVarHint: 'Usage in SQL: {{helper}}',
      filterVarDesc: 'Use these variables in your SQL query to make it filter-aware',
      queryPreview: 'Query Preview',
      loadingPreview: 'Loading preview...',
      previewFailed: 'Failed to preview query',
      fields: 'Fields',
      dataSample: 'Data Sample ({{count}} rows)',
      noData: 'No data returned',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    dataSourceEditor: {
      selectDataSource: '选择数据源',
      readOnlySelect: '仅支持只读 SELECT 查询',
      validating: '验证中...',
      validateSql: '验证并预览',
      availableFilterVars: '可用筛选变量',
      filterVarHint: 'SQL 中的用法: {{helper}}',
      filterVarDesc: '在 SQL 查询中使用这些变量以实现筛选感知',
      queryPreview: '查询预览',
      loadingPreview: '加载预览中...',
      previewFailed: '预览查询失败',
      fields: '字段',
      dataSample: '数据样本（{{count}} 行）',
      noData: '无返回数据',
    },
  },
}, true, true)
import CodeMirror from '@uiw/react-codemirror'
import { sql } from '@codemirror/lang-sql'
import type { DashboardFilter, DashboardWidget, QueryPreviewResult } from '@/lib/dashboardApi'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { useDataSources } from '@/hooks/useDataSources'

interface DataSourceEditorProps {
  widget: DashboardWidget
  filters: DashboardFilter[]
  preview?: QueryPreviewResult
  isPreviewLoading?: boolean
  previewError?: any
  onVerify?: () => void
  onFieldChange: (field: 'dataSourceId' | 'query', value: any) => void
}

export default function DataSourceEditor({
  widget,
  filters,
  preview,
  isPreviewLoading,
  previewError,
  onVerify,
  onFieldChange,
}: DataSourceEditorProps) {
  const { t } = useTranslation()
  const { dataSources, loading: dsLoading, fetchDataSources } = useDataSources()

  const sqlExtensions = useMemo(() => [sql()], [])

  useEffect(() => {
    if (dataSources.length === 0 && !dsLoading) {
      fetchDataSources()
    }
  }, [dataSources.length, dsLoading, fetchDataSources])

  const selectedDs = dataSources.find((ds) => ds.id === widget.dataSourceId)
  const previewErrorMessage = useMemo(() => {
    if (!previewError) return null
    return (
      previewError?.response.data.detail || previewError?.response.data.message || t('components.dataSourceEditor.previewFailed')
    )
  }, [previewError])

  const filterVars = useMemo(() => {
    return filters.map((filter) => {
      const baseKey = filter.paramKey || ''
      if (filter.type === 'time_range') {
        return {
          id: filter.id,
          name: filter.name,
          vars: [`:start_${baseKey}`, `:end_${baseKey}`],
          helper: `$time_filter(:${baseKey}, <field>)`,
        }
      }
      if (filter.type === 'dropdown_static' || filter.type === 'dropdown_datasource') {
        return {
          id: filter.id,
          name: filter.name,
          vars: [`:${baseKey}`],
          helper: `$in_or_equal(:${baseKey}, <field>)`,
        }
      }
      return {
        id: filter.id,
        name: filter.name,
        vars: [`:${baseKey}`],
      }
    })
  }, [filters])

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="datasource-select">{t('components.dataSourceEditor.selectDataSource')}</Label>
        <Select
          value={widget.dataSourceId?.toString() ?? ''}
          onValueChange={(value) => onFieldChange('dataSourceId', Number(value))}
        >
          <SelectTrigger id="datasource-select">
            <SelectValue placeholder={t('components.dataSourceEditor.selectDataSource')} />
          </SelectTrigger>
          <SelectContent>
            {dataSources.map((ds) => (
              <SelectItem key={ds.id} value={ds.id.toString()}>
                {ds.name} ({ds.type})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedDs && <p className="text-xs text-muted-foreground">{selectedDs.description}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="widget-query">SQL Query</Label>
        <div className="overflow-hidden rounded-md border border-input shadow-sm">
          <CodeMirror
            value={widget.query ?? ''}
            height="160px"
            extensions={sqlExtensions}
            onChange={(value) => onFieldChange('query', value)}
            basicSetup={{
              lineNumbers: true,
              highlightActiveLine: true,
              foldGutter: false,
            }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{t('components.dataSourceEditor.readOnlySelect')}</span>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onVerify}
            disabled={!widget.query || !widget.dataSourceId || isPreviewLoading}
          >
            {isPreviewLoading ? t('components.dataSourceEditor.validating') : t('components.dataSourceEditor.validateSql')}
          </Button>
        </div>
      </div>

      {filterVars.length > 0 && (
        <div className="space-y-2">
          <Label>{t('components.dataSourceEditor.availableFilterVars')}</Label>
          <div className="text-xs text-muted-foreground space-y-2">
            {filterVars.map((filter) => (
              <div key={filter.id} className="rounded-md border px-3 py-2">
                <div className="font-medium text-foreground">{filter.name}</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {filter.vars.map((value) => (
                    <span key={value} className="rounded-sm bg-muted px-2 py-1">
                      {value}
                    </span>
                  ))}
                </div>
                {filter.helper && <div className="mt-2 text-xs">{t('components.dataSourceEditor.filterVarHint', { helper: filter.helper })}</div>}
              </div>
            ))}
            <div className="text-xs">{t('components.dataSourceEditor.filterVarDesc')}</div>
          </div>
        </div>
      )}

      {widget.query && (
        <div className="space-y-2">
          <Label>{t('components.dataSourceEditor.queryPreview')}</Label>
          {isPreviewLoading && <div className="text-xs text-muted-foreground">{t('components.dataSourceEditor.loadingPreview')}</div>}
          {previewErrorMessage && (
            <div className="text-xs text-destructive whitespace-pre-wrap">
              {previewErrorMessage}
            </div>
          )}
          {preview && preview.rows.length > 0 && (
            <div className="text-xs text-muted-foreground space-y-2">
              <div className="text-xs font-semibold">{t('components.dataSourceEditor.fields')}</div>
              <div className="flex flex-wrap gap-1">
                {preview.columns.map((col) => (
                  <span key={col.name} className="px-2 py-1 rounded-sm bg-muted">
                    {col.name} <span className="text-muted-foreground">({col.type})</span>
                  </span>
                ))}
              </div>
              <div className="text-xs font-semibold mt-2">
                {t('components.dataSourceEditor.dataSample', { count: preview.rows.length })}
              </div>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted">
                      {preview.columns.map((col) => (
                        <th
                          key={col.name}
                          className="px-2 py-1 text-left font-medium text-muted-foreground"
                        >
                          {col.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, idx) => (
                      <tr key={idx} className="border-b hover:bg-muted/50">
                        {preview.columns.map((col) => (
                          <td key={col.name} className="px-2 py-1 truncate">
                            {String(row[col.name] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {preview && preview.rows.length === 0 && !isPreviewLoading && (
            <div className="text-xs text-muted-foreground">{t('components.dataSourceEditor.noData')}</div>
          )}
        </div>
      )}
    </div>
  )
}
