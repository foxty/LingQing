---
name: slack-workspace
description: |
  TRIGGERS: Slack messages, channel history, thread history, find a Slack discussion,
  summarize Slack conversations, decisions discussed in Slack.

  CAPABILITIES:
  - Search Slack messages the current user can see
  - Read bounded channel and thread history
  - Resolve users, channels, and file metadata for context
  - Summarize conversations with Slack permalink citations
  - Call Slack HTTP APIs through the tenant's Slack API connector (user credentials)

  DO NOT USE when the request is only about non-Slack topics, or about configuring
  the agent Slack bot / ingress (not workspace message APIs).
metadata:
  owner: platform
tools:
  - name: search_apis
    limit: 8
  - name: api_connector
    limit: 20
---

## Responsibility

Enable the agent to **search**, **retrieve**, and **access Slack via APIs** on behalf of
the current user: find messages, read channel/thread history, resolve related metadata,
and summarize with citations. Prefer the tenant's user-scoped Slack API connector
(discover it with `search_apis`); never use the agent Slack bot token for these reads.

## Do

- Discover Slack operations with `search_apis`, then call them with `api_connector`.
- Match the op to intent: keyword/topic search vs known-channel history vs known-thread
  replies; use user/channel/file helpers only when context is incomplete.
- Bound retrieval (~100 messages per call, ≤3 pages unless the user asks for more).
- Summarize with clear decisions / open questions / action items; cite important
  messages via permalinks under **Sources**.
- On not connected / expired credentials: tell the user to connect or reconnect their
  Slack API connector in API Connectors.
- On `missing_scope`: report which call failed and ask an admin to update Slack app
  scopes, then reconnect.
- On empty or not-found results: explain visibility follows the connected user's
  permissions; do not retry with bot credentials.

## Don't

- Do not send Slack messages, create channels, or change workspace settings unless the
  user explicitly asks **and** a suitable write operation exists on the connector.
  Default posture is read/search only.
- Do not invent messages, decisions, or participants that were not returned by the API.
- Do not dump large raw histories when a short summary answers the question.
- Do not fall back to the agent Slack bot for search or history.

## Common practices

- Prefer one focused search or history call first; expand only if the answer is incomplete.
- Resolve `<@U…>` / channel IDs to display names before summarizing for humans.
- Prefer permalinks over pasting long message bodies when citing sources.
- Treat rate limits and scope errors as user-facing constraints, not silent retries
  with a different auth path.
