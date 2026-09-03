from pathlib import Path

import pytest

from manticora.app import ManticoraApp
from manticora.components.records.errors import RecordError
from manticora.models.enums import AddOutcome, RemoveOutcome
from manticora.models.records import RecordSpec, Target
from tests.component.conftest import CONFIG, EXAMPLE_ZONE


WWW_TXT_BLOCK = """\
  - type: AAAA
    value: "2001:db8::1"
  - type: TXT
    value: v=spf1 -all
# Web section <--
"""


def zone_text(project: Path, zone: str = "example.com.") -> str:
    return (project / "zones" / f"{zone}yaml").read_text()


class TestResolve:
    @pytest.mark.parametrize(
        ("fqdn", "target"),
        [
            ("www.example.com", Target(zone="example.com.", name="www")),
            ("www.example.com.", Target(zone="example.com.", name="www")),
            ("example.com", Target(zone="example.com.", name="")),
            ("a.sub.example.com", Target(zone="sub.example.com.", name="a")),
            ("WWW.Example.COM", Target(zone="example.com.", name="WWW")),
        ],
    )
    def test_longest_configured_zone_owns_the_name(self, app: ManticoraApp, fqdn, target):
        assert app.records.resolve(fqdn) == target

    def test_explicit_zone_overrides_the_longest_match(self, app: ManticoraApp):
        assert app.records.resolve("a.sub.example.com", zone="example.com") == Target(zone="example.com.", name="a.sub")

    def test_rejects_unknown_zone_and_names_outside_every_zone(self, app: ManticoraApp):
        with pytest.raises(RecordError, match="not configured"):
            app.records.resolve("www.example.com", zone="example.net")
        with pytest.raises(RecordError, match="not under any configured zone"):
            app.records.resolve("www.example.net")
        with pytest.raises(RecordError, match="not under zone sub.example.com."):
            app.records.resolve("www.example.com", zone="sub.example.com")


class TestAdd:
    def test_appends_to_existing_name_and_zone_still_loads(self, app: ManticoraApp, project: Path):
        result = app.records.add("www.example.com", RecordSpec(type="TXT", values=("v=spf1 -all",)))
        assert result.outcome == AddOutcome.ADDED
        assert result.target == Target(zone="example.com.", name="www")
        assert result.validation_error is None
        assert not result.created_file
        assert zone_text(project) == EXAMPLE_ZONE.replace(
            '  - type: AAAA\n    value: "2001:db8::1"\n# Web section <--\n', WWW_TXT_BLOCK
        )

    def test_creates_new_name_with_ttl_and_metadata(self, app: ManticoraApp, project: Path):
        spec = RecordSpec(type="MX", values=("10 mx1.example.com.", "20 mx2.example.com."), ttl=300, proxied=True)
        result = app.records.add("mail.example.com.", spec)
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.validation_error is None
        assert zone_text(project) == EXAMPLE_ZONE + (
            "\nmail:\n  - type: MX\n    ttl: 300\n    values:\n"
            "      - preference: 10\n        exchange: mx1.example.com.\n"
            "      - preference: 20\n        exchange: mx2.example.com.\n"
            "    octodns:\n      cloudflare:\n        proxied: true\n"
        )

    def test_creates_the_zone_file_of_a_configured_zone(self, app: ManticoraApp, project: Path):
        result = app.records.add("a.sub.example.com", RecordSpec(type="A", values=("5.6.7.8",)))
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.created_file
        assert result.validation_error is None
        assert zone_text(project, "sub.example.com.") == "a:\n  - type: A\n    value: 5.6.7.8\n"

    def test_existing_record_is_skipped_without_writing(self, app: ManticoraApp, project: Path):
        result = app.records.add("www.example.com", RecordSpec(type="A", values=("9.9.9.9",)))
        assert result.outcome == AddOutcome.EXISTS
        assert zone_text(project) == EXAMPLE_ZONE

    @pytest.mark.parametrize(
        ("fqdn", "spec", "zone", "match"),
        [
            ("bad.example.com", RecordSpec(type="A", values=("1.2.3",)), None, 'invalid IPv4 address "1.2.3"'),
            ("bad name.example.com", RecordSpec(type="A", values=("1.2.3.4",)), None, "whitespace is not allowed"),
            ("a.sub.example.com", RecordSpec(type="A", values=("1.2.3.4",)), "example.com", "under a managed subzone"),
        ],
    )
    def test_invalid_records_are_refused_before_writing(
        self, app: ManticoraApp, project: Path, fqdn, spec, zone, match
    ):
        with pytest.raises(RecordError, match=match):
            app.records.add(fqdn, spec, zone=zone)
        assert zone_text(project) == EXAMPLE_ZONE

    def test_zone_level_conflicts_are_written_with_a_warning(self, app: ManticoraApp, project: Path):
        result = app.records.add("www.example.com", RecordSpec(type="CNAME", values=("other.example.org.",)))
        assert result.outcome == AddOutcome.ADDED
        assert result.validation_error is not None
        assert "CNAME at www.example.com. cannot coexist" in result.validation_error
        assert "  - type: CNAME\n    value: other.example.org.\n# Web section <--\n" in zone_text(project)

    def test_edits_keep_working_while_the_zone_is_invalid(self, app: ManticoraApp):
        app.records.add("www.example.com", RecordSpec(type="CNAME", values=("other.example.org.",)))
        result = app.records.add("api.example.com", RecordSpec(type="A", values=("5.6.7.8",)))
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.validation_error is not None


class TestRemove:
    def test_removes_one_type_and_keeps_the_entry(self, app: ManticoraApp, project: Path):
        result = app.records.remove("www.example.com", "A")
        assert result.outcome == RemoveOutcome.REMOVED
        assert result.types == ("A",)
        assert result.validation_error is None
        assert zone_text(project) == EXAMPLE_ZONE.replace("  - type: A\n    value: 1.2.3.4\n", "")

    def test_removes_every_record_and_the_entry(self, app: ManticoraApp, project: Path):
        result = app.records.remove("www.example.com")
        assert result.outcome == RemoveOutcome.REMOVED_NAME
        assert result.types == ("A", "AAAA")
        assert zone_text(project).endswith("# Web section -->\n# Web section <--\n")

    def test_missing_name_type_or_zone_file_is_skipped(self, app: ManticoraApp, project: Path):
        assert app.records.remove("ghost.example.com").outcome == RemoveOutcome.MISSING
        assert app.records.remove("www.example.com", "TXT").outcome == RemoveOutcome.MISSING
        assert app.records.remove("a.sub.example.com").outcome == RemoveOutcome.MISSING
        assert zone_text(project) == EXAMPLE_ZONE
        assert not (project / "zones" / "sub.example.com.yaml").exists()

    def test_add_then_remove_restores_the_file(self, app: ManticoraApp, project: Path):
        app.records.add("www.example.com", RecordSpec(type="TXT", values=("v=spf1 -all",)))
        app.records.add("mail.example.com", RecordSpec(type="MX", values=("10 mx.example.com.",)))
        app.records.remove("www.example.com", "TXT")
        app.records.remove("mail.example.com")
        assert zone_text(project) == EXAMPLE_ZONE


ORDERED_ZONE = """\
'':
  - type: TXT
    value: v=spf1 -all

www:
  - octodns:
      cloudflare:
        proxied: true
    type: A
    value: 1.2.3.4
"""


class TestEnforcedOrder:
    @pytest.fixture()
    def app(self, project: Path) -> ManticoraApp:
        (project / "config.yaml").write_text(CONFIG.replace("enforce_order: false", "enforce_order: true"))
        (project / "zones" / "example.com.yaml").write_text(ORDERED_ZONE)
        return ManticoraApp()

    def test_new_names_and_keys_are_inserted_in_sorted_order(self, app: ManticoraApp, project: Path):
        result = app.records.add("mail.example.com", RecordSpec(type="A", values=("5.6.7.8",), ttl=60, proxied=True))
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.validation_error is None
        assert zone_text(project) == ORDERED_ZONE.replace(
            "    value: v=spf1 -all\n",
            "    value: v=spf1 -all\n\nmail:\n  - octodns:\n      cloudflare:\n        proxied: true\n"
            "    ttl: 60\n    type: A\n    value: 5.6.7.8\n",
        )

    def test_appended_records_keep_the_file_loadable(self, app: ManticoraApp, project: Path):
        result = app.records.add("www.example.com", RecordSpec(type="TXT", values=("x",), ttl=60))
        assert result.validation_error is None
        assert zone_text(project) == ORDERED_ZONE + "  - ttl: 60\n    type: TXT\n    value: x\n"
