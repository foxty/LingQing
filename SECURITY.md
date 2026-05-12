# Security Policy

## Supported versions

Security fixes are applied to the default branch. Older release tags may not receive backports unless noted in release notes.

## Reporting a vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Report sensitive issues privately via **GitHub Security Advisories** (repository **Security** tab → **Report a vulnerability**). If that is unavailable, open a private maintainer contact channel listed in the repository profile. Include:

- Description of the issue and potential impact
- Steps to reproduce
- Affected components (service, endpoint, version)
- Any suggested mitigation

We aim to acknowledge reports within a few business days.

## Scope

In scope:

- Authentication and authorization bypass
- Tenant isolation failures
- Remote code execution in sandbox or agent tooling
- SQL injection, SSRF, or unsafe deserialization in API handlers
- Secret leakage in logs, responses, or repository artifacts

Out of scope (unless chained with a security impact):

- Denial-of-service without a practical exploit path
- Issues in third-party dependencies without a demonstrable impact on LingQing
- Social engineering or physical access scenarios

## Secure development

- Never commit secrets; use `deploy/env/.env.template` and local `.env.local`.
- Scope all repository and service operations by tenant.
- Follow [AGENTS.md](AGENTS.md) for exception handling and logging (no manual stack traces; structured logger only).
