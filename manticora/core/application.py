from __future__ import annotations

from typing import ClassVar, Generic

import rich_click as click

from .component import BaseComponent
from .types import ApplicationType


class BaseApplication(Generic[ApplicationType]):  # noqa: UP046
    """
    Component registry: instantiates `default_components` and exposes their controllers as `app.<name>`.

    Subclass lists `default_components`, commands then reach any controller through click's obj.
    """

    default_components: ClassVar[tuple[type[BaseComponent], ...]] = ()
    _instance: ClassVar[BaseApplication | None] = None

    def __init__(self) -> None:
        self.components: dict[str, BaseComponent] = {}
        type(self)._instance = self
        for component in self.default_components:
            self.register(component)

    @classmethod
    def current(cls) -> ApplicationType:
        if cls._instance is None:
            raise RuntimeError("Application not initialized")
        return cls._instance  # ty:ignore[invalid-return-type]

    def register(self, component_cls: type[BaseComponent]) -> None:
        component = component_cls(self)
        self.components[component.name] = component
        if component.expose_controller:
            setattr(self, component.name, component.controller)
        component.on_register()

    def deregister(self, component_name: str) -> None:
        component = self.components.pop(component_name)
        component.on_deregister()
        if component.expose_controller:
            delattr(self, component_name)

    @classmethod
    def register_cli(cls, group: click.Group) -> None:
        for component_cls in cls.default_components:
            component_cls.expose_cli(group)
