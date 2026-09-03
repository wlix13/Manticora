from __future__ import annotations

from typing import TYPE_CHECKING

import rich_click as click
from pydantic import ValidationError
from rich.markup import escape

from manticora.core import BaseComponent, console
from manticora.models.enums import AddOutcome, RemoveOutcome
from manticora.models.records import RECORD_TYPES, RecordSpec

from .controller import RecordsController


if TYPE_CHECKING:
    from manticora.app import ManticoraApp


class RecordsComponent(BaseComponent["ManticoraApp", RecordsController]):
    name = "records"
    controller_class = RecordsController

    @classmethod
    def expose_cli(cls, base: click.Group) -> None:
        @base.group()
        def records() -> None:
            """Edit records in zone files in place."""

        @records.command("add")
        @click.argument("fqdn")
        @click.argument("record_type", metavar="TYPE", type=click.Choice(RECORD_TYPES, case_sensitive=False))
        @click.argument("values", metavar="VALUE...", nargs=-1, required=True)
        @click.option(
            "--ttl",
            type=click.IntRange(min=0),
            default=None,
            help="TTL in seconds (default: provider default).",
        )
        @click.option(
            "--proxied",
            is_flag=True,
            help="Proxy through Cloudflare (`octodns.cloudflare.proxied`).",
        )
        @click.option(
            "--lenient",
            is_flag=True,
            help="Relax octodns checks for this record (`octodns.lenient`).",
        )
        @click.option(
            "--zone",
            help="Zone owning FQDN (default: longest configured zone it falls under).",
        )
        @click.pass_obj
        def add_record(
            app: ManticoraApp,
            fqdn: str,
            record_type: str,
            values: tuple[str, ...],
            ttl: int | None,
            proxied: bool,
            lenient: bool,
            zone: str | None,
        ) -> None:
            """Add TYPE record for FQDN to its zone file.

            \b
            Values use zone-file syntax: `10 mx.example.com.` for MX, `4 2 <hex>` for SSHFP,
            `0 issue letsencrypt.org` for CAA. TXT values are given unescaped.
            """

            try:
                spec = RecordSpec(type=record_type, values=values, ttl=ttl, proxied=proxied, lenient=lenient)
            except ValidationError as e:
                reasons = "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
                raise click.BadParameter(reasons, param_hint="VALUE...") from e
            result = app.records.add(fqdn, spec, zone=zone)
            shown = f"{record_type} {result.target.fqdn}"
            if result.outcome == AddOutcome.EXISTS:
                console.print(f"  [yellow]skipped[/yellow]  {shown} is already in zone {result.target.zone}")
                return
            where = "new name in" if result.outcome == AddOutcome.CREATED_NAME else "to"
            detail = escape(", ".join(values))
            console.print(f"  [green]added[/green]    {shown} {where} zone {result.target.zone}  [dim]{detail}[/dim]")
            if result.created_file:
                console.print(f"  [green]created[/green]  zone file for {result.target.zone}")
            _warn_invalid(result.validation_error)

        @records.command("remove")
        @click.argument("fqdn")
        @click.argument(
            "record_type",
            metavar="[TYPE]",
            type=click.Choice(RECORD_TYPES, case_sensitive=False),
            required=False,
        )
        @click.option(
            "--zone",
            help="Zone owning FQDN (default: longest configured zone it falls under).",
        )
        @click.pass_obj
        def remove_record(app: ManticoraApp, fqdn: str, record_type: str | None, zone: str | None) -> None:
            """Remove FQDN's TYPE record (every record of FQDN without TYPE) from its zone file."""

            result = app.records.remove(fqdn, record_type, zone=zone)
            shown = f"{record_type} {result.target.fqdn}" if record_type else result.target.fqdn
            if result.outcome == RemoveOutcome.MISSING:
                console.print(f"  [yellow]skipped[/yellow]  {shown} is not in zone {result.target.zone}")
                return
            types = ", ".join(result.types)
            what = (
                f"{result.target.fqdn} ({types}) and its now-empty entry"
                if result.outcome == RemoveOutcome.REMOVED_NAME
                else f"{types} {result.target.fqdn}"
            )
            console.print(f"  [green]removed[/green]  {what} from zone {result.target.zone}")
            _warn_invalid(result.validation_error)


def _warn_invalid(error: str | None) -> None:
    if error is not None:
        console.print(
            f"\n[bold yellow]Warning:[/bold yellow] zone file was written but no longer loads:\n{escape(error)}"
        )
