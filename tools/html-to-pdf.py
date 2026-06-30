"""Export the report HTML files to PDF — standard library only, no pip installs.

This is the "PDF that matches the HTML exactly" path. It drives a browser
that's already on the machine (Microsoft Edge on the Windows VDI, or Chrome /
Chromium on macOS/Linux) in headless "print to PDF" mode, so the PDF is
rendered from the real report HTML + CSS.

This is a LOCAL / VDI step — it needs a browser, so it does not run on AWS
Lambda. For a runs-anywhere PDF (different layout), use
projects/reports/generate_pdf_reports.py instead. The two are complementary:
this one matches the HTML; that one runs in Lambda.

Usage:

    # Convert the two report HTMLs (PDF written next to each)
    python tools/html-to-pdf.py projects/reports/output/executive-report.html \
                                projects/reports/output/platform-report/index.html

    # Choose an output directory
    python tools/html-to-pdf.py output/executive-report.html --out-dir pdf/

    # Force a specific browser if auto-detection misses it
    python tools/html-to-pdf.py report.html --browser "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"

Exit codes: 0 all converted; 1 a conversion failed; 2 no browser found.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Edge is listed first on Windows since it's preinstalled on the VDI.
_WINDOWS_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
_MACOS_CANDIDATES = [
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
_PATH_NAMES = [
    "microsoft-edge",
    "microsoft-edge-stable",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "msedge",
    "chrome",
]


def find_browser() -> str | None:
    """Locate a Chromium-family browser (Edge preferred), or return None."""
    system = platform.system()
    candidates = (
        _WINDOWS_CANDIDATES if system == "Windows"
        else _MACOS_CANDIDATES if system == "Darwin"
        else []
    )
    for path in candidates:
        if Path(path).is_file():
            return path
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _launch_and_capture(cmd: list[str], pdf_path: Path, timeout: float = 60.0) -> bool:
    """Run the headless browser, wait until the PDF is written, then stop it.

    Headless Chrome/Edge often writes the PDF but does NOT exit on its own, so
    instead of waiting for the process we poll until the output file appears and
    its size stops growing, then terminate the browser. Works whether or not the
    browser exits cleanly.
    """
    if pdf_path.exists():
        pdf_path.unlink()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    last_size = -1
    stable = 0
    try:
        while time.time() < deadline:
            if proc.poll() is not None:  # browser exited on its own
                break
            if pdf_path.is_file():
                size = pdf_path.stat().st_size
                if size > 0 and size == last_size:
                    stable += 1
                    if stable >= 2:  # size held steady across two polls -> done
                        break
                else:
                    stable = 0
                last_size = size
            time.sleep(0.4)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return pdf_path.is_file() and pdf_path.stat().st_size > 0


def convert(browser: str, html_path: Path, pdf_path: Path) -> bool:
    """Render html_path to pdf_path with the headless browser. Returns success."""
    file_url = html_path.resolve().as_uri()
    with tempfile.TemporaryDirectory() as profile:
        common = [
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            "--print-to-pdf=" + os.fspath(pdf_path),
            "--no-pdf-header-footer",
        ]
        if platform.system() == "Linux":
            common.append("--no-sandbox")

        # Modern browsers use --headless=new; older accept --headless.
        for headless in ("--headless=new", "--headless"):
            cmd = [browser, headless, *common, file_url]
            if _launch_and_capture(cmd, pdf_path):
                return True
        print(f"  browser produced no PDF for {html_path.name}", file=sys.stderr)
        return False


def _pdf_name(html_path: Path) -> str:
    """executive-report.html -> executive-report; platform-report/index.html -> platform-report."""
    stem = html_path.stem
    if stem == "index" and html_path.parent.name:
        return html_path.parent.name
    return stem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export report HTML to PDF using an installed browser (no pip installs)."
    )
    parser.add_argument("inputs", nargs="+", help="HTML file(s) to convert")
    parser.add_argument("--out-dir", help="Directory for the PDFs (default: next to each input)")
    parser.add_argument("--browser", help="Path to a Chromium-family browser if auto-detection fails")
    args = parser.parse_args(argv)

    browser = args.browser or find_browser()
    if not browser:
        print(
            "No Chromium-family browser found (looked for Edge / Chrome / Chromium).\n"
            "Pass --browser <path>. On the Windows VDI, Edge is usually at:\n"
            r"  C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            file=sys.stderr,
        )
        return 2
    print(f"Using browser: {browser}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for raw in args.inputs:
        html_path = Path(raw)
        if not html_path.is_file():
            print(f"  skip (not found): {raw}", file=sys.stderr)
            ok = False
            continue
        target_dir = out_dir or html_path.parent
        pdf_path = target_dir / f"{_pdf_name(html_path)}.pdf"
        if convert(browser, html_path, pdf_path):
            print(f"  wrote {pdf_path}  ({pdf_path.stat().st_size // 1024} KB)")
        else:
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
