from __future__ import annotations

from typing import Generic

from .types import ApplicationType


class BaseController(Generic[ApplicationType]):  # noqa: UP046
    """Reusable domain logic of one component, reaches the others through `self.app.<name>`."""

    def __init__(self, app: ApplicationType) -> None:
        self.app = app
