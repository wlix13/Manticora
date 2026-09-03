import pytest
from octodns.zone import Zone
from pydantic import ValidationError

from manticora.components.records.errors import RecordError
from manticora.components.records.spec import check_record, entry_data
from manticora.models.records import RECORD_TYPES, RecordSpec, takes_single_value


def spec(record_type: str, *values: str, **fields) -> RecordSpec:
    return RecordSpec(type=record_type, values=values, **fields)


class TestEntryData:
    def test_single_value_uses_value_key(self):
        assert entry_data(spec("A", "1.2.3.4")) == {"type": "A", "value": "1.2.3.4"}

    def test_several_values_use_values_key(self):
        assert entry_data(spec("A", "1.2.3.4", "5.6.7.8")) == {"type": "A", "values": ["1.2.3.4", "5.6.7.8"]}

    def test_ttl_and_metadata_follow_in_file_order(self):
        data = entry_data(spec("AAAA", "100::", ttl=300, proxied=True, lenient=True))
        assert list(data) == ["type", "ttl", "value", "octodns"]
        assert data["octodns"] == {"lenient": True, "cloudflare": {"proxied": True}}

    def test_structured_values_are_parsed_from_rdata_text(self):
        assert entry_data(spec("MX", "10 mx.example.com."))["value"] == {
            "preference": 10,
            "exchange": "mx.example.com.",
        }
        assert entry_data(spec("SSHFP", "4 2 0AAF"))["value"] == {
            "algorithm": 4,
            "fingerprint_type": 2,
            "fingerprint": "0AAF",
        }

    def test_txt_semicolons_are_escaped_unless_the_provider_keeps_them_raw(self):
        txt = spec("TXT", "v=DMARC1; p=none")
        assert entry_data(txt)["value"] == r"v=DMARC1\; p=none"
        assert entry_data(txt, escaped_semicolons=False)["value"] == "v=DMARC1; p=none"

    def test_rejects_unparsable_rdata(self):
        with pytest.raises(RecordError, match="Invalid MX value 'mx.example.com.'"):
            entry_data(spec("MX", "mx.example.com."))


class TestRecordSpec:
    def test_registered_types_are_uppercase_and_include_the_common_ones(self):
        assert {"A", "AAAA", "CNAME", "MX", "TXT", "SSHFP"} <= set(RECORD_TYPES)
        assert takes_single_value("CNAME") and not takes_single_value("A")

    def test_type_is_normalised_to_uppercase(self):
        assert spec("txt", "x").type == "TXT"

    @pytest.mark.parametrize(
        ("record_type", "values", "match"),
        [
            ("BOGUS", ("x",), "unknown record type"),
            ("A", (), "at least one value"),
            ("CNAME", ("a.example.org.", "b.example.org."), "exactly one value"),
        ],
    )
    def test_rejects_shapes_octodns_cannot_take(self, record_type, values, match):
        with pytest.raises(ValidationError, match=match):
            spec(record_type, *values)

    def test_negative_ttl_is_rejected(self):
        with pytest.raises(ValidationError, match="ttl"):
            spec("A", "1.2.3.4", ttl=-1)


class TestCheckRecord:
    def test_valid_record_passes(self):
        check_record(spec("A", "1.2.3.4"), Zone("example.com.", set()), "www", 3600)

    def test_octodns_reasons_surface(self):
        with pytest.raises(RecordError, match='invalid IPv4 address "1.2.3"'):
            check_record(spec("A", "1.2.3"), Zone("example.com.", set()), "www", 3600)
        with pytest.raises(RecordError, match="root CNAME not allowed"):
            check_record(spec("CNAME", "a.example.org."), Zone("example.com.", set()), "", 3600)

    def test_lenient_relaxes_octodns_checks(self):
        check_record(spec("CNAME", "a.example.org.", lenient=True), Zone("example.com.", set()), "", 3600)

    def test_records_under_a_delegated_sub_zone_are_rejected(self):
        with pytest.raises(RecordError, match="under a managed subzone"):
            check_record(spec("A", "1.2.3.4"), Zone("example.com.", {"sub"}), "a.sub", 3600)
