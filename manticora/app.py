from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import rich_click as click
from rich.logging import RichHandler

from manticora import __version__
from manticora.components.config.component import ConfigComponent
from manticora.components.dns.component import DNSComponent
from manticora.components.records.component import RecordsComponent
from manticora.core import BaseApplication, err, find_project_root


if TYPE_CHECKING:
    from manticora.components.config.controller import ConfigController
    from manticora.components.dns.controller import DNSController
    from manticora.components.records.controller import RecordsController

click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.SHOW_ARGUMENTS = True
click.rich_click.GROUP_ARGUMENTS_OPTIONS = True
click.rich_click.STYLE_ERRORS_SUGGESTION = "dim italic"
click.rich_click.MAX_WIDTH = 100
click.rich_click.COMMAND_GROUPS = {
    "manticora": [
        {
            "name": "Deploy",
            "commands": ["validate", "plan", "deploy"],
        },
        {
            "name": "Records",
            "commands": ["records"],
        },
    ],
}

LOG = logging.getLogger(__name__)


class ManticoraApp(BaseApplication["ManticoraApp"]):
    default_components = (ConfigComponent, DNSComponent, RecordsComponent)

    config: ConfigController
    dns: DNSController
    records: RecordsController

    def __init__(self, config_file: str = "config.yaml") -> None:
        self.project_root = find_project_root()
        self.config_path = self.project_root / config_file
        super().__init__()


@click.group()
@click.version_option(__version__, "-V", "--version")
@click.option(
    "--config",
    "-c",
    default="config.yaml",
    help="Path to OctoDNS config file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Quiet mode, drop octodns warnings from stderr",
)
@click.pass_context
def cli(ctx: click.Context, config: str, verbose: bool, quiet: bool) -> None:
    """Manticora - GitOps DNS Manager CLI."""

    handler = RichHandler(console=err, show_time=False, show_path=False)
    # octodns logs a traceback for every failure it also raises, and those are rendered as errors already
    handler.addFilter(lambda record: record.levelno < logging.ERROR or record.name.startswith("manticora"))
    logging.basicConfig(level=logging.ERROR if quiet else logging.WARNING, format="%(message)s", handlers=[handler])
    logging.getLogger("manticora").setLevel(logging.DEBUG if verbose else logging.INFO)
    ctx.obj = ManticoraApp(config_file=config)
    LOG.debug(f"Project root: {ctx.obj.project_root}")
    LOG.debug(f"Config path: {ctx.obj.config_path}")


ManticoraApp.register_cli(cli)
