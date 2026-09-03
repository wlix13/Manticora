"""plan/deploy against a second YamlProvider as target: no network, no token."""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from octodns.record import Record
from octodns.record.change import Create, Update
from octodns.zone import Zone

from manticora.app import ManticoraApp, cli
from manticora.components.dns.controller import DNSError
from manticora.models.enums import Operation
from manticora.models.results import DeploymentPlan, ZoneChange
from tests.component.conftest import EXAMPLE_ZONE, YAML_TARGET_CONFIG


def git(cwd: Path, *args: str) -> None:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args]
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)  # noqa: S603


class TestPlanAndDeploy:
    def test_plan_creates_everything_then_deploy_leaves_nothing(self, yaml_target_project: Path):
        app = ManticoraApp()
        plan = app.dns.plan([])
        assert plan.total_changes == 3
        assert {c.operation for c in plan.zones["example.com."]} == {Operation.CREATE}
        assert "  + www A 3600 1.2.3.4" in plan.discord()
        app.dns.sync(["example.com."], apply=True)
        assert (yaml_target_project / "live" / "example.com.yaml").exists()
        assert app.dns.plan([]).total_changes == 0

    def test_cli_deploys_with_discord_output(self, yaml_target_project: Path):
        args = ["deploy", "--force", "--format", "discord", "-z", "example.com."]
        result = CliRunner().invoke(cli, args, catch_exceptions=False)
        assert result.exit_code == 0
        assert result.output.startswith("```diff\n📋 DNS Deployment Plan: 3 changes") and result.output.endswith(
            "```\n"
        )
        assert (yaml_target_project / "live" / "example.com.yaml").exists()

    def test_discord_output_fits_the_limit(self):
        changes = [
            ZoneChange(
                operation=Operation.CREATE,
                name=f"h{i}",
                type="A",
                ttl=300,
                value="1.2.3.4",
            )
            for i in range(500)
        ]
        changes.append(ZoneChange(operation=Operation.DELETE, name="", type="MX", ttl=300, value="10 mx.example.com."))
        text = DeploymentPlan(zones={"example.com.": changes}).discord(limit=1000)
        assert len(text) <= 1000 and text.endswith("```")
        assert "more, see run logs" in text and "Mail delivery" in text

    def test_cli_renders_plan(self, yaml_target_project: Path):
        result = CliRunner().invoke(cli, ["plan", "-z", "example.com."], catch_exceptions=False)
        assert result.exit_code == 0
        assert "DNS Deployment Plan: 3 changes" in result.output and "Records to Create" in result.output

    def test_update_shows_old_and_new(self):
        zone = Zone("example.com.", set())
        old = Record.new(zone, "www", {"type": "A", "ttl": 60, "value": "1.2.3.4"})
        new = Record.new(zone, "www", {"type": "A", "ttl": 120, "value": "5.6.7.8"})
        change = ZoneChange.from_octodns(Update(old, new))
        assert (change.value, change.ttl_display) == ("1.2.3.4 -> 5.6.7.8", "60 -> 120")

    def test_structured_values_render_as_rdata_text(self):
        zone = Zone("example.com.", set())
        mx = Record.new(zone, "", {"type": "MX", "ttl": 60, "value": {"preference": 10, "exchange": "mx.example.com."}})
        assert ZoneChange.from_octodns(Create(mx)).value == "10 mx.example.com."

    def test_dangerous_deletes_are_warned_once_per_kind(self):
        deletes = [
            ZoneChange(operation=Operation.DELETE, name="", type="MX", ttl=300, value="10 mx.example.com."),
            ZoneChange(operation=Operation.DELETE, name="a", type="MX", ttl=300, value="10 mx2.example.com."),
            ZoneChange(operation=Operation.DELETE, name="t", type="CNAME", ttl=300, value="abc.cfargotunnel.com."),
            ZoneChange(operation=Operation.DELETE, name="x", type="TXT", ttl=300, value="v=spf1 -all"),
            ZoneChange(operation=Operation.CREATE, name="y", type="NS", ttl=300, value="ns1.example.com."),
        ]
        warnings = DeploymentPlan(zones={"example.com.": deletes}).warnings
        assert len(warnings) == 2
        assert "Mail delivery" in warnings[0] and "Argo Tunnel" in warnings[1]


class TestChangedZones:
    def test_reads_git_diff(self, yaml_target_project: Path):
        git(yaml_target_project, "init", "-q", "-b", "main")
        git(yaml_target_project, "add", ".")
        git(yaml_target_project, "commit", "-q", "-m", "base")
        (yaml_target_project / "zones" / "example.com.yaml").write_text(
            EXAMPLE_ZONE + "x:\n  - type: A\n    value: 9.9.9.9\n"
        )
        (yaml_target_project / "zones" / "sub.example.com.yaml").write_text("a:\n  - type: A\n    value: 5.6.7.8\n")
        git(yaml_target_project, "commit", "-q", "-am", "change")
        git(yaml_target_project, "add", ".")
        git(yaml_target_project, "commit", "-q", "-m", "add sub")
        app = ManticoraApp()
        assert app.dns.changed_zones("HEAD~2") == ["example.com.", "sub.example.com."]
        assert app.dns.target_zones("a.com., b.com.", "HEAD~2") == ["a.com.", "b.com."]
        (yaml_target_project / "config.yaml").write_text(YAML_TARGET_CONFIG + "\n")
        git(yaml_target_project, "commit", "-q", "-am", "config")
        assert app.dns.changed_zones("HEAD~1") == []

    def test_outside_git_is_an_error(self, yaml_target_project: Path):
        with pytest.raises(DNSError, match="Git error"):
            ManticoraApp().dns.changed_zones("main")
