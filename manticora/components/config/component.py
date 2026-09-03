from __future__ import annotations

from typing import TYPE_CHECKING

import rich_click as click

from manticora.core import BaseComponent, Error, console

from .controller import ConfigController


if TYPE_CHECKING:
    from manticora.app import ManticoraApp


class ValidationError(Error):
    """Config or zone files do not load through octodns."""


class ConfigComponent(BaseComponent["ManticoraApp", ConfigController]):
    name = "config"
    controller_class = ConfigController

    @classmethod
    def expose_cli(cls, base: click.Group) -> None:
        @base.command()
        @click.pass_obj
        def validate(app: ManticoraApp) -> None:
            """Validate config and zone files through octodns."""

            result = app.config.validate()
            console.print(result)
            if not result.ok:
                raise ValidationError("Validation failed")
