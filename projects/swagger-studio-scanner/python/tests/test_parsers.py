"""Unit tests for the parser adapters: api meta, ruleset, findings.

These cover the gaps the v2 reports spec called out (rule id in description,
created/modified extraction, ruleset metadata) and the OCP boundary on the
finding parser strategy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from swagger_studio_scanner.models import RulesetMeta, Severity
from swagger_studio_scanner.parsers import (
    DEFAULT_FINDING_PARSER,
    DescriptionPrefixFindingParser,
    extract_api_meta,
    parse_finding,
    parse_ruleset_payload,
)


# --- extract_api_meta --------------------------------------------------------


def _item_with_properties(props: list[dict]) -> dict:
    return {"name": "ignored", "properties": props}


def test_extract_api_meta_reads_iso_timestamps_and_flags() -> None:
    meta = extract_api_meta(
        _item_with_properties(
            [
                {"type": "X-Created", "value": "2025-08-13T10:21:00Z"},
                {"type": "X-Modified", "value": "2026-01-04T11:00:00+00:00"},
                {"type": "X-Default", "value": "true"},
                {"type": "X-Published", "value": "false"},
            ]
        )
    )
    assert meta.created_at == datetime(2025, 8, 13, 10, 21, 0, tzinfo=timezone.utc)
    assert meta.modified_at == datetime(2026, 1, 4, 11, 0, 0, tzinfo=timezone.utc)
    assert meta.is_default_version is True
    assert meta.is_published is False


def test_extract_api_meta_missing_properties_all_none() -> None:
    meta = extract_api_meta(_item_with_properties([{"type": "X-Version", "value": "1.0"}]))
    assert meta.created_at is None
    assert meta.modified_at is None
    assert meta.is_default_version is None
    assert meta.is_published is None


def test_extract_api_meta_robust_to_garbage_timestamp() -> None:
    meta = extract_api_meta(_item_with_properties([{"type": "X-Created", "value": "yesterday"}]))
    assert meta.created_at is None


# --- parse_ruleset_payload ---------------------------------------------------


def test_parse_ruleset_payload_returns_none_for_unrecognized() -> None:
    assert parse_ruleset_payload(None) is None
    assert parse_ruleset_payload({}) is None
    assert parse_ruleset_payload({"unrelated": "data"}) is None


def test_parse_ruleset_payload_picks_known_keys() -> None:
    rs = parse_ruleset_payload({"name": "openapi-3-0-active", "version": "1.4.0"})
    assert rs == RulesetMeta(name="openapi-3-0-active", version="1.4.0")


def test_parse_ruleset_payload_accepts_partial() -> None:
    rs = parse_ruleset_payload({"ruleset": "house-style"})
    assert rs == RulesetMeta(name="house-style", version=None)


# --- FindingParser strategy --------------------------------------------------


def test_default_finding_parser_splits_rule_id_from_description() -> None:
    f = parse_finding(
        {
            "rule": "unknown",
            "severity": "CRITICAL",
            "description": "info-contact -> info.contact is required",
            "line": 1,
        }
    )
    assert f.rule == "info-contact"
    assert f.message == "info.contact is required"
    assert f.severity is Severity.CRITICAL
    # raw description preserved for backward-compat consumers
    assert f.description == "info-contact -> info.contact is required"
    assert f.line == 1


def test_default_finding_parser_prefers_real_rule_field() -> None:
    f = parse_finding(
        {
            "rule": "oas3-schema",
            "severity": "WARNING",
            "description": "human readable thing",
        }
    )
    assert f.rule == "oas3-schema"
    assert f.message == "human readable thing"


def test_default_finding_parser_falls_back_on_plain_description() -> None:
    f = parse_finding({"rule": "", "severity": "INFO", "description": "no arrow here"})
    assert f.rule == "unknown"
    assert f.message == "no arrow here"


def test_default_finding_parser_unknown_severity_coerced_to_info() -> None:
    f = parse_finding({"rule": "r", "severity": "EXTREME", "description": "x"})
    assert f.severity is Severity.INFO


def test_finding_parser_strategy_is_swappable() -> None:
    """OCP: a custom parser can be injected without monkey-patching."""

    class StaticParser:
        def parse(self, entry):  # noqa: ANN001 — protocol method
            from swagger_studio_scanner.models import Finding

            return Finding(rule="static", severity=Severity.INFO, description="x")

    f = parse_finding({"rule": "r", "severity": "CRITICAL", "description": "y"}, parser=StaticParser())
    assert f.rule == "static"
    # Sanity: default parser path is unchanged.
    assert isinstance(DEFAULT_FINDING_PARSER, DescriptionPrefixFindingParser)
