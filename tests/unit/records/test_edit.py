import pytest

from manticora.components.records.edit import ZoneFile, entry_lines, record_lines, scalar_text
from manticora.components.records.errors import RecordError
from manticora.models.enums import AddOutcome, RemoveOutcome


APEX = """\
# Root domain
'':
  - type: ALIAS
    value: example.pages.dev.
    octodns:
      cloudflare:
        proxied: true
"""

WWW_A = """\
  - type: A
    value: 1.2.3.4
"""

WWW_AAAA = """\
  - type: AAAA
    value: "2001:db8::1"
"""

WWW = "# Web section -->\nwww:\n" + WWW_A + WWW_AAAA + "# Web section <--\n"

MAIL = """\
# Mail
mail:
  - type: MX
    value:
      preference: 10
      exchange: mx.example.com.
"""

BASE = APEX + "\n" + WWW + "\n" + MAIL

TXT_RECORD = {"type": "TXT", "value": "v=spf1 -all"}
TXT_BLOCK = """\
  - type: TXT
    value: v=spf1 -all
"""


class TestRendering:
    def test_full_record_renders_every_field_in_order(self):
        data = {
            "type": "TXT",
            "ttl": 300,
            "values": ["v=spf1 include:_spf.example.com ~all", "plain"],
            "octodns": {"lenient": True, "cloudflare": {"proxied": True}},
        }
        assert record_lines(data) == [
            "  - type: TXT",
            "    ttl: 300",
            "    values:",
            '      - "v=spf1 include:_spf.example.com ~all"',
            "      - plain",
            "    octodns:",
            "      lenient: true",
            "      cloudflare:",
            "        proxied: true",
        ]

    def test_mapping_value_renders_as_block(self):
        data = {"type": "SSHFP", "value": {"algorithm": 4, "fingerprint_type": 2, "fingerprint": "0AAF"}}
        assert record_lines(data, "") == [
            "- type: SSHFP",
            "  value:",
            "    algorithm: 4",
            "    fingerprint_type: 2",
            "    fingerprint: 0AAF",
        ]

    def test_entry_starts_with_quoted_name_when_needed(self):
        assert entry_lines("", TXT_RECORD)[0] == "'':"
        assert entry_lines("www", TXT_RECORD)[0] == "www:"
        assert entry_lines("100", TXT_RECORD)[0] == "'100':"

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            ("1.2.3.4", "1.2.3.4"),
            ("2001:db8::1", '"2001:db8::1"'),
            ("100::", '"100::"'),
            ("no", "'no'"),
            ("123", "'123'"),
            ("", "''"),
            (r"v=DMARC1\; p=none\; rua=mailto:a@b.c", r"v=DMARC1\; p=none\; rua=mailto:a@b.c"),
            ("a: b", '"a: b"'),
        ],
    )
    def test_scalar_text_quotes_only_what_would_read_back_differently(self, value, text):
        assert scalar_text(value) == text


class TestParsedView:
    def test_lists_entries_with_record_types(self):
        zone = ZoneFile(BASE)
        assert [(e.name, [r.type for r in e.records], e.splice) for e in zone.entries] == [
            ("", ["ALIAS"], True),
            ("www", ["A", "AAAA"], True),
            ("mail", ["MX"], True),
        ]

    def test_lookups_ignore_case(self):
        zone = ZoneFile(BASE)
        assert zone.entry("WWW") is not None
        assert zone.has_record("www", "aaaa")
        assert not zone.has_record("www", "TXT")

    def test_empty_and_comment_only_files_have_no_entries(self):
        assert ZoneFile("").entries == ()
        assert ZoneFile("# nothing yet\n").entries == ()

    def test_single_mapping_and_flow_entries_are_not_spliceable(self):
        zone = ZoneFile("a:\n  type: A\n  value: 1.1.1.1\nb: [{type: A, value: 1.1.1.1}, {type: TXT, value: x}]\n")
        assert [(e.name, [r.type for r in e.records], e.splice) for e in zone.entries] == [
            ("a", ["A"], False),
            ("b", ["A", "TXT"], False),
        ]

    @pytest.mark.parametrize(
        ("text", "match"),
        [
            ("- type: A\n", "no top-level mapping"),
            ("www:\n  - type: A\n    value: 1.1.1.1\nWWW:\n  - type: TXT\n    value: x\n", "Duplicate entry"),
            ("shared: &s [x]\nwww:\n  - type: A\n    value: 1.1.1.1\n    tags: *s\n", "anchors or aliases"),
            ("? [a, b]\n: 1\n", "non-scalar top-level key"),
            ("www: [\n", "not valid YAML"),
        ],
    )
    def test_refuses_files_it_cannot_edit_safely(self, text, match):
        with pytest.raises(RecordError, match=match):
            ZoneFile(text)


class TestAddRecord:
    def test_appends_after_last_record_before_trailing_comment(self):
        result = ZoneFile(BASE).add_record("www", TXT_RECORD)
        assert result.outcome == AddOutcome.ADDED
        assert result.text == BASE.replace(WWW_AAAA, WWW_AAAA + TXT_BLOCK)

    def test_creates_missing_name_at_end_of_file(self):
        result = ZoneFile(BASE).add_record("ftp", TXT_RECORD)
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.text == BASE + "\nftp:\n" + TXT_BLOCK

    def test_creates_name_in_empty_file_without_separator(self):
        assert ZoneFile("").add_record("ftp", TXT_RECORD).text == "ftp:\n" + TXT_BLOCK
        assert ZoneFile("# hdr\n\n\n").add_record("ftp", TXT_RECORD).text == "# hdr\n\nftp:\n" + TXT_BLOCK

    def test_appends_under_bare_key(self):
        assert ZoneFile("ftp:\n").add_record("ftp", TXT_RECORD).text == "ftp:\n" + TXT_BLOCK

    def test_follows_the_file_indent_style(self):
        text = "www:\n- type: A\n  value: 1.1.1.1\n"
        assert ZoneFile(text).add_record("www", TXT_RECORD).text == text + "- type: TXT\n  value: v=spf1 -all\n"
        assert ZoneFile(text).add_record("ftp", TXT_RECORD).text == text + "\nftp:\n- type: TXT\n  value: v=spf1 -all\n"

    def test_handles_missing_final_newline_and_crlf(self):
        assert ZoneFile(BASE.rstrip("\n")).add_record("www", TXT_RECORD).text == BASE.replace(
            WWW_AAAA, WWW_AAAA + TXT_BLOCK
        )
        crlf = "www:\r\n  - type: A\r\n    value: 1.1.1.1\r\n"
        assert ZoneFile(crlf).add_record("www", TXT_RECORD).text == crlf + TXT_BLOCK.replace("\n", "\r\n")

    def test_rejects_duplicate_type(self):
        with pytest.raises(RecordError, match="already has A record"):
            ZoneFile(BASE).add_record("www", {"type": "A", "value": "5.6.7.8"})

    @pytest.mark.parametrize(
        "text",
        [
            "www:\n  type: A\n  value: 1.1.1.1\n",
            "www: [{type: A, value: 1.1.1.1}]\n",
            "www: null\n",
        ],
    )
    def test_rejects_entries_that_are_not_block_sequences(self, text):
        with pytest.raises(RecordError, match="block sequence"):
            ZoneFile(text).add_record("www", TXT_RECORD)


class TestRemoveRecord:
    def test_removes_one_record_and_keeps_entry(self):
        result = ZoneFile(BASE).remove_record("www", "A")
        assert result.outcome == RemoveOutcome.REMOVED
        assert result.types == ("A",)
        assert result.text == BASE.replace(WWW_A, "")

    def test_removing_last_record_drops_entry_and_one_separator(self):
        result = ZoneFile(BASE).remove_record("mail", "mx")
        assert result.outcome == RemoveOutcome.REMOVED_NAME
        assert result.types == ("MX",)
        assert result.text == APEX + "\n" + WWW + "\n# Mail\n"

    def test_removing_without_type_drops_every_record(self):
        result = ZoneFile(BASE).remove_record("WWW")
        assert result.outcome == RemoveOutcome.REMOVED_NAME
        assert result.types == ("A", "AAAA")
        assert result.text == APEX + "\n# Web section -->\n# Web section <--\n\n" + MAIL

    def test_removing_first_entry_keeps_its_comment_but_no_leading_blank(self):
        assert ZoneFile(BASE).remove_record("").text == "# Root domain\n\n" + WWW + "\n" + MAIL
        bare = "a:\n  - type: A\n    value: 1.1.1.1\n\n" + MAIL
        assert ZoneFile(bare).remove_record("a").text == MAIL

    def test_removes_every_item_of_a_duplicated_type(self):
        text = "www:\n  - type: A\n    value: 1.1.1.1\n  - type: TXT\n    value: x\n  - type: A\n    value: 2.2.2.2\n"
        result = ZoneFile(text).remove_record("www", "A")
        assert result.types == ("A", "A")
        assert result.text == "www:\n  - type: TXT\n    value: x\n"

    def test_whole_entry_removal_works_for_mapping_form(self):
        text = "a:\n  type: A\n  value: 1.1.1.1\nb:\n  - type: A\n    value: 1.1.1.1\n"
        assert ZoneFile(text).remove_record("a", "A").text == "b:\n  - type: A\n    value: 1.1.1.1\n"

    def test_partial_removal_from_flow_form_is_rejected(self):
        with pytest.raises(RecordError, match="block sequence"):
            ZoneFile("a: [{type: A, value: 1.1.1.1}, {type: TXT, value: x}]\n").remove_record("a", "A")

    def test_emptied_file_renders_empty(self):
        assert ZoneFile("www:\n  - type: A\n    value: 1.1.1.1\n").remove_record("www").text == ""

    def test_missing_name_or_type_is_rejected(self):
        with pytest.raises(RecordError, match="not in the zone file"):
            ZoneFile(BASE).remove_record("ghost")
        with pytest.raises(RecordError, match="has no TXT record"):
            ZoneFile(BASE).remove_record("www", "TXT")


class TestRoundtrip:
    def test_add_then_remove_in_existing_entry_restores_text(self):
        added = ZoneFile(BASE).add_record("www", TXT_RECORD).text
        assert ZoneFile(added).remove_record("www", "TXT").text == BASE

    def test_add_then_remove_new_entry_restores_text(self):
        added = ZoneFile(BASE).add_record("ftp", TXT_RECORD).text
        assert ZoneFile(added).remove_record("ftp").text == BASE

    def test_emptied_file_can_be_rebuilt(self):
        text = "www:\n" + TXT_BLOCK
        emptied = ZoneFile(text).remove_record("www").text
        assert ZoneFile(emptied).add_record("www", TXT_RECORD).text == text


SORTED_BASE = """\
'':
  - type: TXT
    value: v=spf1 -all

# Web
www:
  - type: A
    value: 1.2.3.4
"""


class TestOrderedInsertion:
    def test_new_entry_lands_before_the_first_name_sorting_after_it(self):
        result = ZoneFile(SORTED_BASE).add_record("mail", {"type": "A", "ttl": 300, "value": "5.6.7.8"}, order=str)
        assert result.outcome == AddOutcome.CREATED_NAME
        assert result.text == SORTED_BASE.replace(
            "    value: v=spf1 -all\n",
            "    value: v=spf1 -all\n\nmail:\n  - ttl: 300\n    type: A\n    value: 5.6.7.8\n",
        )

    def test_new_first_entry_is_followed_by_a_separator(self):
        text = "www:\n  - type: A\n    value: 1.2.3.4\n"
        result = ZoneFile(text).add_record("api", TXT_RECORD, order=str)
        assert result.text == "api:\n" + TXT_BLOCK + "\n" + text

    def test_new_last_entry_still_goes_to_the_end(self):
        result = ZoneFile(SORTED_BASE).add_record("zzz", TXT_RECORD, order=str)
        assert result.text == SORTED_BASE + "\nzzz:\n" + TXT_BLOCK

    def test_appended_record_keys_are_sorted(self):
        result = ZoneFile(SORTED_BASE).add_record("www", {"type": "TXT", "ttl": 60, "value": "x"}, order=str)
        assert result.text == SORTED_BASE + "  - ttl: 60\n    type: TXT\n    value: x\n"
