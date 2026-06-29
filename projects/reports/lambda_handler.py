"""AWS Lambda handler for the report generators — LITE variant.

No S3, no boto3. Takes the scan object INLINE in the invoke payload (the
`scan` field from the scanner Lambda's response) and returns the rendered
HTML + CSV INLINE in the response. Nothing is read from or written to S3.

Invocation (manual). Typically you build the payload from the scanner's
output with jq — see docs/aws-lambda-lite.md.

    aws lambda invoke \\
        --function-name swagger-studio-reports \\
        --cli-binary-format raw-in-base64-out \\
        --payload file://reports-payload.json \\
        out.json

Event schema:

    {
        "scan":             { ... },   # REQUIRED — the scanner response's "scan"
        "org_display_name": str,       # REQUIRED
        "studio_base_url":  str,       # OPTIONAL (default app.swaggerhub.com/apis)
        "placeholder_ask":  bool       # OPTIONAL — executive report placeholder
    }

Response:

    {
        "statusCode": 200,
        "executive_html": "<full HTML string>",
        "platform_html":  "<full HTML string>",
        "findings_csv":   "<CSV string>"
    }

Extract each with jq, e.g.:  jq -r '.executive_html' out.json > executive-report.html

IAM: only basic logging (AWSLambdaBasicExecutionRole). No S3, no SSM.

Note on the 6 MB limit: applies to both the inbound payload (the scan object)
and the outbound response (the HTML). Fine for small / --limit'ed scans; for
full-estate runs use the S3 (heavy) variant.

Tier 2/3 enrichment (ownership map, rule names, CoP guidance) is a heavy-variant
feature; the lite handler renders Tier 1 + optional placeholder ask only.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

# The report scripts sit alongside this handler at /var/task in Lambda.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import generate_executive_report as _exec_report  # noqa: E402
import generate_platform_report as _platform_report  # noqa: E402


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    scan = event["scan"]
    org_display = event["org_display_name"]
    studio_base = event.get("studio_base_url", "https://app.swaggerhub.com/apis")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        scan_path = work / "scan.json"
        scan_path.write_text(json.dumps(scan), encoding="utf-8")

        # Executive report
        exec_out = work / "executive-report.html"
        exec_argv = [
            "--input", str(scan_path),
            "--output", str(exec_out),
            "--org-display-name", org_display,
        ]
        if event.get("placeholder_ask"):
            exec_argv.append("--placeholder-ask")
        _exec_report.main(exec_argv)

        # Platform report (writes index.html + findings.csv into a dir)
        platform_dir = work / "platform"
        platform_dir.mkdir()
        _platform_report.main([
            "--input", str(scan_path),
            "--output-dir", str(platform_dir),
            "--org-display-name", org_display,
            "--studio-base-url", studio_base,
        ])

        response = {
            "statusCode": 200,
            "executive_html": exec_out.read_text(encoding="utf-8"),
            "platform_html": (platform_dir / "index.html").read_text(encoding="utf-8"),
            "findings_csv": (platform_dir / "findings.csv").read_text(encoding="utf-8"),
        }

        # PDFs are optional — produced only when reportlab is bundled in the
        # package (returned base64-encoded since PDF is binary). Set the event
        # field "pdf": false to skip even when available.
        if event.get("pdf", True):
            response.update(_maybe_pdfs(scan, org_display, studio_base, work, event))

        return response


def _maybe_pdfs(
    scan: dict[str, Any],
    org_display: str,
    studio_base: str,
    work: Path,
    event: dict[str, Any],
) -> dict[str, str]:
    """Return base64 PDFs if reportlab is available, else a skip note."""
    try:
        import base64

        import _lib as L  # noqa: PLC0415
        import generate_pdf_reports as gpdf  # noqa: PLC0415

        if not gpdf.REPORTLAB_AVAILABLE:
            return {"pdf_warning": "PDFs skipped: reportlab not in this package."}

        normalized = L.normalize(scan, {}, {}, None)
        pdf_dir = work / "pdf"
        exec_pdf, plat_pdf = gpdf.build_all(
            normalized, org_display, pdf_dir, studio_base,
            placeholder=bool(event.get("placeholder_ask")),
        )
        return {
            "executive_pdf_base64": base64.b64encode(exec_pdf.read_bytes()).decode("ascii"),
            "platform_pdf_base64": base64.b64encode(plat_pdf.read_bytes()).decode("ascii"),
        }
    except Exception as e:  # noqa: BLE001 - never fail the HTML response over a PDF
        return {"pdf_warning": f"PDF generation skipped: {e}"}
