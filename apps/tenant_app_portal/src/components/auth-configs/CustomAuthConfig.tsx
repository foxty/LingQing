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
export function CustomAuthConfig({ config, submitting, onChange }: CustomAuthConfigProps) {
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
    <div className="space-y-4">
      {/* Overview Info Box */}
      <div className="rounded-md bg-blue-50 p-4 text-sm text-blue-900">
        <p className="font-semibold mb-2">🔐 Session-Based Authentication</p>
        <p className="mb-2">
          Use this for enterprise systems (Kingdee, SAP, Oracle, etc.) that require a two-step
          process:
        </p>
        <ol className="list-decimal list-inside space-y-1 ml-2 text-xs">
          <li>
            <strong>Login:</strong> Call login endpoint with credentials → get session tokens
          </li>
          <li>
            <strong>Use:</strong> Include tokens in headers for all API requests
          </li>
        </ol>
        <p className="mt-2 text-xs text-muted-foreground">
          💡 Tokens are automatically cached and refreshed. You only configure once!
        </p>
      </div>

      {/* Login Endpoint */}
      <div className="space-y-2">
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
        />
        <p className="text-xs text-muted-foreground">
          The path to your login API. Will be combined with Base URL.
        </p>
      </div>

      {/* Login Method */}
      <div className="space-y-2">
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

      {/* Login Payload Template */}
      <div className="space-y-2">
        <Label htmlFor="custom-payload-template">
          Login Request Body Template
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-payload-template"
          value={config.loginPayloadTemplate}
          onChange={(e) => updateField('loginPayloadTemplate', e.target.value)}
          placeholder={`Example 1 (Simple):
{
  "username": "{username}",
  "password": "{password}"
}

Example 2 (Kingdee array format):
{
  "parameters": ["{account_id}", "{username}", "{app_key}", "{app_secret}", 2052]
}`}
          rows={8}
          disabled={submitting}
          className={
            jsonErrors.loginPayloadTemplate ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {jsonErrors.loginPayloadTemplate && (
          <p className="text-xs text-red-600 font-medium">⚠️ Invalid JSON format</p>
        )}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>📝 Define the JSON structure for your login request.</p>
          <p>
            🔄 Use <code className="bg-muted px-1 py-0.5 rounded">{'{placeholder}'}</code> syntax -
            values come from Extra Config below.
          </p>
          <p>💡 Placeholders are automatically replaced before sending the login request.</p>
        </div>
      </div>

      {/* Token Extraction Paths */}
      <div className="space-y-2">
        <Label htmlFor="custom-token-extraction">
          Token Extraction Paths
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-token-extraction"
          value={config.tokenExtraction}
          onChange={(e) => updateField('tokenExtraction', e.target.value)}
          placeholder={`Example 1 (Nested object):
{
  "token": "Context.UserToken",
  "session_id": "Context.SessionId"
}

Example 2 (Simple response):
{
  "access_token": "data.access_token",
  "refresh_token": "data.refresh_token"
}

Example 3 (Array response):
{
  "token": "items.0.token"
}`}
          rows={8}
          disabled={submitting}
          className={jsonErrors.tokenExtraction ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {jsonErrors.tokenExtraction && (
          <p className="text-xs text-red-600 font-medium">⚠️ Invalid JSON format</p>
        )}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>🎯 Tell the system where to find tokens in the login response.</p>
          <p>
            📍 Use dot notation:{' '}
            <code className="bg-muted px-1 py-0.5 rounded">"Context.UserToken"</code> means{' '}
            <code className="bg-muted px-1 py-0.5 rounded">response["Context"]["UserToken"]</code>
          </p>
          <p>
            🔢 For arrays: <code className="bg-muted px-1 py-0.5 rounded">"items.0.id"</code> means
            first item's id
          </p>
          <p>✨ Each key becomes a token name you can use in Request Headers.</p>
        </div>
      </div>

      {/* Request Headers Template */}
      <div className="space-y-2">
        <Label htmlFor="custom-request-headers">
          API Request Headers Template
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-request-headers"
          value={config.requestHeaders}
          onChange={(e) => updateField('requestHeaders', e.target.value)}
          placeholder={`Example 1 (Kingdee):
{
  "X-User-Token": "{token}",
  "X-Session-Id": "{session_id}"
}

Example 2 (OAuth2 Bearer):
{
  "Authorization": "Bearer {access_token}"
}

Example 3 (Multiple headers):
{
  "X-API-Key": "{api_key}",
  "X-Signature": "{signature}",
  "X-Timestamp": "{timestamp}"
}`}
          rows={8}
          disabled={submitting}
          className={jsonErrors.requestHeaders ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {jsonErrors.requestHeaders && (
          <p className="text-xs text-red-600 font-medium">⚠️ Invalid JSON format</p>
        )}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>📨 These headers will be added to EVERY API request after login.</p>
          <p>
            🔗 Use <code className="bg-muted px-1 py-0.5 rounded">{'{token_name}'}</code> to
            reference tokens extracted above.
          </p>
          <p>⚙️ System automatically replaces placeholders with actual token values.</p>
        </div>
      </div>

      {/* Credentials & Extra Config */}
      <div className="space-y-2">
        <Label htmlFor="custom-extra-config">
          Credentials & Configuration
          <span className="text-destructive ml-1">*</span>
        </Label>
        <Textarea
          id="custom-extra-config"
          value={config.extraConfig}
          onChange={(e) => updateField('extraConfig', e.target.value)}
          placeholder={`Example 1 (Kingdee):
{
  "account_id": "YOUR_DATACENTER_ID",
  "username": "admin",
  "app_key": "your-app-key-here",
  "app_secret": "your-secret-here",
  "token_ttl_seconds": 1800
}

Example 2 (OAuth2):
{
  "client_id": "your-client-id",
  "client_secret": "your-client-secret",
  "token_ttl_seconds": 3600
}

Example 3 (Simple):
{
  "username": "api_user",
  "password": "secret_password",
  "token_ttl_seconds": 900
}`}
          rows={10}
          disabled={submitting}
          className={jsonErrors.extraConfig ? 'border-red-500 focus-visible:ring-red-500' : ''}
        />
        {jsonErrors.extraConfig && (
          <p className="text-xs text-red-600 font-medium">⚠️ Invalid JSON format</p>
        )}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>🔑 Your actual credential values (will be encrypted and stored securely).</p>
          <p>🔄 These values replace the {'{placeholders}'} in Login Payload Template.</p>
          <p>
            ⏱️ <code className="bg-muted px-1 py-0.5 rounded">token_ttl_seconds</code>: How long to
            cache tokens (default: 1800s = 30 min).
          </p>
          <p className="text-orange-600 font-medium">
            ⚠️ Sensitive fields (password, secret, token, api_key) are automatically encrypted!
          </p>
        </div>
      </div>

      {/* Quick Start Guide */}
      <div className="rounded-md bg-amber-50 border border-amber-200 p-3">
        <p className="text-xs font-semibold text-amber-900 mb-2">💡 Quick Start Guide:</p>
        <ol className="text-xs text-amber-800 space-y-1 list-decimal list-inside">
          <li>
            Enter your login endpoint path (e.g.,{' '}
            <code className="bg-white px-1 rounded">/api/login</code>)
          </li>
          <li>Define the login request body using {'{placeholders}'} for credentials</li>
          <li>Specify where tokens appear in the login response (use dot notation)</li>
          <li>Define which headers to send with API requests (reference tokens by name)</li>
          <li>Provide your actual credentials in Extra Config</li>
          <li>Save and test! Tokens will be auto-managed 🎉</li>
        </ol>
      </div>
    </div>
  )
}
