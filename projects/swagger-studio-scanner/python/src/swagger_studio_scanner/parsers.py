"""Adapters that translate raw SwaggerHub payloads into typed domain models.

Why a separate module: the SRP boundary between *talking to the API*
(`client.py`) and *interpreting the API's payloads* is real. Wire shapes
evolve independently of HTTP concerns, and unit-testing the adapters
requires no network. SwaggerHub also encodes several distinct facts —
API identity, age, default-version flag, published flag — inside one
generic `properties` array; one module owns that deserialization grammar.

Public surface:

- Listing payload    : ``extract_api_items``, ``extract_api_ref``,
                       ``extract_api_meta``, ``parse_swagger_url``.
- Ruleset payload    : ``parse_ruleset_payload``.
- Finding payload    : ``FindingParser`` protocol,
                       ``DescriptionPrefixFindingParser`` (default),
                       ``DEFAULT_FINDING_PARSER``, ``parse_finding``.

All functions are total: malformed input yields a sensible default
(``None`` / empty list / parser fallback) rather than raising. Callers
decide what to do with absences; the parsers never invent values.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Protocol

from .models import ApiMeta, ApiRef, Finding, RulesetMeta, Severity

# --- Listing payload ---------------------------------------------------------


def extract_api_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the API list out of a ``/apis/{owner}`` payload.

    Different SwaggerHub deployments key the list differently; try each
    known key in order so this stays the one place to patch.
    """
    for key in ("apis", "items"):
        items = payload.get(key)
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    return []


def extract_api_ref(item: dict[str, Any]) -> ApiRef | None:
    """Recover ``(owner, name, version)`` from a listing item's Swagger URL.

    The canonical resource URL lives in the property whose ``type`` is
    ``Swagger``. The top-level ``name`` on a listing item is OpenAPI
    ``info.title`` and must NOT be used as the slug.
    """
    url = _find_property(item, "Swagger", key="url")
    if not isinstance(url, str):
        return None
    return parse_swagger_url(url)


def extract_api_meta(item: dict[str, Any]) -> ApiMeta:
    """Recover descriptive metadata from a listing item's ``properties`` array.

    Missing properties yield ``None``; the report layer decides how to
    surface absent data.
    """
    return ApiMeta(
        created_at=_parse_iso(_find_property(item, "X-Created", key="value")),
        modified_at=_parse_iso(_find_property(item, "X-Modified", key="value")),
        is_default_version=_parse_bool(_find_property(item, "X-Default", key="value")),
        is_published=_parse_bool(_find_property(item, "X-Published", key="value")),
    )


def parse_swagger_url(url: str) -> ApiRef | None:
    """Extract ``(owner, name, version)`` from a SwaggerHub canonical URL.

    Accepts absolute (``https://api.swaggerhub.com/apis/...``) and relative
    (``apis/...``) forms. Returns ``None`` for any URL that doesn't have the
    ``/apis/{owner}/{name}/{version}`` shape — including the empty string.
    """
    if not url:
        return None
    if "/apis/" in url:
        tail = url.split("/apis/", 1)[1]
    elif url.startswith("apis/"):
        tail = url[len("apis/") :]
    else:
        return None
    parts = tail.strip("/").split("/")
    if len(parts) < 3 or not all(parts[:3]):
        return None
    owner, name, version = parts[:3]
    return ApiRef(owner=owner, name=name, version=version)


def _find_property(item: dict[str, Any], type_name: str, *, key: str) -> Any:
    """Return ``properties[?type==type_name][key]``, or ``None``."""
    props = item.get("properties")
    if not isinstance(props, list):
        return None
    for prop in props:
        if isinstance(prop, dict) and prop.get("type") == type_name:
            return prop.get(key)
    return None


# --- Ruleset payload ---------------------------------------------------------


def parse_ruleset_payload(payload: Any) -> RulesetMeta | None:
    """Pick the active ruleset name/version out of a ``/standardization`` payload.

    The endpoint shape is not officially documented; we accept a small set
    of known keys. Returns ``None`` when nothing recognizable is present —
    callers treat "no active ruleset" identically to "we couldn't tell."
    """
    if not isinstance(payload, dict):
        return None
    name = _first_str(payload, "name", "ruleset", "rulesetName", "active")
    version = _first_str(payload, "version", "rulesetVersion")
    if not name and not version:
        return None
    return RulesetMeta(name=name, version=version)


def _first_str(payload: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return None


# --- Finding parsing ---------------------------------------------------------

_DESCRIPTION_PREFIX_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_\-]*)\s*->\s*(.+)$")


class FindingParser(Protocol):
    """Strategy for normalizing a raw finding dict.

    OCP boundary: swap in a different parser when Studio changes its
    finding shape, without touching ``client.py`` or the scanner
    orchestrator. The client accepts a ``FindingParser`` in its
    constructor; the default is the description-prefix parser.
    """

    def parse(self, entry: dict[str, Any]) -> Finding: ...


class DescriptionPrefixFindingParser:
    """Default parser: recover the rule id from ``description = '<rule-id> -> <message>'``.

    SwaggerHub's ``/standardization`` response uses ``description`` as the
    only carrier of the rule id in current deployments; the per-finding
    ``rule`` field comes back as the literal string ``"unknown"``. We split
    when needed and keep the original ``description`` intact so any consumer
    still depending on the raw text continues to work.
    """

    def parse(self, entry: dict[str, Any]) -> Finding:
        description = str(entry.get("description") or entry.get("message") or "")
        raw_rule = str(entry.get("rule") or entry.get("ruleId") or "").strip()
        rule_id, message = self._split(raw_rule, description)
        return Finding(
            rule=rule_id,
            severity=_severity(entry.get("severity")),
            description=description,
            message=message,
            line=_safe_int(entry.get("line")),
            path=entry.get("path") if isinstance(entry.get("path"), str) else None,
        )

    @staticmethod
    def _split(rule_raw: str, description: str) -> tuple[str, str | None]:
        if rule_raw and rule_raw.lower() != "unknown":
            return rule_raw, description or None
        m = _DESCRIPTION_PREFIX_RE.match(description.strip())
        if m:
            return m.group(1), m.group(2).strip()
        # Last resort: keep whatever we have so the report can still show something.
        return rule_raw or "unknown", description or None


DEFAULT_FINDING_PARSER: FindingParser = DescriptionPrefixFindingParser()


def parse_finding(
    entry: dict[str, Any], parser: FindingParser = DEFAULT_FINDING_PARSER
) -> Finding:
    """Convenience wrapper used by the client and tests."""
    return parser.parse(entry)


# --- Shared coercion helpers -------------------------------------------------


def _severity(raw: Any) -> Severity:
    s = str(raw or "INFO").upper()
    try:
        return Severity(s)
    except ValueError:
        return Severity.INFO


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_iso(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes"}:
            return True
        if v in {"false", "0", "no"}:
            return False
    return None
