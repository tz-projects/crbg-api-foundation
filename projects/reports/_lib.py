"""Shared helpers for the governance report generators (v2 spec).

The scanner JSON is normalized into a tier-aware view that surfaces what data
is present without crashing on what isn't:

- Tier 1: Studio (the scan JSON itself).
- Tier 2: ownership map (optional YAML/JSON file keyed by `owner/name[/version]`).
- Tier 3: rule display names, CoP guidance, asks (each optional).

Both generators consume the same NormalizedScan and decide section-by-section
which tier they're rendering. Anything missing from the scanner is reported
as "data not available" — never silently dropped.

Standard library only by design (v2 §"Shared implementation notes"): no
chart library, no template engine, optional PyYAML for richer ownership maps.
"""

from __future__ import annotations

import html as _html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# --- Parsing helpers ----------------------------------------------------------

_RULE_DESCRIPTION_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_\-]*)\s*->\s*(.+)$")


def parse_rule_from_description(description: str) -> tuple[str, str]:
    """Pull `(rule_id, human_message)` out of a `rule-id -> message` description.

    SwaggerHub's `/standardization` response carries the rule id only inside
    `description`; the per-finding `rule` field stays `"unknown"` until the
    scanner is patched. Falls back to `(description, description)` when the
    pattern doesn't match so unknown shapes still surface in the report.
    """
    m = _RULE_DESCRIPTION_RE.match(description.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return description.strip(), description.strip()


def humanize_rule_id(rule_id: str) -> str:
    """`operation-description` -> `Operation description`."""
    cleaned = rule_id.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return rule_id
    return cleaned[0].upper() + cleaned[1:]


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# --- Domain views -------------------------------------------------------------


@dataclass
class FindingView:
    rule_id: str
    rule_display: str
    severity: str
    line: int | None
    message: str
    path: str | None


@dataclass
class ApiView:
    owner: str
    name: str
    version: str
    status: str  # "pass" | "warn" | "fail" | "error"
    findings: list[FindingView]
    error: str | None
    scanned_at: datetime | None
    created_at: datetime | None
    modified_at: datetime | None
    # Tier 1 enrichments lifted from the scanner's meta block.
    is_published: bool | None = None
    is_default_version: bool | None = None
    # Tier 2 enrichments — None when ownership map absent or sparse.
    team: str | None = None
    domain: str | None = None
    contact_email: str | None = None
    repo_url: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}/{self.version}"

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARNING")

    def studio_url(self, base: str) -> str:
        return f"{base.rstrip('/')}/{self.owner}/{self.name}/{self.version}"


@dataclass
class RulePareto:
    rule_id: str
    rule_display: str
    severity: str  # "CRITICAL" | "WARNING" | "mixed"
    count: int
    share_pct: float
    cumulative_pct: float


@dataclass
class NormalizedScan:
    org: str
    scanned_at: datetime | None
    ruleset_name: str | None
    apis: list[ApiView]
    has_age_data: bool
    has_ownership: bool
    ownership_coverage_pct: float
    has_rule_display_lookup: bool
    has_cop_guidance: bool

    # --- Counts ---

    @property
    def api_count(self) -> int:
        return len(self.apis)

    @property
    def pass_count(self) -> int:
        return sum(1 for a in self.apis if a.status == "pass")

    @property
    def warn_count(self) -> int:
        return sum(1 for a in self.apis if a.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for a in self.apis if a.status == "fail")

    @property
    def error_count(self) -> int:
        return sum(1 for a in self.apis if a.status == "error")

    @property
    def scannable_count(self) -> int:
        """APIs the scanner could actually evaluate (excludes SCAN_ERROR)."""
        return self.api_count - self.error_count

    @property
    def pass_pct(self) -> float:
        return _pct(self.pass_count, self.scannable_count)

    @property
    def fail_pct(self) -> float:
        return _pct(self.fail_count, self.scannable_count)

    @property
    def warn_only_pct(self) -> float:
        return _pct(self.warn_count, self.scannable_count)

    @property
    def all_findings(self) -> list[FindingView]:
        out: list[FindingView] = []
        for a in self.apis:
            out.extend(a.findings)
        return out

    @property
    def teams(self) -> list[str]:
        return sorted({a.team for a in self.apis if a.team})

    @property
    def domains(self) -> list[str]:
        return sorted({a.domain for a in self.apis if a.domain})

    @property
    def has_published_data(self) -> bool:
        """At least one API has a known published-state."""
        return any(a.is_published is not None for a in self.apis)

    @property
    def published_coverage_pct(self) -> float:
        """Share of scanned APIs with a known published-state — 0-100."""
        known = sum(1 for a in self.apis if a.is_published is not None)
        return _pct(known, self.api_count)

    @property
    def has_default_version_data(self) -> bool:
        return any(a.is_default_version is not None for a in self.apis)


def _pct(n: int, d: int) -> float:
    if d <= 0:
        return 0.0
    return round(100.0 * n / d, 1)


# --- Loaders ------------------------------------------------------------------


def load_scan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional_mapping(path: Path | None) -> dict[str, Any]:
    """Load YAML or JSON; return {} if path is None/missing.

    PyYAML is used when available; otherwise a minimal flat-dict fallback
    keeps the generator usable on a bare interpreter (Tier 3 lookups are
    flat by convention).
    """
    if not path or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text) or {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Tiny fallback YAML parser for flat `key: value` files.

    Used only when PyYAML isn't installed — Tier 3 lookups (display names,
    CoP URLs) are flat enough that this gets the job done. Ownership maps
    with nested team/domain/contact_email require PyYAML.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line or line[0] in " \t-":
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# --- Normalization ------------------------------------------------------------


def normalize(
    scan: dict[str, Any],
    ownership_map: dict[str, Any] | None,
    rule_display_lookup: dict[str, str] | None,
    cop_guidance: dict[str, str] | None,
) -> NormalizedScan:
    """Build a NormalizedScan from raw scanner JSON + optional Tier 2/3 inputs."""
    results = scan.get("results") or []
    org = _infer_org(scan, results)

    # Rule display names may be embedded in the scan (the scanner fetched them
    # from Studio's rule definitions) and/or supplied via --rule-display-names.
    # Merge both; the explicit lookup wins per-key so a caller can override the
    # embedded titles. Absent both -> {} -> findings fall back to a humanized id.
    embedded_names = scan.get("rule_display_names")
    if not isinstance(embedded_names, dict):
        embedded_names = {}
    rule_display_lookup = {**embedded_names, **(rule_display_lookup or {})}

    apis: list[ApiView] = []
    age_data_seen = False
    matched = 0
    total = 0

    for r in results:
        if not isinstance(r, dict):
            continue
        api_info = r.get("api") or {}
        owner = api_info.get("owner") or "unknown"
        name = api_info.get("name") or "unknown"
        version = api_info.get("version") or "0"
        slug = f"{owner}/{name}/{version}"
        status = (r.get("status") or "error").lower()

        meta_block = r.get("meta") if isinstance(r.get("meta"), dict) else {}
        created_at = parse_iso(
            r.get("created_at")
            or api_info.get("created_at")
            or meta_block.get("created_at")
        )
        modified_at = parse_iso(
            r.get("modified_at")
            or api_info.get("modified_at")
            or meta_block.get("modified_at")
        )
        if created_at or modified_at:
            age_data_seen = True

        is_published = meta_block.get("is_published")
        is_default_version = meta_block.get("is_default_version")
        if not isinstance(is_published, bool):
            is_published = None
        if not isinstance(is_default_version, bool):
            is_default_version = None

        findings: list[FindingView] = []
        for fr in r.get("findings") or []:
            if not isinstance(fr, dict):
                continue
            desc = str(fr.get("description") or "")
            rule_raw = str(fr.get("rule") or "")
            if rule_raw and rule_raw.lower() != "unknown":
                rule_id, message = rule_raw, desc
            else:
                rule_id, message = parse_rule_from_description(desc)
            display = (rule_display_lookup or {}).get(rule_id) or humanize_rule_id(rule_id)
            findings.append(
                FindingView(
                    rule_id=rule_id,
                    rule_display=display,
                    severity=str(fr.get("severity") or "WARNING").upper(),
                    line=fr.get("line") if isinstance(fr.get("line"), int) else None,
                    message=message,
                    path=fr.get("path") if isinstance(fr.get("path"), str) else None,
                )
            )

        entry = None
        if ownership_map:
            entry = (
                ownership_map.get(slug)
                or ownership_map.get(f"{owner}/{name}")
                or ownership_map.get(name)
            )
        if entry:
            matched += 1
        total += 1

        team = domain = contact_email = repo_url = None
        if isinstance(entry, dict):
            team = entry.get("team")
            domain = entry.get("domain")
            contact_email = entry.get("contact_email")
            repo_url = entry.get("repo_url")

        apis.append(
            ApiView(
                owner=owner,
                name=name,
                version=version,
                status=status,
                findings=findings,
                error=r.get("error"),
                scanned_at=parse_iso(r.get("scanned_at")),
                created_at=created_at,
                modified_at=modified_at,
                is_published=is_published,
                is_default_version=is_default_version,
                team=team,
                domain=domain,
                contact_email=contact_email,
                repo_url=repo_url,
            )
        )

    coverage_pct = _pct(matched, total) if total else 0.0
    return NormalizedScan(
        org=org,
        scanned_at=parse_iso(scan.get("generated_at") or scan.get("scanned_at")),
        ruleset_name=scan.get("ruleset_name") or scan.get("ruleset"),
        apis=apis,
        has_age_data=age_data_seen,
        has_ownership=bool(ownership_map) and matched > 0,
        ownership_coverage_pct=coverage_pct,
        has_rule_display_lookup=bool(rule_display_lookup),
        has_cop_guidance=bool(cop_guidance),
    )


def _infer_org(scan: dict[str, Any], results: list[Any]) -> str:
    for k in ("org", "organization", "owner"):
        v = scan.get(k)
        if isinstance(v, str) and v:
            return v
    for r in results:
        if isinstance(r, dict):
            api = r.get("api") or {}
            v = api.get("owner")
            if isinstance(v, str) and v:
                return v
    return "unknown"


# --- Aggregations -------------------------------------------------------------


def rule_pareto(scan: NormalizedScan, top_n: int = 10) -> list[RulePareto]:
    """Top-N rules by failure count, with share % and cumulative %."""
    counts: Counter[str] = Counter()
    displays: dict[str, str] = {}
    sevs: dict[str, set[str]] = defaultdict(set)
    for f in scan.all_findings:
        counts[f.rule_id] += 1
        displays[f.rule_id] = f.rule_display
        sevs[f.rule_id].add(f.severity)

    total = sum(counts.values())
    if total == 0:
        return []

    out: list[RulePareto] = []
    running = 0
    for rule_id, c in counts.most_common(top_n):
        running += c
        sev_set = sevs[rule_id]
        sev = next(iter(sev_set)) if len(sev_set) == 1 else "mixed"
        out.append(
            RulePareto(
                rule_id=rule_id,
                rule_display=displays.get(rule_id, rule_id),
                severity=sev,
                count=c,
                share_pct=round(100.0 * c / total, 1),
                cumulative_pct=round(100.0 * running / total, 1),
            )
        )
    return out


def rules_to_reach(scan: NormalizedScan, threshold_pct: float = 70.0) -> int:
    """How many top rules cumulatively cover `threshold_pct` of all findings.

    Small number => bulk-fixable concentration. Large number => scattered.
    """
    pareto = rule_pareto(scan, top_n=10_000)
    if not pareto:
        return 0
    for i, p in enumerate(pareto, start=1):
        if p.cumulative_pct >= threshold_pct:
            return i
    return len(pareto)


def apis_failing_rule(scan: NormalizedScan, rule_id: str) -> list[ApiView]:
    return [a for a in scan.apis if any(f.rule_id == rule_id for f in a.findings)]


def top_failing_apis(scan: NormalizedScan, top_n: int = 10) -> list[ApiView]:
    scored = [
        (a, len(a.findings), a.critical_count)
        for a in scan.apis
        if a.status in ("fail", "warn")
    ]
    scored.sort(key=lambda t: (-t[1], -t[2], t[0].slug))
    return [a for a, _, _ in scored[:top_n]]


# --- Age buckets (Tier 1 substitute for team distribution) --------------------


@dataclass
class AgeBucket:
    label: str
    api_count: int
    failing_count: int


_AGE_BUCKETS = [
    ("< 90 days", timedelta(days=0), timedelta(days=90)),
    ("90 days – 1 year", timedelta(days=90), timedelta(days=365)),
    ("1 – 3 years", timedelta(days=365), timedelta(days=365 * 3)),
    ("3+ years", timedelta(days=365 * 3), timedelta(days=365 * 100)),
]


def age_buckets(scan: NormalizedScan) -> list[AgeBucket]:
    if not scan.has_age_data or not scan.scanned_at:
        return []
    now = scan.scanned_at
    buckets = [AgeBucket(label=lbl, api_count=0, failing_count=0) for lbl, _, _ in _AGE_BUCKETS]
    for api in scan.apis:
        if not api.created_at:
            continue
        age = now - api.created_at
        for i, (_, lo, hi) in enumerate(_AGE_BUCKETS):
            if lo <= age < hi:
                buckets[i].api_count += 1
                if api.status in ("fail", "warn"):
                    buckets[i].failing_count += 1
                break
    return buckets


def unpublished_failing_stats(scan: NormalizedScan) -> tuple[int, int]:
    """Return ``(unpublished_failing, total_failing_with_known_state)``.

    Excludes APIs whose published-state is unknown so the percentage is
    grounded in apples-to-apples comparison. A CIO-relevant headline framing:
    *of the failing APIs we know about, how many are still drafts vs. live.*
    """
    failing_known = [
        a
        for a in scan.apis
        if a.status in ("fail", "warn") and a.is_published is not None
    ]
    unpub = sum(1 for a in failing_known if a.is_published is False)
    return unpub, len(failing_known)


def recent_vs_dormant(scan: NormalizedScan, window_days: int = 90) -> tuple[int, int, int, int]:
    """(recent_total, recent_failing, dormant_total, dormant_failing) by modified_at."""
    if not scan.has_age_data or not scan.scanned_at:
        return (0, 0, 0, 0)
    cutoff = scan.scanned_at - timedelta(days=window_days)
    r_total = r_fail = d_total = d_fail = 0
    for api in scan.apis:
        if not api.modified_at:
            continue
        failing = api.status in ("fail", "warn")
        if api.modified_at >= cutoff:
            r_total += 1
            r_fail += int(failing)
        else:
            d_total += 1
            d_fail += int(failing)
    return r_total, r_fail, d_total, d_fail


# --- Per-team aggregation (Tier 2) --------------------------------------------


@dataclass
class TeamSummary:
    team: str
    domain: str | None
    contact_email: str | None
    owned: int
    failing: int
    findings_total: int
    findings_critical: int
    findings_warning: int
    top_rules: list[tuple[str, int]]  # (rule_display, count)


def team_summaries(scan: NormalizedScan) -> list[TeamSummary]:
    by_team: dict[str, list[ApiView]] = defaultdict(list)
    for a in scan.apis:
        if a.team:
            by_team[a.team].append(a)

    out: list[TeamSummary] = []
    for team, apis in by_team.items():
        counts: Counter[str] = Counter()
        crit = warn = 0
        for a in apis:
            for f in a.findings:
                counts[f.rule_display] += 1
                if f.severity == "CRITICAL":
                    crit += 1
                elif f.severity == "WARNING":
                    warn += 1
        out.append(
            TeamSummary(
                team=team,
                domain=next((a.domain for a in apis if a.domain), None),
                contact_email=next((a.contact_email for a in apis if a.contact_email), None),
                owned=len(apis),
                failing=sum(1 for a in apis if a.status in ("fail", "warn")),
                findings_total=sum(counts.values()),
                findings_critical=crit,
                findings_warning=warn,
                top_rules=counts.most_common(3),
            )
        )
    out.sort(key=lambda t: (-t.findings_total, t.team))
    return out


def domain_summaries(scan: NormalizedScan) -> list[tuple[str, int, int]]:
    """(domain_name, owned, failing) sorted by failing count desc."""
    by_dom: dict[str, list[ApiView]] = defaultdict(list)
    for a in scan.apis:
        if a.domain:
            by_dom[a.domain].append(a)
    rows = [
        (d, len(apis), sum(1 for a in apis if a.status in ("fail", "warn")))
        for d, apis in by_dom.items()
    ]
    rows.sort(key=lambda r: (-r[2], r[0]))
    return rows


# --- Formatting ---------------------------------------------------------------


def fmt_date(dt: datetime | None) -> str:
    return dt.strftime("%B %d, %Y") if dt else "data not available"


def fmt_datetime(dt: datetime | None) -> str:
    if not dt:
        return "data not available"
    tz = dt.tzname() or "UTC"
    return f"{dt.strftime('%Y-%m-%d %H:%M')} {tz}"


def esc(value: Any) -> str:
    return _html.escape("" if value is None else str(value), quote=True)


def fmt_pct(value: float) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def studio_url(base: str, owner: str, name: str, version: str) -> str:
    return f"{base.rstrip('/')}/{owner}/{name}/{version}"
