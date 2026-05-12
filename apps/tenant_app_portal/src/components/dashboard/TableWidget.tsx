import type { TableColumnConfig, TableDisplayConfig, TableValueFormat } from '@/lib/dashboardApi'
import { formatDate } from '@/lib/dateTime'

interface TableWidgetProps {
  data: Array<Record<string, any>>
  displayConfig?: TableDisplayConfig
}

function formatTableValue(
  value: unknown,
  format?: TableValueFormat,
  defaultFormat?: TableValueFormat
): string {
  const finalFormat = format ?? defaultFormat

  if (value === null || value === undefined) {
    return finalFormat?.nullDisplay ?? ''
  }

  const formatType = finalFormat?.formatType
  const prefix = finalFormat?.prefix ?? ''
  const suffix = finalFormat?.suffix ?? ''

  if (formatType === 'boolean') {
    const boolValue = Boolean(value)
    const label = boolValue
      ? (finalFormat?.trueLabel ?? 'True')
      : (finalFormat?.falseLabel ?? 'False')
    return `${prefix}${label}${suffix}`
  }

  if (formatType === 'datetime') {
    const normalized = formatDate(value as string, {
      precision:
        finalFormat?.dateFormat === 'date'
          ? 'date'
          : finalFormat?.dateFormat === 'time'
            ? 'time'
            : 'datetime',
      fallback: '',
    })
    if (!normalized) {
      return `${prefix}${String(value)}${suffix}`
    }
    return `${prefix}${normalized}${suffix}`
  }

  if (formatType === 'number' || formatType === 'currency' || formatType === 'percent') {
    const numeric = Number(value)
    if (Number.isNaN(numeric)) {
      return `${prefix}${String(value)}${suffix}`
    }

    const precision = finalFormat?.precision
    const numberFormat = new Intl.NumberFormat(undefined, {
      style:
        formatType === 'currency' ? 'currency' : formatType === 'percent' ? 'percent' : 'decimal',
      currency: formatType === 'currency' ? (finalFormat?.currency ?? 'USD') : undefined,
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    })

    return `${prefix}${numberFormat.format(numeric)}${suffix}`
  }

  return `${prefix}${String(value)}${suffix}`
}

export default function TableWidget({ data, displayConfig }: TableWidgetProps) {
  if (!data.length) {
    return <div className="text-sm text-muted-foreground">No data.</div>
  }

  const config = displayConfig ?? {}
  const columns: TableColumnConfig[] = config.columns?.length
    ? config.columns
    : Object.keys(data[0]).map((field) => ({ field }))
  const showHeader = config.showHeader ?? true
  const showRowNumbers = config.showRowNumbers ?? false
  const zebraStripes = config.zebraStripes ?? false
  const compact = config.compact ?? false

  const cellPadding = compact ? 'px-2 py-1' : 'px-3 py-2'

  return (
    <div className="overflow-auto rounded-md border">
      <table className="w-full text-sm">
        {showHeader && (
          <thead className="bg-muted">
            <tr>
              {showRowNumbers && (
                <th className={`${cellPadding} text-left font-medium text-muted-foreground w-12`}>
                  #
                </th>
              )}
              {columns.map((col) => (
                <th
                  key={col.field}
                  className={`${cellPadding} font-medium text-muted-foreground ${
                    col.align === 'center'
                      ? 'text-center'
                      : col.align === 'right'
                        ? 'text-right'
                        : 'text-left'
                  }`}
                  style={{
                    width: col.width,
                    minWidth: col.minWidth,
                    maxWidth: col.maxWidth,
                  }}
                >
                  {col.label ?? col.field}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {data.map((row, idx) => (
            <tr
              key={idx}
              className={`border-t ${zebraStripes && idx % 2 === 1 ? 'bg-muted/30' : ''}`}
            >
              {showRowNumbers && (
                <td className={`${cellPadding} text-muted-foreground`}>{idx + 1}</td>
              )}
              {columns.map((col) => (
                <td
                  key={col.field}
                  className={`${cellPadding} ${
                    col.align === 'center'
                      ? 'text-center'
                      : col.align === 'right'
                        ? 'text-right'
                        : 'text-left'
                  }`}
                  style={{
                    width: col.width,
                    minWidth: col.minWidth,
                    maxWidth: col.maxWidth,
                  }}
                >
                  {formatTableValue(row[col.field], col.format, config.defaultFormat)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
