"""AWS Lambda handler for the swagger-studio-scanner — LITE variant.

No S3, no SSM, no boto3. The simplest possible deployment:

  - The SwaggerHub API key + org come from plain Lambda environment variables
    (read by the existing Settings/config layer, which sources env vars).
  - The scan result (scan.json) is returned INLINE in the invoke response,
    not written to S3. You save the response and feed it to the reports
    Lambda (or the local reports generator).

Invocation (manual):

    aws lambda invoke \\
        --function-name swagger-studio-scanner \\
        --cli-binary-format raw-in-base64-out \\
        --payload '{"limit": 25}' \\
        out.json

Event schema:

    { "limit": int | null }   # OPTIONAL — same as the scanner CLI's --limit/-n

Response:

    {
        "statusCode": 200,
        "summary": { ... aggregate counts ... },
        "ruleset": { ... } | null,
        "scan": { ... the full scan.json object ... }   # feed this to reports
    }

Required Lambda environment variables:

    SWAGGERHUB_API_KEY    Org-owner read key (plain env var — visible in the
                          console; fine for a trial key, use the SSM variant
                          on the heavy branch for sensitive keys)
    SWAGGERHUB_ORG        Org slug to scan

Optional env vars (same names as the CLI):

    SWAGGERHUB_BASE_URL, SCANNER_CONCURRENCY, SCANNER_REQUEST_TIMEOUT_S,
    SCANNER_LOG_LEVEL

IAM: only basic logging is needed (AWSLambdaBasicExecutionRole). No S3, no SSM.

Note on the 6 MB response limit: a synchronous Lambda response caps at ~6 MB.
A small or --limit'ed scan is well under that. A full 600-API scan may exceed
it — chunk with "limit", or use the S3 (heavy) variant for full-estate runs.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from swagger_studio_scanner.config import load_settings
from swagger_studio_scanner.logging_setup import configure_logging
from swagger_studio_scanner.pareto import ScanSummary
from swagger_studio_scanner.reports import write_json
from swagger_studio_scanner.scanner import scan_org


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    limit = event.get("limit") if isinstance(event, dict) else None

    settings = load_settings()  # SWAGGERHUB_API_KEY + SWAGGERHUB_ORG from env vars
    configure_logging(settings.scanner_log_level)

    report = asyncio.run(scan_org(settings, limit=limit))

    if not report.results:
        return {
            "statusCode": 200,
            "warning": "No APIs returned by Studio listing endpoint.",
            "org": settings.swaggerhub_org,
            "limit_applied": limit,
            "scan": None,
        }

    # Reuse the canonical writer (to /tmp, the only writable FS in Lambda),
    # then read it back so the returned object matches the on-disk schema the
    # reports generator expects.
    with tempfile.TemporaryDirectory() as tmp:
        json_path = write_json(report, Path(tmp))
        scan = json.loads(json_path.read_text(encoding="utf-8"))

    summary = ScanSummary.from_results(report.results)
    return {
        "statusCode": 200,
        "summary": {
            "total_apis": summary.total_apis,
            "passed": summary.passed,
            "warned": summary.warned,
            "failed": summary.failed,
            "errored": summary.errored,
            "total_findings": summary.total_findings,
            "critical_findings": summary.critical_findings,
            "warning_findings": summary.warning_findings,
        },
        "ruleset": report.ruleset.model_dump(mode="json") if report.ruleset else None,
        "limit_applied": limit,
        "scan": scan,
    }
