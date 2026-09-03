from __future__ import annotations

from typing import TYPE_CHECKING

import rich_click as click
from rich.panel import Panel

from manticora.core import BaseComponent, console

from .controller import DNSController, DNSError


if TYPE_CHECKING:
    from manticora.app import ManticoraApp


class DNSComponent(BaseComponent["ManticoraApp", DNSController]):
    name = "dns"
    controller_class = DNSController

    @classmethod
    def expose_cli(cls, base: click.Group) -> None:
        @base.command()
        @click.option(
            "--zones",
            "-z",
            help="Comma-separated zones (e.g., example.com.,example.dev.), default: zones changed since --base-ref.",
        )
        @click.option(
            "--base-ref",
            default="main",
            help="Git reference to compare against for change detection.",
        )
        @click.option(
            "--format",
            "output_format",
            default="human",
            type=click.Choice(["human", "discord"]),
            help="Output format.",
        )
        @click.pass_obj
        def plan(app: ManticoraApp, zones: str | None, base_ref: str, output_format: str) -> None:
            """Generate deployment plan for DNS changes."""

            result = app.dns.plan(app.dns.target_zones(zones, base_ref))
            if output_format == "discord":
                click.echo(result.discord())
            else:
                console.print(result)

        @base.command()
        @click.option(
            "--zones",
            "-z",
            help="Comma-separated zones (e.g., example.com.,example.dev.), default: zones changed since --base-ref.",
        )
        @click.option(
            "--base-ref",
            default="main",
            help="Git reference to compare against for change detection.",
        )
        @click.option(
            "--dry-run",
            is_flag=True,
            help="Show what would be deployed without doing it.",
        )
        @click.option(
            "--force",
            is_flag=True,
            help="Deploy without confirmation prompt.",
        )
        @click.option(
            "--format",
            "output_format",
            default="human",
            type=click.Choice(["human", "discord"]),
            help="Output format, discord prints the plan block and no result panel.",
        )
        @click.pass_obj
        def deploy(
            app: ManticoraApp,
            zones: str | None,
            base_ref: str,
            dry_run: bool,
            force: bool,
            output_format: str,
        ) -> None:
            """Deploy DNS changes."""

            validation = app.config.validate()
            if not validation.ok:
                console.print(validation)
                raise DNSError("Deployment aborted: fix validation errors first")
            targets = app.dns.target_zones(zones, base_ref)
            result = app.dns.plan(targets)
            if output_format == "discord":
                click.echo(result.discord())
            elif result.total_changes:
                console.print(result)
            else:
                console.print("[green]✅ No DNS changes detected[/green]")
            if not result.total_changes:
                return
            if not dry_run:
                if not force and not click.confirm("Do you want to proceed with the deployment?"):
                    return
                app.dns.sync(targets, apply=True)
            if output_format == "human":
                message = "Dry-run completed successfully" if dry_run else "DNS changes deployed successfully"
                console.print(
                    Panel(
                        f"[green bold]✅ {message}[/green bold]\nZones: {', '.join(result.zones)}",
                        border_style="green",
                    )
                )
