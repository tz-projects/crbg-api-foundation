"""AWS Lambda handler for the executive + platform report generators.

Reads a scan.json from S3, optionally reads Tier 2 / Tier 3 input files from
S3 (ownership map, rule display names, CoP guidance, asks file), runs both
report generators, and uploads all output HTML + CSV back to S3.

Stdlib-only at runtime apart from boto3 (which is preinstalled in the Lambda
Python runtime). Same scripts that run on the work laptop run here unchanged.

Invocation (manual):

    aws lambda invoke \\
        --function-name swagger-studio-reports \\
        --payload '{
            "scan_json_s3_uri": "s3://your-bucket/scans/2026-06-22/scan.json",
            "output_s3_prefix": "s3://your-bucket/reports/2026-06-22/",
            "org_display_name": "Acme Corporation",
            "studio_base_url": "https://app.swaggerhub.com/apis",
            "placeholder_ask": true
        }' \\
        out.json

Event schema:

    REQUIRED:
        scan_json_s3_uri      s3:// URI of the scan.json produced by the scanner
        output_s3_prefix      s3:// URI prefix where HTML/CSV will be written
        org_display_name      Human-readable org name (e.g. "Acme Corporation")
        studio_base_url       Base URL for per-API links in the platform report
                              (typically https://app.swaggerhub.com/apis)

    OPTIONAL (Tier 2/3 inputs — any s3:// URI):
        ownership_map_s3_uri          Lights up per-team sections
        rule_display_names_s3_uri     Humanizes rule ids
        cop_guidance_s3_uri           Replaces "guidance pending" placeholders
        asks_file_s3_uri              Sets the "What's needed" paragraph
        placeholder_ask: bool         Uses built-in placeholder ask paragraph
                                      (mutually exclusive with asks_file_s3_uri)
        per_team_threshold: int       Per-team subset HTML threshold (default 5)

Required IAM permissions:
    - s3:GetObject on the input bucket/prefix
    - s3:PutObject on the output bucket/prefix
    - logs:CreateLogStream, logs:PutLogEvents (via AWSLambdaBasicExecutionRole)

PyYAML is optional: only required if any of the YAML input files use nested
(non-flat) structure. Without PyYAML, the bundled flat-YAML fallback parser
handles flat `key: value` files. Add it to the Lambda zip if you need nested.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3

# The report scripts live alongside this handler at /var/task/ in Lambda.
# Add that dir to sys.path so `import generate_executive_report` works.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import generate_executive_report as _exec_report  # noqa: E402
import generate_platform_report as _platform_report  # noqa: E402

_s3 = boto3.client("s3")


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """s3://bucket/key -> ('bucket', 'key')."""
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Expected s3:// URI, got: {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


def _download_to(uri: str, dest: Path) -> Path:
    bucket, key = _parse_s3_uri(uri)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _s3.download_file(bucket, key, str(dest))
    return dest


def _upload_dir(local_dir: Path, s3_prefix_uri: str) -> list[str]:
    """Upload every file under local_dir to s3_prefix_uri, return list of s3:// URIs."""
    bucket, key_prefix = _parse_s3_uri(s3_prefix_uri.rstrip("/") + "/")
    uploaded: list[str] = []
    for f in local_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(local_dir).as_posix()
        key = f"{key_prefix}{rel}"
        content_type = (
            "text/html" if f.suffix == ".html"
            else "text/csv" if f.suffix == ".csv"
            else "application/octet-stream"
        )
        _s3.upload_file(
            str(f), bucket, key, ExtraArgs={"ContentType": content_type}
        )
        uploaded.append(f"s3://{bucket}/{key}")
    return uploaded


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    scan_uri = event["scan_json_s3_uri"]
    output_prefix = event["output_s3_prefix"]
    org_display = event["org_display_name"]
    studio_base = event["studio_base_url"]

    # Optional inputs — only download what's present in the event
    optional_inputs = {
        "ownership_map_s3_uri": "--ownership-map",
        "rule_display_names_s3_uri": "--rule-display-names",
        "cop_guidance_s3_uri": "--cop-guidance",
        "asks_file_s3_uri": "--asks-file",
    }

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        scan_local = _download_to(scan_uri, work / "scan.json")

        downloaded_flags: list[str] = []
        for event_key, cli_flag in optional_inputs.items():
            uri = event.get(event_key)
            if not uri:
                continue
            local = _download_to(uri, work / Path(_parse_s3_uri(uri)[1]).name)
            downloaded_flags.extend([cli_flag, str(local)])

        # ----- Executive report -----
        exec_out_dir = work / "executive"
        exec_out_dir.mkdir()
        exec_out_file = exec_out_dir / "executive-report.html"
        exec_argv = [
            "--input", str(scan_local),
            "--output", str(exec_out_file),
            "--org-display-name", org_display,
        ]
        # Executive report uses these subset flags only
        exec_subset = {"--ownership-map", "--rule-display-names", "--asks-file"}
        i = 0
        while i < len(downloaded_flags):
            if downloaded_flags[i] in exec_subset:
                exec_argv.extend(downloaded_flags[i:i + 2])
            i += 2
        if event.get("placeholder_ask") and "--asks-file" not in exec_argv:
            exec_argv.append("--placeholder-ask")
        _exec_report.main(exec_argv)

        # ----- Platform report -----
        platform_out_dir = work / "platform"
        platform_out_dir.mkdir()
        platform_argv = [
            "--input", str(scan_local),
            "--output-dir", str(platform_out_dir),
            "--org-display-name", org_display,
            "--studio-base-url", studio_base,
        ]
        # Platform report accepts these subset flags
        platform_subset = {
            "--ownership-map", "--rule-display-names", "--cop-guidance",
        }
        i = 0
        while i < len(downloaded_flags):
            if downloaded_flags[i] in platform_subset:
                platform_argv.extend(downloaded_flags[i:i + 2])
            i += 2
        if event.get("per_team_threshold") is not None:
            platform_argv.extend(
                ["--per-team-threshold", str(event["per_team_threshold"])]
            )
        _platform_report.main(platform_argv)

        # ----- Upload everything back to S3 -----
        # Put exec under <prefix>/executive-report.html and platform under
        # <prefix>/platform-report/...
        exec_uploaded = _upload_dir(exec_out_dir, output_prefix.rstrip("/") + "/")
        platform_uploaded = _upload_dir(
            platform_out_dir, output_prefix.rstrip("/") + "/platform-report/"
        )

    return {
        "statusCode": 200,
        "body": {
            "executive_report": exec_uploaded,
            "platform_report": platform_uploaded,
            "inputs_used": {
                "scan": scan_uri,
                **{k: event.get(k) for k in optional_inputs if event.get(k)},
            },
        },
    }
