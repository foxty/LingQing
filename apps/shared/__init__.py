"""Shared infrastructure layer.

This module contains shared components used by both Agent and API layers:
- RAG (Retrieval-Augmented Generation) components
- Data sources management (analytics databases, external connections)
- Other shared infrastructure components

Following Clean Architecture principles, this layer provides base infrastructure
that business logic layers (agents, api) depend on.
"""
