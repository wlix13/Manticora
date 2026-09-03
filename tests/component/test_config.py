from pathlib import Path

import pytest

from manticora.app import ManticoraApp
from manticora.components.records.errors import RecordError
from manticora.models.enums import AddOutcome
from manticora.models.records import RecordSpec
from tests.component.conftest import CONFIG


class TestValidate:
    def test_passes_and_fails_with_octodns_reason(self, yaml_target_project: Path):
        assert ManticoraApp().config.validate().ok
        (yaml_target_project / "zones" / "example.com.yaml").write_text("www:\n  - type: A\n    value: 1.2.3\n")
        result = ManticoraApp().config.validate()
        assert result.error is not None and "1.2.3" in result.error

    def test_provider_secrets_are_required_only_here(self, project: Path):
        result = ManticoraApp().config.validate()
        assert result.error is not None and "CLOUDFLARE_API_TOKEN" in result.error


class TestManagerValidatorsReachRecords:
    def test_disable_validators_from_config_is_honoured(self, project: Path, app: ManticoraApp):
        srv = RecordSpec(type="SRV", values=("10 5 5060 sip.example.com.",))
        with pytest.raises(RecordError, match="invalid name for SRV"):
            app.records.add("foo.example.com", srv)
        relaxed = CONFIG.replace(
            "manager:\n", "manager:\n  validators:\n    record:\n      disable_validators:\n        SRV: [srv-name]\n"
        )
        (project / "config.yaml").write_text(relaxed)
        assert ManticoraApp().records.add("foo.example.com", srv).outcome == AddOutcome.CREATED_NAME
