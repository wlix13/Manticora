from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from octodns.manager import Manager

from manticora.core import OCTODNS_ERRORS, BaseController
from manticora.models.results import ValidationResult


if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from manticora.app import ManticoraApp  # noqa: F401


class ConfigController(BaseController["ManticoraApp"]):
    def in_project(self) -> AbstractContextManager[None]:
        """Run octodns from project root, where its relative provider paths are anchored."""

        return contextlib.chdir(self.app.project_root)

    def manager(self, cls: type[Manager] = Manager) -> Manager:
        with self.in_project():
            return cls(str(self.app.config_path))

    def validate(self) -> ValidationResult:
        try:
            with self.in_project():
                self.manager().validate_configs()
        except OCTODNS_ERRORS as e:
            return ValidationResult(error=str(e))
        return ValidationResult()
