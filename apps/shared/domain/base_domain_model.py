"""Core domain models for business logic layer.

Domain models are framework-agnostic and represent pure business entities.
They should not depend on SQLAlchemy, FastAPI, or any external frameworks.

"""

from dataclasses import asdict, dataclass


@dataclass
class BaseDomainModel:
    """Base class for all domain models.

    Domain models are immutable data structures representing business entities.
    Use dataclass for simplicity and performance.
    """

    def model_dump(self) -> dict[str, any]:
        """Convert to dict (Pydantic compatibility)."""
        return asdict(self)

    def to_dict(self) -> dict:
        """Convert domain model to dictionary."""
        return asdict(self)

    def as_dict(self) -> dict:
        """Convert domain model to dictionary."""
        return asdict(self)
