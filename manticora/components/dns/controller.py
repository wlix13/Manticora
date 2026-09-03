from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from octodns.provider.plan import _PlanOutput

from manticora.core import OCTODNS_ERRORS, BaseController, Error
from manticora.models.results import DeploymentPlan


if TYPE_CHECKING:
    from manticora.app import ManticoraApp  # noqa: F401

LOG = logging.getLogger(__name__)


class DNSError(Error):
    """Git or octodns step failed."""


class _Capture(_PlanOutput):
    """Plan output keeping `(target, Plan)` pairs instead of printing them."""

    def __init__(self) -> None:
        super().__init__("capture")
        self.plans: list = []

    def run(self, plans: list, *args: object, **kwargs: object) -> None:
        self.plans = plans


class DNSController(BaseController["ManticoraApp"]):
    def target_zones(self, zones: str | None, base_ref: str) -> list[str]:
        """Zones to act on: comma-separated `zones`, else those changed since `base_ref`. Empty means all."""

        if zones:
            return [zone.strip() for zone in zones.split(",")]
        return self.changed_zones(base_ref)

    def changed_zones(self, base_ref: str) -> list[str]:
        """Zones whose file changed since `base_ref`, empty (all zones) when config.yaml itself changed."""

        cmd = ["git", "diff", "--name-only", base_ref, "HEAD"]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=self.app.project_root,
            )
        except OSError as e:
            raise DNSError(f"Cannot run git: {e}") from e
        except subprocess.CalledProcessError as e:
            raise DNSError(f"Git error (exit {e.returncode}): {e.stderr.strip()}") from e
        files = proc.stdout.splitlines()
        LOG.debug(f"Changed files: {files}")
        if "config.yaml" in files:
            return []
        return [Path(file).stem + "." for file in files if file.startswith("zones/") and file.endswith(".yaml")]

    def plan(self, zones: list[str]) -> DeploymentPlan:
        return self.sync(zones, apply=False)

    def sync(self, zones: list[str], *, apply: bool) -> DeploymentPlan:
        """Plan `zones` (all when empty) and, with `apply`, push changes to their targets."""

        capture = _Capture()
        try:
            with self.app.config.in_project():
                manager = self.app.config.manager()
                manager.plan_outputs = {"capture": capture}
                # force skips octodns' unsafe-plan thresholds, which would reject bulk changes
                manager.sync(eligible_zones=zones, dry_run=not apply, force=True)
        except OCTODNS_ERRORS as e:
            raise DNSError(f"{'Deployment' if apply else 'Plan'} failed: {e}") from e
        return DeploymentPlan.from_plans(capture.plans)
