from pathlib import Path

from rich.console import Console

from .application import BaseApplication
from .component import BaseComponent
from .controller import BaseController
from .errors import OCTODNS_ERRORS, Error
from .model import BaseModel


__all__ = [
    "OCTODNS_ERRORS",
    "BaseApplication",
    "BaseComponent",
    "BaseController",
    "BaseModel",
    "Error",
    "console",
    "err",
    "find_project_root",
]

console = Console()
err = Console(stderr=True)


def find_project_root() -> Path:
    """Nearest ancestor of cwd holding config.yaml, cwd itself when none does."""

    for directory in (cwd := Path.cwd(), *cwd.parents):
        if (directory / "config.yaml").exists():
            return directory
    return cwd
