import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ApiConnectorSchemaSourceType, FieldErrorKey } from '@/components/api-connector/types'

interface SchemaSectionProps {
  submitting: boolean
  schemaSourceType: ApiConnectorSchemaSourceType
  schemaSourceUrl: string
  fieldErrors: Partial<Record<FieldErrorKey, string>>
  onSchemaSourceTypeChange: (value: ApiConnectorSchemaSourceType) => void
  onSchemaSourceUrlChange: (value: string) => void
  clearFieldError: (key: FieldErrorKey) => void
}

export function SchemaSection({
  submitting,
  schemaSourceType,
  schemaSourceUrl,
  fieldErrors,
  onSchemaSourceTypeChange,
  onSchemaSourceUrlChange,
  clearFieldError,
}: SchemaSectionProps) {
  const { t } = useTranslation()

  return (
    <section className="space-y-3 py-4 last:pb-0">
      <h3 className="text-sm font-semibold tracking-tight">
        {t('components.addApiConnectorDialog.schemaConfig')}
      </h3>
      <div className="space-y-3 border-l-2 border-border pl-3">
        <div className="space-y-1">
          <Label>{t('components.addApiConnectorDialog.schemaSourceType')}</Label>
          <Select
            value={schemaSourceType}
            onValueChange={(value) =>
              onSchemaSourceTypeChange(value as ApiConnectorSchemaSourceType)
            }
            disabled={submitting}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="manual">manual</SelectItem>
              <SelectItem value="openapi_url">openapi_url</SelectItem>
              <SelectItem value="openapi_upload">openapi_upload</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {schemaSourceType === 'openapi_url' ? (
          <div className="space-y-1">
            <Label htmlFor="add-schema-source-url">
              {t('components.addApiConnectorDialog.schemaUrl')}
            </Label>
            <Input
              id="add-schema-source-url"
              value={schemaSourceUrl}
              onChange={(e) => {
                onSchemaSourceUrlChange(e.target.value)
                clearFieldError('schemaSourceUrl')
              }}
              placeholder="https://api.example.com/openapi.json"
              disabled={submitting}
              errorMsg={fieldErrors.schemaSourceUrl}
            />
          </div>
        ) : null}

        {schemaSourceType === 'openapi_upload' ? (
          <p className="text-xs text-muted-foreground">
            {t('components.addApiConnectorDialog.schemaNote')}
          </p>
        ) : null}
      </div>
    </section>
  )
}
