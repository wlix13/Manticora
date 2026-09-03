from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from natsort import natsort_keygen
from octodns.manager import Manager
from octodns.provider.yaml import YamlProvider
from octodns.zone import Zone

from manticora.components.records.edit import ZoneFile
from manticora.components.records.errors import RecordError
from manticora.components.records.spec import check_record, entry_data
from manticora.core import OCTODNS_ERRORS, BaseController
from manticora.models.enums import AddOutcome, RemoveOutcome
from manticora.models.records import AddResult, RecordSpec, RemoveResult, Target


if TYPE_CHECKING:
    from collections.abc import Callable

    from manticora.app import ManticoraApp  # noqa: F401


LOG = logging.getLogger(__name__)

YAML_PROVIDER_CLASS = "octodns.provider.yaml.YamlProvider"


class RecordsManager(Manager):
    def _config_providers(self, providers_config: dict[str, Any]) -> dict[str, Any]:
        yaml_only = {name: cfg for name, cfg in providers_config.items() if cfg.get("class") == YAML_PROVIDER_CLASS}
        return super()._config_providers(yaml_only)


class RecordsController(BaseController["ManticoraApp"]):
    def add(self, fqdn: str, spec: RecordSpec, *, zone: str | None = None) -> AddResult:
        """Validate record through octodns, then splice it into its zone file."""

        target = self.resolve(fqdn, zone)
        path = self.path(target.zone)
        zone_file = ZoneFile(self._read(path))
        if zone_file.has_record(target.name, spec.type):
            return AddResult(outcome=AddOutcome.EXISTS, target=target)
        check_record(spec, self._zone(target.zone), target.name, self._provider.default_ttl)
        data = entry_data(spec, escaped_semicolons=self._provider.escaped_semicolons)
        edited = zone_file.add_record(target.name, data, order=self._order)
        created = not path.exists()
        self._write(path, edited.text)
        return AddResult(
            outcome=edited.outcome,
            target=target,
            created_file=created,
            validation_error=self._revalidate(target.zone),
        )

    def remove(self, fqdn: str, record_type: str | None = None, *, zone: str | None = None) -> RemoveResult:
        """Drop records of name (all, or one type) from its zone file, and entry when left empty."""

        target = self.resolve(fqdn, zone)
        path = self.path(target.zone)
        zone_file = ZoneFile(self._read(path))
        entry = zone_file.entry(target.name)
        if entry is None or not entry.of_type(record_type):
            return RemoveResult(outcome=RemoveOutcome.MISSING, target=target)
        edited = zone_file.remove_record(target.name, record_type)
        self._write(path, edited.text)
        return RemoveResult(
            outcome=edited.outcome,
            target=target,
            types=edited.types,
            validation_error=self._revalidate(target.zone),
        )

    def resolve(self, fqdn: str, zone: str | None = None) -> Target:
        """Split FQDN into configured zone owning it and record name, preferring longest zone."""

        zones = self.zones
        if zone is not None:
            zone = zone.rstrip(".").lower() + "."
            if zone not in zones:
                raise RecordError(f"Zone {zone!r} is not configured; configured zones: {', '.join(zones)}")
        candidates = (zone,) if zone is not None else sorted(zones, key=len, reverse=True)
        host = fqdn.rstrip(".")
        for candidate in candidates:
            if host.lower() == candidate[:-1]:
                return Target(zone=candidate, name="")
            if host.lower().endswith("." + candidate[:-1]):
                return Target(zone=candidate, name=host[: -len(candidate)])
        scope = f"zone {zone}" if zone is not None else f"any configured zone ({', '.join(zones)})"
        raise RecordError(f"{fqdn!r} is not under {scope}")

    def path(self, zone: str) -> Path:
        return self.app.project_root / self._provider.directory / f"{zone}yaml"

    @cached_property
    def zones(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                name.lower()
                for name, zone in self._manager.config["zones"].items()
                if not name.startswith("*") and not (isinstance(zone, dict) and "alias" in zone)
            )
        )

    @cached_property
    def _manager(self) -> Manager:
        try:
            return self.app.config.manager(RecordsManager)
        except OCTODNS_ERRORS as e:
            raise RecordError(f"Cannot load {self.app.config_path}: {e}") from e

    @cached_property
    def _provider(self) -> YamlProvider:
        providers = [p for p in self._manager.providers.values() if isinstance(p, YamlProvider)]
        if len(providers) != 1:
            raise RecordError(
                f"Expected exactly one {YAML_PROVIDER_CLASS} provider in the config, found {len(providers)}"
            )
        LOG.debug(f"Zone files in {providers[0].directory}; zones: {', '.join(self.zones)}")
        return providers[0]

    @property
    def _order(self) -> Callable[[str], Any] | None:
        if not self._provider.enforce_order:
            return None
        return natsort_keygen() if self._provider.order_mode == "natural" else (lambda key: key)

    def _zone(self, name: str) -> Zone:
        return Zone(name, self._manager.configured_sub_zones(name))

    def _read(self, path: Path) -> str:
        """Zone file text, empty for zone whose file does not exist yet."""

        try:
            return path.read_text()
        except FileNotFoundError:
            return ""
        except OSError as e:
            raise RecordError(f"Failed to read zone file {path}: {e}") from e

    def _write(self, path: Path, text: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text)
            tmp.replace(path)
        except OSError as e:
            raise RecordError(f"Failed to write zone file {path}: {e}") from e

    def _revalidate(self, name: str) -> str | None:
        """Load zone file back through octodns and its zone validators, error text when it no longer passes."""

        zone = self._zone(name)
        try:
            with self.app.config.in_project():
                self._provider.populate(zone)
            zone.validate()
        except OCTODNS_ERRORS as e:
            return str(e)
        return None
