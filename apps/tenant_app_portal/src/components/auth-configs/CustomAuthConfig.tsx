import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useEffect, useState } from 'react'

interface CustomAuthConfigData {
  loginEndpoint: string
  loginMethod: string
  loginPayloadTemplate: string
  tokenExtraction: string
  requestHeaders: string
  extraConfig: string
}

interface CustomAuthConfigProps {
  config: CustomAuthConfigData
  submitting: boolean
  fieldErrors?: Partial<
    Record<
      | 'loginEndpoint'
      | 'loginPayloadTemplate'
      | 'tokenExtraction'
      | 'requestHeaders'
      | 'extraConfig',
      string
    >
  >
  onChange: (config: CustomAuthConfigData) => void
}

/**
 * Custom/Session-based authentication configuration form.
 *
 * For enterprise systems (Kingdee, SAP, Oracle, etc.) that require:
 * 1. Login to obtain session tokens
 * 2. Use tokens in custom headers for API requests
 *
 * Features automatic token caching and refresh.
 */
export function CustomAuthConfig({
  config,
  submitting,
  fieldErrors,
  onChange,
}: CustomAuthConfigProps) {
  const [jsonErrors, setJsonErrors] = useState<Record<string, boolean>>({
    loginPayloadTemplate: false,
    tokenExtraction: false,
    requestHeaders: false,
    extraConfig: false,
  })

  // Validate JSON fields whenever they change
  useEffect(() => {
    const validateJson = (value: string): boolean => {
      if (!value || !value.trim()) return false // Empty is considered invalid for required fields
      try {
        JSON.parse(value)
        return true
      } catch {
        return false
      }
    }

    setJsonErrors({
      loginPayloadTemplate: !validateJson(config.loginPayloadTemplate),
      tokenExtraction: !validateJson(config.tokenExtraction),
      requestHeaders: !validateJson(config.requestHeaders),
      extraConfig: !validateJson(config.extraConfig),
    })
  }, [
    config.loginPayloadTemplate,
    config.tokenExtraction,
    config.requestHeaders,
    config.extraConfig,
  ])

  const updateField = (field: keyof CustomAuthConfigData, value: string) => {
    onChange({ ...config, [field]: value })
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Session auth: login once for tokens, then send those tokens on API requests. Tokens are
        cached and refreshed automatically.
      </p>

      <div className="space-y-1">
        <Label htmlFor="custom-login-endpoint">
          Login Endpoint
          <span className="text-xs text-muted-foreground ml-2">(relative to Base URL)</span>
        </Label>
        <Input
          id="custom-login-endpoint"
          value={config.loginEndpoint}
          onChange={(e) => updateField('loginEndpoint', e.target.value)}
          placeholder="/api/auth/login or /Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginByAppSecret.common.kdsvc"
          disabled={submitting}
          errorMsg={fieldErrors?.loginEndpoint}
        />
        <p className="text-xs text-muted-foreground">
          Path to the login API; combined with Base URL.
        </p>
      </div>

      <div className="space-y-1">
        <Label htmlFor="custom-login-method">Login HTTP Method</Label>
        <Select
          value={config.loginMethod}
          onValueChange={(v) => updateField('loginMethod', v)}
          disabled={submitting}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="POST">POST (most common)</SelectItem>
            <SelectItem value="GET">GET</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="custom-payload-template">
          Login Request Body Template
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-payload-template"
          value={config.loginPayloadTemplate}
          onChange={(e) => updateField('loginPayloadTemplate', e.target.value)}
          placeholder={`{
  "username": "{username}",
  "password": "{password}"
}`}
          rows={6}
          disabled={submitting}
          className={
            jsonErrors.loginPayloadTemplate ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {fieldErrors?.loginPayloadTemplate ? (
          <p className="text-xs text-destructive">{fieldErrors.loginPayloadTemplate}</p>
        ) : jsonErrors.loginPayloadTemplate ? (
          <p className="text-xs text-destructive font-medium">Invalid JSON format</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          JSON body for login. Use{' '}
          <code className="rounded bg-muted px-1 py-0.5">{'{placeholder}'}</code> values from
          Credentials & Configuration below.
        </p>
      </div>

      <div className="space-y-1">
        <Label htmlFor="custom-token-extraction">
          Token Extraction Paths
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-token-extraction"
          value={config.tokenExtraction}
          onChange={(e) => updateField('tokenExtraction', e.target.value)}
          placeholder={`{
  "token": "Context.UserToken",
  "session_id": "Context.SessionId"
}`}
          rows={5}
          disabled={submitting}
          className={jsonErrors.tokenExtraction ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {fieldErrors?.tokenExtraction ? (
          <p className="text-xs text-destructive">{fieldErrors.tokenExtraction}</p>
        ) : jsonErrors.tokenExtraction ? (
          <p className="text-xs text-destructive font-medium">Invalid JSON format</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Dot paths into the login response (e.g.{' '}
          <code className="rounded bg-muted px-1 py-0.5">Context.UserToken</code>). Each key is a
          token name for request headers.
        </p>
      </div>

      <div className="space-y-1">
        <Label htmlFor="custom-request-headers">
          API Request Headers Template
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-request-headers"
          value={config.requestHeaders}
          onChange={(e) => updateField('requestHeaders', e.target.value)}
          placeholder={`{
  "Authorization": "Bearer {access_token}"
}`}
          rows={5}
          disabled={submitting}
          className={jsonErrors.requestHeaders ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {fieldErrors?.requestHeaders ? (
          <p className="text-xs text-destructive">{fieldErrors.requestHeaders}</p>
        ) : jsonErrors.requestHeaders ? (
          <p className="text-xs text-destructive font-medium">Invalid JSON format</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Headers added to every API request after login. Reference tokens with{' '}
          <code className="rounded bg-muted px-1 py-0.5">{'{token_name}'}</code>.
        </p>
      </div>

      <div className="space-y-1">
        <Label htmlFor="custom-extra-config">
          Credentials & Configuration
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-extra-config"
          value={config.extraConfig}
          onChange={(e) => updateField('extraConfig', e.target.value)}
          placeholder={`{
  "username": "api_user",
  "password": "secret_password",
  "token_ttl_seconds": 1800
}`}
          rows={6}
          disabled={submitting}
          className={jsonErrors.extraConfig ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {fieldErrors?.extraConfig ? (
          <p className="text-xs text-destructive">{fieldErrors.extraConfig}</p>
        ) : jsonErrors.extraConfig ? (
          <p className="text-xs text-destructive font-medium">Invalid JSON format</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Credential values (encrypted at rest) that fill login placeholders. Optional{' '}
          <code className="rounded bg-muted px-1 py-0.5">token_ttl_seconds</code> controls cache
          lifetime (default 1800).
        </p>
      </div>
    </div>
  )
}
