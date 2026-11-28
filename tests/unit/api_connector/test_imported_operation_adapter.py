"""Adapter mapping for OpenAPI-imported operation drafts."""

from dataclasses import fields

from apps.shared.external_systems.api_connector.adapters import imported_operation_domain_from_spec
from apps.shared.external_systems.api_connector.constants import AUTH_REQUIREMENT_REQUIRED
from apps.shared.external_systems.api_connector.domain import ApiOperationDomain
from apps.shared.external_systems.api_connector.schema_parser import OperationSpec


def test_imported_operation_domain_from_spec_matches_domain_factory():
    spec = OperationSpec(
        operation_uid_seed="seed",
        method="GET",
        path_template="/widgets",
        operation_id="list_widgets",
        summary="List widgets",
        description=None,
        tags=["api"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
        auth_requirement=AUTH_REQUIREMENT_REQUIRED,
    )
    from_adapter = imported_operation_domain_from_spec(connector_id=7, owner_id=3, spec=spec)
    from_domain = ApiOperationDomain.draft_imported_from_fields(
        connector_id=7,
        owner_id=3,
        method=spec.method,
        path_template=spec.path_template,
        operation_id=spec.operation_id,
        summary=spec.summary,
        description=spec.description,
        tags=spec.tags,
        request_schema=spec.request_schema,
        response_schema=spec.response_schema,
        auth_requirement=spec.auth_requirement,
    )
    skip = {"created_at", "updated_at"}
    for field in fields(ApiOperationDomain):
        if field.name in skip:
            continue
        assert getattr(from_adapter, field.name) == getattr(from_domain, field.name)