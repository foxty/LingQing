"""Agent ingress channel adapters.

Each platform lives in its own subpackage (e.g. ``slack/``). Public webhooks
use ``/ingress/{endpoint_key}/...`` URLs; platform-specific routers verify
signatures and dispatch to the matching ingress service.
"""
