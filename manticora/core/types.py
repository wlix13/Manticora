from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar


if TYPE_CHECKING:
    from .application import BaseApplication
    from .controller import BaseController

ApplicationType = TypeVar("ApplicationType", bound="BaseApplication")
ControllerType = TypeVar("ControllerType", bound="BaseController")
