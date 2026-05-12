"""Adapters between live app DB/domain/DTO layers."""

from apps.shared.live_app.domain import LiveAppConfig, LiveAppRecord
from apps.shared.live_app.schemas import LiveAppDeploymentStateDTO, LiveAppListDTO, LiveAppRecordDTO


def db_live_app_to_domain(db_live_app) -> LiveAppRecord:
    config = LiveAppConfig.from_mapping(db_live_app.app_config)
    owner_name: str | None = None
    if "owner_user" in db_live_app.__dict__:
        owner_user = db_live_app.__dict__.get("owner_user")
        owner_name = owner_user.username if owner_user else ("已删除用户" if db_live_app.owner_id is not None else None)

    return LiveAppRecord(
        app_id=db_live_app.id,
        name=db_live_app.name,
        description=db_live_app.description,
        entry_file=db_live_app.entry_file,
        sdk_version=db_live_app.sdk_version,
        status=db_live_app.status,
        data_source_id=db_live_app.data_source_id,
        owner_name=owner_name,
        deployment_state=config.deployed_commits,
        updated_at=None if db_live_app.updated_at is None else db_live_app.updated_at.isoformat(),
    )


def domain_live_app_to_dto(record: LiveAppRecord) -> LiveAppRecordDTO:
    return LiveAppRecordDTO(
        app_id=record.app_id,
        name=record.name,
        description=record.description,
        entry_file=record.entry_file,
        sdk_version=record.sdk_version,
        status=record.status,
        data_source_id=record.data_source_id,
        owner_name=record.owner_name,
        deployment_state=LiveAppDeploymentStateDTO(
            dev=record.deployment_state.dev,
            test=record.deployment_state.test,
            prod=record.deployment_state.prod,
        ),
        updated_at=record.updated_at,
    )


def domain_live_app_list_to_dto(records: list[LiveAppRecord]) -> LiveAppListDTO:
    app_dtos = [domain_live_app_to_dto(item) for item in records]
    return LiveAppListDTO(apps=app_dtos, count=len(app_dtos))
