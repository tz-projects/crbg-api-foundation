"""Parser unit tests for the SwaggerHub listing response.

Fixtures use the real response shape captured from a SparkLayer trial org:
top-level ``name`` is OpenAPI info.title, the actual slug lives in the
``Swagger`` property URL, and ``X-Versions`` carries a marker like ``"-1.0.0"``
that must NOT be treated as a real version.

(Imports now point at the dedicated ``parsers`` module — the client owns
HTTP only.)
"""

from __future__ import annotations

from swagger_studio_scanner.parsers import (
    extract_api_items,
    extract_api_ref,
    parse_swagger_url,
)


def test_parse_swagger_url_absolute() -> None:
    ref = parse_swagger_url(
        "https://api.swaggerhub.com/apis/sparklayerinc/scanner-bad-petstore/1.0.0"
    )
    assert ref is not None
    assert ref.owner == "sparklayerinc"
    assert ref.name == "scanner-bad-petstore"
    assert ref.version == "1.0.0"


def test_parse_swagger_url_relative() -> None:
    ref = parse_swagger_url("apis/acme/orders/2.1.0")
    assert ref is not None
    assert (ref.owner, ref.name, ref.version) == ("acme", "orders", "2.1.0")


def test_parse_swagger_url_rejects_unrecognized_shape() -> None:
    assert parse_swagger_url("https://example.com/whatever") is None
    assert parse_swagger_url("apis/owner") is None
    assert parse_swagger_url("") is None


def test_extract_api_ref_uses_swagger_property_not_info_title() -> None:
    """The top-level ``name`` is info.title — must NOT be used as the slug."""
    item = {
        "name": "Scanner Good Petstore",  # info.title — distractor
        "description": "Well-formed sample API ...",
        "properties": [
            {
                "type": "Swagger",
                "url": "https://api.swaggerhub.com/apis/sparklayerinc/scanner-good-petstore/1.0.0",
            },
            {"type": "X-Version", "value": "1.0.0"},
            {"type": "X-Versions", "value": "-1.0.0"},  # the bogus marker
        ],
    }
    ref = extract_api_ref(item)
    assert ref is not None
    assert ref.owner == "sparklayerinc"
    assert ref.name == "scanner-good-petstore"
    assert ref.version == "1.0.0"


def test_extract_api_ref_returns_none_when_no_swagger_property() -> None:
    item = {"name": "x", "properties": [{"type": "X-Version", "value": "1.0.0"}]}
    assert extract_api_ref(item) is None


def test_extract_api_items_finds_apis_key() -> None:
    payload = {"apis": [{"name": "x"}, {"name": "y"}]}
    items = extract_api_items(payload)
    assert len(items) == 2


def test_extract_api_items_handles_missing_apis_key() -> None:
    assert extract_api_items({"totalCount": 0}) == []
