import { useTranslation } from 'react-i18next'
import i18n from '@/i18n/config'
import { Input } from '@/components/ui/input'

i18n.addResourceBundle('en', 'translation', {
  components: {
    manualOperation: {
      requestSchema: 'Request Schema (JSON)',
      responseSchema: 'Response Schema (JSON)',
    },
  },
}, true, true)

i18n.addResourceBundle('zh', 'translation', {
  components: {
    manualOperation: {
      requestSchema: '请求 Schema (JSON)',
      responseSchema: '响应 Schema (JSON)',
    },
  },
}, true, true)
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

interface ManualOperationFormProps {
  method: string
  onMethodChange: (v: string) => void
  pathTemplate: string
  onPathTemplateChange: (v: string) => void
  summary: string
  onSummaryChange: (v: string) => void
  operationId: string
  onOperationIdChange: (v: string) => void
  requestSchemaText?: string
  onRequestSchemaTextChange?: (v: string) => void
  responseSchemaText?: string
  onResponseSchemaTextChange?: (v: string) => void
  /** When true, renders the Request / Response Schema fields. Defaults to false. */
  showSchemaFields?: boolean
  /** Prefix for HTML id attributes to avoid collisions when rendered multiple times. */
  idPrefix?: string
}

export default function ManualOperationForm({
  method,
  onMethodChange,
  pathTemplate,
  onPathTemplateChange,
  summary,
  onSummaryChange,
  operationId,
  onOperationIdChange,
  requestSchemaText,
  onRequestSchemaTextChange,
  responseSchemaText,
  onResponseSchemaTextChange,
  showSchemaFields = false,
  idPrefix = 'op',
}: ManualOperationFormProps) {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Method</Label>
          <Select value={method} onValueChange={onMethodChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="GET">GET</SelectItem>
              <SelectItem value="POST">POST</SelectItem>
              <SelectItem value="PUT">PUT</SelectItem>
              <SelectItem value="PATCH">PATCH</SelectItem>
              <SelectItem value="DELETE">DELETE</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${idPrefix}-operation-id`}>Operation ID</Label>
          <Input
            id={`${idPrefix}-operation-id`}
            value={operationId}
            onChange={(e) => onOperationIdChange(e.target.value)}
            placeholder="getOrder"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-path`}>Path Template</Label>
        <Input
          id={`${idPrefix}-path`}
          value={pathTemplate}
          onChange={(e) => onPathTemplateChange(e.target.value)}
          placeholder="/orders/{id}"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-summary`}>Summary</Label>
        <Input
          id={`${idPrefix}-summary`}
          value={summary}
          onChange={(e) => onSummaryChange(e.target.value)}
          placeholder="Get order detail"
        />
      </div>

      {showSchemaFields && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-request-schema`}>{t('components.manualOperation.requestSchema')}</Label>
            <Textarea
              id={`${idPrefix}-request-schema`}
              rows={14}
              value={requestSchemaText ?? ''}
              onChange={(e) => onRequestSchemaTextChange?.(e.target.value)}
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${idPrefix}-response-schema`}>{t('components.manualOperation.responseSchema')}</Label>
            <Textarea
              id={`${idPrefix}-response-schema`}
              rows={14}
              value={responseSchemaText ?? ''}
              onChange={(e) => onResponseSchemaTextChange?.(e.target.value)}
              className="font-mono text-xs"
            />
          </div>
        </div>
      )}
    </div>
  )
}
