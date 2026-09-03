from pathlib import Path

from click.testing import CliRunner

from manticora.app import cli
from tests.component.conftest import EXAMPLE_ZONE


def invoke(*args: str):
    return CliRunner().invoke(cli, args, catch_exceptions=False)


class TestAddRecord:
    def test_adds_and_reports(self, project: Path):
        result = invoke("records", "add", "www.example.com", "txt", "v=spf1 -all")
        assert result.exit_code == 0
        assert "added" in result.output and "TXT www.example.com." in result.output
        assert "  - type: TXT\n    value: v=spf1 -all\n" in (project / "zones" / "example.com.yaml").read_text()

    def test_reports_new_name_and_created_zone_file(self, project: Path):
        result = invoke("records", "add", "a.sub.example.com", "A", "5.6.7.8", "--ttl", "60")
        assert result.exit_code == 0
        assert "new name in zone sub.example.com." in result.output
        assert "created" in result.output
        assert (
            project / "zones" / "sub.example.com.yaml"
        ).read_text() == "a:\n  - type: A\n    ttl: 60\n    value: 5.6.7.8\n"

    def test_skips_existing_record(self, project: Path):
        result = invoke("records", "add", "www.example.com", "A", "9.9.9.9")
        assert result.exit_code == 0
        assert "skipped" in result.output
        assert (project / "zones" / "example.com.yaml").read_text() == EXAMPLE_ZONE

    def test_warns_when_zone_no_longer_loads(self, project: Path):
        result = invoke("records", "add", "www.example.com", "CNAME", "other.example.org.")
        assert result.exit_code == 0
        assert "no longer loads" in result.output
        assert "cannot coexist" in result.output

    def test_unknown_type_is_a_usage_error(self, project: Path):
        result = CliRunner().invoke(cli, ["records", "add", "www.example.com", "BOGUS", "x"])
        assert result.exit_code == 2


class TestRemoveRecord:
    def test_removes_one_type(self, project: Path):
        result = invoke("records", "remove", "www.example.com", "a")
        assert result.exit_code == 0
        assert "removed" in result.output and "A www.example.com." in result.output
        assert "  - type: A\n" not in (project / "zones" / "example.com.yaml").read_text()

    def test_removes_whole_entry(self, project: Path):
        result = invoke("records", "remove", "www.example.com")
        assert result.exit_code == 0
        assert "www.example.com. (A, AAAA) and its now-empty entry" in result.output

    def test_skips_missing(self, project: Path):
        result = invoke("records", "remove", "ghost.example.com")
        assert result.exit_code == 0
        assert "skipped" in result.output
