from __future__ import annotations

from enum import StrEnum


class Operation(StrEnum):
    """octodns change kinds, values match its change class names."""

    CREATE = "Create"
    UPDATE = "Update"
    DELETE = "Delete"


class AddOutcome(StrEnum):
    ADDED = "added"
    CREATED_NAME = "created-name"
    EXISTS = "exists"


class RemoveOutcome(StrEnum):
    REMOVED = "removed"
    REMOVED_NAME = "removed-name"
    MISSING = "missing"
