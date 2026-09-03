from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml

from manticora.components.records.errors import RecordError
from manticora.models.enums import AddOutcome, RemoveOutcome


RECORD_INDENT = "  "
NULL_TAG = "tag:yaml.org,2002:null"
STR_TAG = "tag:yaml.org,2002:str"
YAML_WIDTH = 10**6
"""Effectively no line folding: octodns values (DKIM keys, long TXT) must stay on one line."""

_ITEM_RE = re.compile(r"^(\s*)- ")


@dataclass(frozen=True)
class RecordItem:
    type: str | None
    start: int
    end: int


@dataclass(frozen=True)
class NameItem:
    name: str
    records: tuple[RecordItem, ...]
    splice: bool
    start: int
    end: int

    def matches(self, name: str) -> bool:
        return self.name.lower() == name.lower()

    def of_type(self, record_type: str | None) -> tuple[RecordItem, ...]:
        if record_type is None:
            return self.records
        return tuple(r for r in self.records if r.type is not None and r.type.upper() == record_type.upper())


@dataclass(frozen=True)
class AddEdit:
    text: str
    outcome: AddOutcome


@dataclass(frozen=True)
class RemoveEdit:
    text: str
    outcome: RemoveOutcome
    types: tuple[str, ...] = ()


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    """Double-quote strings holding colons (IPv6, SPF includes), as zone files spell them."""

    style = '"' if ":" in value and "\\" not in value else None
    return dumper.represent_scalar(STR_TAG, value, style=style)


_Dumper.add_representer(str, _represent_str)


def _dump(obj: Any, sort_keys: bool = False) -> str:
    return yaml.dump(obj, Dumper=_Dumper, sort_keys=sort_keys, width=YAML_WIDTH, allow_unicode=True)


def scalar_text(value: str) -> str:
    """`value` as YAML scalar, quoted whenever plain text would read back differently (`no`, `''`, `1:2::3`)."""

    return _dump(value).removesuffix("\n").removesuffix("\n...")


def record_lines(data: dict[str, Any], indent: str = RECORD_INDENT, sort_keys: bool = False) -> list[str]:
    """One record as sequence item (`- type: A` / `  value: ...`), each line prefixed with `indent`."""

    return [indent + line for line in _dump([data], sort_keys).splitlines()]


def entry_lines(name: str, data: dict[str, Any], indent: str = RECORD_INDENT, sort_keys: bool = False) -> list[str]:
    return [f"{scalar_text(name)}:", *record_lines(data, indent, sort_keys)]


class ZoneFile:
    def __init__(self, text: str) -> None:
        text = (
            text if text.endswith("\n") or not text else text + "\n"
        )  # PyYAML end-marks stop one line short without it
        self._eol = "\r\n" if "\r\n" in text else "\n"
        self._lines = text.splitlines()
        self.entries = tuple(_name_item(key, value, s, e) for key, value, s, e in _entries(_compose(text)))
        self._indent = next(
            (m.group(1) for e in self.entries for r in e.records if (m := _ITEM_RE.match(self._lines[r.start]))),
            RECORD_INDENT,
        )

    def entry(self, name: str) -> NameItem | None:
        return next((e for e in self.entries if e.matches(name)), None)

    def has_record(self, name: str, record_type: str) -> bool:
        entry = self.entry(name)
        return entry is not None and bool(entry.of_type(record_type))

    def add_record(self, name: str, data: dict[str, Any], *, order: Callable[[str], Any] | None = None) -> AddEdit:
        """
        Append record under `name`, creating entry when missing.

        New entry goes at end of file, or, with `order` (sort key octodns enforces on file),
        before first entry sorting after it, with keys sorted same way.
        """

        if self.has_record(name, data["type"]):
            raise RecordError(f"{name or '@'!r} already has {data['type']} record")
        lines = list(self._lines)
        entry = self.entry(name)
        if entry is None:
            block = entry_lines(name, data, self._indent, sort_keys=order is not None)
            at = self._entry_line(lines, name, order)
            if at == 0:
                block = [*block, ""] if lines else block
            else:
                block = ["", *block]
            lines[at:at] = block
            return AddEdit(self._render(lines), AddOutcome.CREATED_NAME)

        if not entry.splice:
            raise RecordError(f"Records of {name or '@'!r} must be a block sequence to add to")
        if entry.records:
            last = entry.records[-1]
            indent = _item_indent(lines[last.start])
            at = _content_end(lines, last.start, last.end)
        else:
            indent, at = self._indent, entry.start + 1
        lines[at:at] = record_lines(data, indent, sort_keys=order is not None)
        return AddEdit(self._render(lines), AddOutcome.ADDED)

    def remove_record(self, name: str, record_type: str | None = None) -> RemoveEdit:
        """Drop records of `name` (all, or only `record_type`), and entry when left empty."""

        entry = self.entry(name)
        if entry is None:
            raise RecordError(f"{name or '@'!r} is not in the zone file")
        victims = entry.of_type(record_type)
        if not victims:
            raise RecordError(f"{name or '@'!r} has no {record_type} record")
        lines = list(self._lines)
        types = tuple(r.type for r in victims if r.type is not None)
        if len(victims) == len(entry.records):
            _drop_block(lines, entry.start, _content_end(lines, entry.start, entry.end))
            return RemoveEdit(self._render(lines), RemoveOutcome.REMOVED_NAME, types)

        if not entry.splice:
            raise RecordError(f"Records of {name or '@'!r} must be a block sequence to remove from")
        for item in sorted(victims, key=lambda r: r.start, reverse=True):
            del lines[item.start : _content_end(lines, item.start, item.end)]
        return RemoveEdit(self._render(lines), RemoveOutcome.REMOVED, types)

    def _entry_line(self, lines: list[str], name: str, order: Callable[[str], Any] | None) -> int:
        """Line new `name:` entry opens on: after content of entry it should follow, else end of file."""

        if order is not None:
            key = order(name)
            index = next((i for i, e in enumerate(self.entries) if order(e.name) > key), None)
            if index == 0:
                return 0
            if index is not None:
                before = self.entries[index - 1]
                return _content_end(lines, before.start, before.end)
        _trim_trailing_blank(lines)
        return len(lines)

    def _render(self, lines: list[str]) -> str:
        _trim_trailing_blank(lines)
        return self._eol.join(lines) + self._eol if lines else ""


def _compose(text: str) -> yaml.MappingNode | None:
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        anchored = any(getattr(event, "anchor", None) for event in yaml.parse(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as e:
        raise RecordError(f"Zone file is not valid YAML: {e}") from e
    if anchored:
        raise RecordError("Zone file uses YAML anchors or aliases; refusing to edit around them")
    if root is not None and not isinstance(root, yaml.MappingNode):
        raise RecordError("Zone file has no top-level mapping")
    return root


def _entries(root: yaml.MappingNode | None) -> list[tuple[str, yaml.Node, int, int]]:
    """`(name, value, start, end)` per top-level entry, each running to next key (or end of file)."""

    if root is None or not root.value:
        return []
    keys = [key for key, _ in root.value]
    if any(not isinstance(key, yaml.ScalarNode) for key in keys):
        raise RecordError("Zone file has a non-scalar top-level key; refusing to edit around it")
    seen: set[str] = set()
    for key in keys:
        if key.value.lower() in seen:
            raise RecordError(f"Duplicate entry for {key.value!r}; edits and loads would disagree")
        seen.add(key.value.lower())
    starts = [key.start_mark.line for key in keys]
    ends = [*starts[1:], _end_line(root)]
    return [(key.value, value, s, e) for (key, value), s, e in zip(root.value, starts, ends, strict=True)]


def _name_item(name: str, value: yaml.Node, start: int, end: int) -> NameItem:
    if isinstance(value, yaml.SequenceNode) and not value.flow_style:
        records = tuple(RecordItem(_scalar(item, "type"), s, e) for item, s, e in _spans(value.value, _end_line(value)))
        return NameItem(name, records, True, start, end)
    if isinstance(value, yaml.SequenceNode):
        records = tuple(RecordItem(_scalar(item, "type"), start, end) for item in value.value)
        return NameItem(name, records, False, start, end)
    if isinstance(value, yaml.MappingNode):
        return NameItem(name, (RecordItem(_scalar(value, "type"), start, end),), False, start, end)
    bare = value.tag == NULL_TAG and value.start_mark.index == value.end_mark.index
    return NameItem(name, (), bare, start, end)


def _end_line(node: yaml.Node) -> int:
    mark = node.end_mark
    if mark is None:
        raise RecordError("Zone file node carries no position; cannot edit around it")
    return mark.line


def _scalar(node: yaml.Node, key: str) -> str | None:
    if not isinstance(node, yaml.MappingNode):
        return None
    value = next((v for k, v in node.value if getattr(k, "value", None) == key), None)
    if isinstance(value, yaml.ScalarNode) and value.tag != NULL_TAG:
        return value.value
    return None


def _spans(items: list[yaml.Node], end_line: int) -> list[tuple[yaml.Node, int, int]]:
    """Pair each sequence item with its line span, running to next item (or `end_line`)."""

    if not items:
        return []
    starts = [item.start_mark.line for item in items]
    return list(zip(items, starts, [*starts[1:], end_line], strict=True))


def _item_indent(line: str) -> str:
    match = _ITEM_RE.match(line)
    if match is None:
        raise RecordError(f"Expected a '- type:' item to splice next to, found {line!r}")
    return match.group(1)


def _content_end(lines: list[str], start: int, end: int) -> int:
    """End of `lines[start:end]` without trailing blank and comment lines, which belong to what follows."""

    while end > start and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return end


def _drop_block(lines: list[str], start: int, end: int) -> None:
    """Delete `lines[start:end]`, collapsing blank lines meeting at seam."""

    del lines[start:end]
    if start == 0 or not lines[start - 1].strip():
        while start < len(lines) and not lines[start].strip():
            del lines[start]


def _trim_trailing_blank(lines: list[str]) -> None:
    while lines and not lines[-1].strip():
        lines.pop()
