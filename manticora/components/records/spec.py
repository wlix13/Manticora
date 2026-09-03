from __future__ import annotations

from typing import Any

from octodns.record import Record
from octodns.record.exception import RecordException
from octodns.zone import SubzoneRecordException, Zone

from manticora.components.records.errors import RecordError
from manticora.models.records import RecordSpec


CHUNKED_TYPES = frozenset(
    {
        "SPF",
        "TXT",
    }
)
"""Types whose values octodns stores with semicolons escaped."""


def parse_values(spec: RecordSpec) -> list[Any]:
    """Values in octodns YAML shape (`10 mx.example.com.` → `{preference: 10, exchange: mx.example.com.}`)."""

    record_cls = Record.registered_types()[spec.type]
    parsed = []
    for text in spec.values:
        try:
            parsed.append(record_cls.parse_rdata_texts([text])[0])
        except RecordException as e:
            raise RecordError(f"Invalid {spec.type} value {text!r}: {e}") from e
    return parsed


def entry_data(spec: RecordSpec, *, escaped_semicolons: bool = True) -> dict[str, Any]:
    """Zone-file entry: `type`, `ttl` when given, `value` or `values`, then `octodns` metadata."""

    values = parse_values(spec)
    if not escaped_semicolons and spec.type in CHUNKED_TYPES:
        values = list(spec.values)
    data: dict[str, Any] = {"type": spec.type}
    if spec.ttl is not None:
        data["ttl"] = spec.ttl
    if len(values) == 1:
        data["value"] = values[0]
    else:
        data["values"] = values
    if spec.octodns:
        data["octodns"] = spec.octodns
    return data


def check_record(spec: RecordSpec, zone: Zone, name: str, default_ttl: int) -> None:
    """Build record through octodns and add it to (empty) `zone`, which also rejects sub-zone clashes."""

    data = {**entry_data(spec), "ttl": spec.ttl if spec.ttl is not None else default_ttl}
    try:
        zone.add_record(Record.new(zone, name, data))
    except (RecordException, SubzoneRecordException, ValueError) as e:
        raise RecordError(str(e)) from e
