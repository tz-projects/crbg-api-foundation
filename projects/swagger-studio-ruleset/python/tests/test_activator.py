"""Activator pure-logic tests — covers the in-place mutator only.

The HTTP lookup + POST flow is integration-tested by running the publisher
against a real org; mocking httpx round-trips here would test the mock more
than the logic.
"""

from __future__ import annotations

from swagger_studio_ruleset_publisher.activator import _set_enabled_by_id


def test_flips_matching_entry_by_ruleset_id() -> None:
    config: dict = {
        "spectralRulesets": [
            {"rulesetId": "abc-123", "enabled": False},
            {"rulesetId": "xyz-999", "enabled": False},
        ]
    }
    _set_enabled_by_id(config, "abc-123")
    assert config["spectralRulesets"][0]["enabled"] is True
    # Other entries untouched.
    assert config["spectralRulesets"][1]["enabled"] is False


def test_adds_entry_when_id_missing_from_existing_array() -> None:
    config: dict = {"spectralRulesets": []}
    _set_enabled_by_id(config, "new-id")
    assert config["spectralRulesets"] == [{"rulesetId": "new-id", "enabled": True}]


def test_creates_array_when_key_missing_entirely() -> None:
    config: dict = {}
    _set_enabled_by_id(config, "id-1")
    assert config["spectralRulesets"] == [{"rulesetId": "id-1", "enabled": True}]


def test_creates_array_when_key_present_but_not_a_list() -> None:
    config: dict = {"spectralRulesets": None}
    _set_enabled_by_id(config, "id-1")
    assert config["spectralRulesets"] == [{"rulesetId": "id-1", "enabled": True}]


def test_idempotent_on_already_enabled() -> None:
    config: dict = {"spectralRulesets": [{"rulesetId": "id-1", "enabled": True}]}
    _set_enabled_by_id(config, "id-1")
    assert len(config["spectralRulesets"]) == 1
    assert config["spectralRulesets"][0]["enabled"] is True


def test_skips_non_dict_entries() -> None:
    config: dict = {
        "spectralRulesets": [
            "not-a-dict",
            {"rulesetId": "abc-123", "enabled": False},
        ]
    }
    _set_enabled_by_id(config, "abc-123")
    assert config["spectralRulesets"][1]["enabled"] is True
