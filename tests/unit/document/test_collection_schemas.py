"""Document collection API schema limits."""

import pytest
from pydantic import ValidationError

from apps.shared.document.constants import (
    DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH,
    DOCUMENT_COLLECTION_NAME_MAX_LENGTH,
)
from apps.shared.document.schemas import DocumentCollectionCreate, DocumentCollectionUpdate


def test_collection_create_rejects_long_name():
    with pytest.raises(ValidationError):
        DocumentCollectionCreate(
            name="x" * (DOCUMENT_COLLECTION_NAME_MAX_LENGTH + 1),
        )


def test_collection_create_rejects_long_description():
    with pytest.raises(ValidationError):
        DocumentCollectionCreate(
            name="ok",
            description="y" * (DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH + 1),
        )


def test_collection_update_accepts_max_lengths():
    DocumentCollectionUpdate(
        name="n" * DOCUMENT_COLLECTION_NAME_MAX_LENGTH,
        description="d" * DOCUMENT_COLLECTION_DESCRIPTION_MAX_LENGTH,
    )