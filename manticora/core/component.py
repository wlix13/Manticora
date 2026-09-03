from typing import ClassVar, Generic

import rich_click as click

from .types import ApplicationType, ControllerType


class BaseComponent(Generic[ApplicationType, ControllerType]):  # noqa: UP046
    """Component: CLI commands for one domain, plus the controller holding its reusable logic."""

    name: ClassVar[str]
    controller_class: ClassVar[type]
    expose_controller: ClassVar[bool] = True
    """Make the controller reachable as `app.<name>` for other components."""

    def __init__(self, app: ApplicationType) -> None:
        self.app = app
        self.controller: ControllerType = self.controller_class(app)

    @classmethod
    def expose_cli(cls, base: click.Group) -> None:
        """Add click commands to `base`, called before any application exists."""

    def on_register(self) -> None:
        """Called after the component is registered with the application."""

    def on_deregister(self) -> None:
        """Called before the component is removed from the application."""
