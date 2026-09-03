from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from octodns.record.base import ValueMixin, ValuesMixin
from rich.console import Group, RenderableType
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from manticora.core import BaseModel

from .enums import Operation


if TYPE_CHECKING:
    from octodns.provider.plan import Plan
    from octodns.record import Record
    from octodns.record.change import Change


class ValidationResult(BaseModel):
    """Outcome of loading config and every zone through octodns, error text when that failed."""

    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def __rich__(self) -> Panel:
        if self.error is None:
            return Panel(
                "[green bold]✅ All validations passed![/green bold]",
                title="Validation Results",
                border_style="green",
            )
        return Panel(
            f"❌ {escape(self.error)}",
            title="Validation Errors",
            border_style="red",
        )


class Style(BaseModel):
    """How one operation shows up: diff marker, rich colour, section header."""

    marker: str
    color: str
    header: str


STYLE = {
    Operation.CREATE: Style(
        marker="+",
        color="green",
        header="➕ Records to Create",
    ),
    Operation.UPDATE: Style(
        marker="~",
        color="yellow",
        header="🔄 Records to Update",
    ),
    Operation.DELETE: Style(
        marker="-",
        color="red",
        header="❌ Records to Delete",
    ),
}


class ZoneChange(BaseModel):
    """One planned record change, value and TTL spelled `old -> new` when an update alters them."""

    operation: Operation
    name: str
    type: str
    ttl: int
    value: str
    new_ttl: int | None = None

    @property
    def ttl_display(self) -> str:
        return f"{self.ttl} -> {self.new_ttl}" if self.new_ttl is not None else str(self.ttl)

    @classmethod
    def from_octodns(cls, change: Change) -> ZoneChange:
        old, new = change.existing, change.new
        shown = new if old is None else old
        values = [_values(record) for record in (old, new) if record is not None]
        return cls(
            operation=Operation(type(change).__name__),
            name=shown.name,
            type=shown._type,
            ttl=shown.ttl,
            value=values[0] if len(set(values)) == 1 else " -> ".join(values),
            new_ttl=new.ttl if old is not None and new is not None and new.ttl != old.ttl else None,
        )


def _values(record: Record) -> str:
    if isinstance(record, ValuesMixin):
        return "\n".join(value.to_rdata_text() for value in record.values)
    return record.value.to_rdata_text() if isinstance(record, ValueMixin) else ""


class DeploymentPlan(BaseModel):
    """Planned changes per zone."""

    zones: dict[str, list[ZoneChange]] = {}

    @classmethod
    def from_plans(cls, plans: list[tuple[object, Plan]]) -> DeploymentPlan:
        zones: dict[str, list[ZoneChange]] = {}
        for _target, plan in plans:
            changes = zones.setdefault(plan.desired.decoded_name, [])
            changes.extend(ZoneChange.from_octodns(change) for change in plan.changes)
        return cls(zones=zones)

    @property
    def total_changes(self) -> int:
        return sum(len(changes) for changes in self.zones.values())

    @property
    def warnings(self) -> list[str]:
        """One line per kind of dangerous delete found."""

        found = [danger for changes in self.zones.values() for change in changes if (danger := _danger(change))]
        return [f"⚠️  Detected potentially dangerous change: {danger}" for danger in dict.fromkeys(found)]

    def discord(self, limit: int = 3800) -> str:
        """Plan as Discord diff code block, cut to `limit` characters."""

        if not self.total_changes:
            return "```diff\n✅ No DNS changes detected\n```"
        several = len(self.zones) > 1
        head = [
            "```diff",
            f"📋 DNS Deployment Plan: {self.total_changes} changes",
            f"🌐 Zone{'s' if several else ''}: {', '.join(self.zones)}",
            "",
        ]
        body: list[str] = []
        for operation in Operation:
            style = STYLE[operation]
            items = [
                f"  {style.marker} {f'[{zone}] ' if several else ''}{c.name} {c.type} {c.ttl_display} {c.value}"
                for zone, changes in self.zones.items()
                for c in changes
                if c.operation is operation
            ]
            if items:
                body += [f"{style.header}:", *items, ""]
        tail = ["🚨 DANGEROUS CHANGES DETECTED!", *self.warnings, ""] if self.warnings else []
        tail.append("```")
        room = limit - len("\n".join(head + tail)) - 40  # 40: the "… more" line
        kept: list[str] = []
        for line in body:
            room -= len(line) + 1
            if room < 0:
                left = sum(item.startswith("  ") for item in body[len(kept) :])
                kept.append(f"  … {left} more, see run logs")
                break
            kept.append(line)
        return "\n".join(head + kept + tail)

    def __rich__(self) -> Group:
        parts: list[RenderableType] = [
            f"\n[bold cyan]📋 DNS Deployment Plan: {self.total_changes} changes[/bold cyan]\n"
        ]
        for zone, changes in self.zones.items():
            parts.append(f"[bold blue]🌐 Zone: {zone}[/bold blue]")
            for operation, rows in _sections(changes):
                style = STYLE[operation]
                table = Table(header_style=f"bold {style.color}", box=None)
                for column, color in (("Name", "cyan"), ("Type", "magenta"), ("TTL", "yellow"), ("Value", "white")):
                    table.add_column(column, style=color)
                for change in rows:
                    table.add_row(change.name, change.type, change.ttl_display, escape(change.value))
                parts += [f"  [{style.color}]{style.header}[/{style.color}]", table, ""]
        if self.warnings:
            parts += [
                Panel(
                    "\n".join(self.warnings),
                    title="🚨 DANGEROUS CHANGES DETECTED",
                    border_style="red bold",
                ),
                "",
            ]
        return Group(*parts)


def _sections(changes: list[ZoneChange]) -> Iterator[tuple[Operation, list[ZoneChange]]]:
    """Non-empty groups of `changes` per operation, in `Operation` order."""

    for operation in Operation:
        if rows := [change for change in changes if change.operation is operation]:
            yield operation, rows


def _danger(change: ZoneChange) -> str | None:
    """What deleting this record breaks, None when nothing worth warning about."""

    if change.operation is not Operation.DELETE:
        return None
    match change.type:
        case "MX":
            return "Mail delivery (MX records) deletion"
        case "NS":
            return "Name server records deletion"
        case "A" | "AAAA":
            return f"Domain {change.type} records deletion"
        case "CNAME" if "cfargotunnel.com" in change.value:
            return "Cloudflare Argo Tunnel records deletion"
    return None
