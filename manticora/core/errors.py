from __future__ import annotations

import yaml
from octodns.manager import ManagerException
from octodns.provider import ProviderException
from octodns.record.exception import RecordException
from octodns.secret.exception import SecretsException
from octodns.zone import DuplicateRecordException, SubzoneRecordException
from octodns.zone.exception import ZoneException
from rich.markup import escape


OCTODNS_ERRORS = (
    ManagerException,
    SecretsException,
    ProviderException,
    RecordException,
    ZoneException,
    DuplicateRecordException,
    SubzoneRecordException,
    yaml.YAMLError,
    OSError,
)
"""Everything octodns raises while loading config and zone files."""


class Error(Exception):
    """Base error, printed by `main` as red `Error:` line with exit code 1."""

    def __rich__(self) -> str:
        return f"[red bold]Error:[/red bold] [red]{escape(str(self))}[/red]"
