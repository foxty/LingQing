"""Slack agent ingress adapter.

- ``admin_service`` — portal CRUD, manifest download, connection test
- ``ingress_service`` — runtime: Slack event → identity → chat → reply
- ``ingress_router`` — public webhooks (signing secret, no JWT)
- ``interactivity_service`` — Block Kit feedback buttons and comment modal
"""
