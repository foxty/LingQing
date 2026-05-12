"""Vector store metadata key constants and documentation.

All chunks stored in the vector database use a consistent metadata schema.
These constants define the canonical keys and their semantics.

Metadata Keys:
- resource_type: Canonical resource type (document, asset, api_connector).
  Used for filtering and routing search results.
- resource_id: Internal DB primary key of the owning resource.
  Used for retrieval and context expansion.
- tenant_id: Tenant isolation key. All queries must filter by tenant_id.
- chunk_index: Zero-based position of this chunk within its resource.
  Used for ordering and context window expansion.
- total_chunks: Total number of chunks for this resource.
  Used for progress tracking and validation.

Document-specific metadata (added by chunking pipeline):
- doc_id: Document DB ID (same as resource_id for documents).
- filename: Original filename for display.
- file_url: Storage URL for file retrieval.

Asset-specific metadata:
- asset_id: Asset DB ID (same as resource_id for assets).
- data_source_id: Parent data source ID.
- asset_name: Table/view name.
- asset_type: table, view, etc.

API connector-specific metadata:
- operation_uid: Unique operation identifier.
- connector_id: Parent API connector ID.
- method: HTTP method (GET, POST, etc.).
- path_template: API path template.
- summary: Operation summary.
- description: Operation description.
- tags: OpenAPI tags.
"""

from __future__ import annotations

# Core metadata keys (all resource types)
META_RESOURCE_TYPE: str = "resource_type"
META_RESOURCE_ID: str = "resource_id"
META_PARENT_ID: str = "parent_id"
META_OWNER_ID: str = "owner_id"
META_TENANT_ID: str = "tenant_id"
META_CHUNK_INDEX: str = "chunk_index"
META_TOTAL_CHUNKS: str = "total_chunks"
