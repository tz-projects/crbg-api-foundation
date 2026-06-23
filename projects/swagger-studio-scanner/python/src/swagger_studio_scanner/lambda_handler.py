"""AWS Lambda handler for the swagger-studio-scanner.

This is a thin wrapper around the existing async ``scan_org()`` orchestrator.
The scanner code itself is untouched — the handler reads config from Lambda
environment variables + SSM Parameter Store, runs the scan, and uploads the
resulting ``scan.json`` to S3.

Invocation (manual, from CloudShell or any machine with the AWS CLI):

    aws lambda invoke \\
        --function-name swagger-studio-scanner \\
        --payload '{
            "s3_bucket": "your-bucket",
            "s3_prefix": "scans/2026-06-22/",
            "limit": 25
        }' \\
        out.json

Event schema:

    {
        "s3_bucket": str,     # REQUIRED — destination bucket
        "s3_prefix": str,     # REQUIRED — S3 key prefix; "/scan.json" appended
        "limit":     int|null # OPTIONAL — equivalent to scanner CLI's --limit/-n
    }

Required Lambda environment variables:

    SWAGGERHUB_ORG               Org slug to scan
    SSM_API_KEY_PARAMETER        Name of an SSM SecureString parameter holding
                                 the SwaggerHub API key
                                 (e.g. /scanner/swaggerhub_api_key)

Optional Lambda environment variables (same names as the CLI uses):

    SWAGGERHUB_BASE_URL          Default https://api.swaggerhub.com
    SCANNER_CONCURRENCY          Default 8
    SCANNER_REQUEST_TIMEOUT_S    Default 30
    SCANNER_LOG_LEVEL            Default INFO

Required IAM permissions for the Lambda execution role:

    - ssm:GetParameter on the parameter named in SSM_API_KEY_PARAMETER
    - s3:PutObject on the destination bucket/prefix
    - logs:CreateLogStream, logs:PutLogEvents (granted by AWSLambdaBasicExecutionRole)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import boto3

from swagger_studio_scanner.config import load_settings
from swagger_studio_scanner.logging_setup import configure_logging
from swagger_studio_scanner.pareto import ScanSummary
from swagger_studio_scanner.reports import write_json
from swagger_studio_scanner.scanner import scan_org

_ssm = boto3.client("ssm")
_s3 = boto3.client("s3")


def _hydrate_env_from_ssm() -> None:
    """Pull the API key from SSM and inject it into the env so Settings sees it.

    Settings (pydantic-settings) reads from env vars first, so this needs to
    happen BEFORE load_settings() is called.
    """
    if "SWAGGERHUB_API_KEY" in os.environ:
        return  # already set (e.g. for local testing)
    param_name = os.environ["SSM_API_KEY_PARAMETER"]
    resp = _ssm.get_parameter(Name=param_name, WithDecryption=True)
    os.environ["SWAGGERHUB_API_KEY"] = resp["Parameter"]["Value"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    bucket = event["s3_bucket"]
    prefix = event["s3_prefix"].rstrip("/") + "/"
    limit = event.get("limit")

    _hydrate_env_from_ssm()
    settings = load_settings()
    configure_logging(settings.scanner_log_level)

    report = asyncio.run(scan_org(settings, limit=limit))

    if not report.results:
        return {
            "statusCode": 200,
            "body": {
                "warning": "No APIs returned by Studio listing endpoint.",
                "org": settings.swaggerhub_org,
                "limit_applied": limit,
            },
        }

    # Write scan.json to /tmp (the only writable filesystem in Lambda),
    # then upload to S3. Reuses the canonical writer so the on-disk schema
    # matches what the reports project expects.
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = write_json(report, Path(tmpdir))
        s3_key = f"{prefix}scan.json"
        _s3.upload_file(
            str(json_path),
            bucket,
            s3_key,
            ExtraArgs={"ContentType": "application/json"},
        )

    summary = ScanSummary.from_results(report.results)
    return {
        "statusCode": 200,
        "body": {
            "scan_json_s3_uri": f"s3://{bucket}/{s3_key}",
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
            "ruleset": (
                report.ruleset.model_dump(mode="json") if report.ruleset else None
            ),
            "limit_applied": limit,
        },
    }
