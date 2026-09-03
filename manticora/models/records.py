from __future__ import annotations

from typing import Any

from octodns.record import Record
from octodns.record.base import ValueMixin
from pydantic import NonNegativeInt, field_validator, model_validator

from manticora.core import BaseModel

from .enums import AddOutcome, RemoveOutcome


RECORD_TYPES: tuple[str, ...] = tuple(sorted(Record.registered_types()))


def takes_single_value(record_type: str) -> bool:
    return issubclass(Record.registered_types()[record_type], ValueMixin)


class RecordSpec(BaseModel):
    """Record as CLI describes it, values in zone-file (rdata) syntax (`10 mx.example.com.` for MX, TXT unescaped)."""

    type: str
    values: tuple[str, ...]
    ttl: NonNegativeInt | None = None
    proxied: bool = False
    lenient: bool = False

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        value = value.upper()
        if value not in RECORD_TYPES:
            raise ValueError(f"unknown record type {value!r}")
        return value

    @model_validator(mode="after")
    def _value_count_fits_type(self) -> RecordSpec:
        if not self.values:
            raise ValueError(f"{self.type} records need at least one value")
        if len(self.values) > 1 and takes_single_value(self.type):
            raise ValueError(f"{self.type} records take exactly one value")
        return self

    @property
    def octodns(self) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        if self.lenient:
            meta["lenient"] = True
        if self.proxied:
            meta["cloudflare"] = {"proxied": True}
        return meta


class Target(BaseModel):
    """Configured zone (with trailing dot) and record name relative to it, empty at apex."""

    zone: str
    name: str

    @property
    def fqdn(self) -> str:
        return f"{self.name}.{self.zone}" if self.name else self.zone


class AddResult(BaseModel):
    outcome: AddOutcome
    target: Target
    created_file: bool = False
    validation_error: str | None = None


class RemoveResult(BaseModel):
    outcome: RemoveOutcome
    target: Target
    types: tuple[str, ...] = ()
    validation_error: str | None = None
