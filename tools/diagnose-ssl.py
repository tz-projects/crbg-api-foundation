"""Self-contained SSL diagnostic for the corporate-laptop install.

Standard-library only — runs on any Python 3.10+ with no `pip install` needed.
Walks through the same six steps as docs/troubleshooting.md §1 and prints
verdicts you can act on directly.

Usage (from anywhere):

    python tools/diagnose-ssl.py

Or, on Windows:

    python tools\\diagnose-ssl.py

It checks, in order:
  1. SSL_CERT_FILE / REQUESTS_CA_BUNDLE env vars
  2. Whether the file in those vars exists and looks like PEM
  3. Whether Python's ssl module can load it
  4. Whether a real HTTPS handshake to api.swaggerhub.com succeeds with the
     bundle as the trust root
  5. If 4 fails: connects with verification OFF, downloads the actual leaf
     cert your network presents, saves it to server-cert.pem, and (on Windows)
     dumps Subject / Issuer via certutil so you can identify which CA you
     need to add to your bundle
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
from pathlib import Path

HOST = "api.swaggerhub.com"
PORT = 443
LEAF_CERT_OUT = Path("server-cert.pem")


def _h(title: str) -> None:
    """Print a step header."""
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def step_1_env_vars() -> tuple[str | None, str | None]:
    _h("Step 1 — Are the env vars visible in *this* terminal?")
    ssl_cert = os.environ.get("SSL_CERT_FILE")
    reqs_ca = os.environ.get("REQUESTS_CA_BUNDLE")
    print(f"  SSL_CERT_FILE      = {ssl_cert or '(not set)'}")
    print(f"  REQUESTS_CA_BUNDLE = {reqs_ca or '(not set)'}")
    if not ssl_cert and not reqs_ca:
        _fail("Neither env var is set in this terminal.")
        print("  → If you've already set them with SetEnvironmentVariable, you may need to")
        print("    fully close PowerShell and open a fresh terminal. Then re-run this script.")
    elif not ssl_cert:
        _warn("SSL_CERT_FILE is unset but REQUESTS_CA_BUNDLE is set.")
        print("  → Many libraries fall back to certifi without SSL_CERT_FILE. Set both for safety.")
    elif not reqs_ca:
        _warn("REQUESTS_CA_BUNDLE is unset but SSL_CERT_FILE is set.")
    else:
        _ok("Both env vars are set in this terminal.")
    return ssl_cert, reqs_ca


def step_2_file_exists(bundle_path: str | None) -> Path | None:
    _h("Step 2 — Does the bundle file actually exist and look like PEM?")
    if not bundle_path:
        _fail("No bundle path to check (Step 1 found no env var).")
        return None
    p = Path(bundle_path)
    if not p.exists():
        _fail(f"File does not exist: {p}")
        print("  → Re-check the path in your env var. List with: ")
        print("    Get-ChildItem $env:USERPROFILE -Filter *.cer,*.pem -Recurse -ErrorAction SilentlyContinue")
        return None
    size = p.stat().st_size
    print(f"  Path : {p}")
    print(f"  Size : {size} bytes")
    if size == 0:
        _fail("File is empty.")
        return None
    try:
        first_line = p.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except Exception as e:
        _fail(f"Could not read file: {e}")
        return None
    print(f"  Head : {first_line!r}")
    if "BEGIN CERTIFICATE" not in first_line:
        _fail("First line is not '-----BEGIN CERTIFICATE-----'.")
        print("  → File is probably DER (binary) or has a BOM. Re-export as")
        print("    'Base-64 encoded X.509 (.CER)' from certlm.msc, or in VS Code")
        print("    save with encoding 'UTF-8' (NOT 'UTF-8 with BOM').")
        return None
    _ok("File exists, non-empty, starts with -----BEGIN CERTIFICATE-----.")
    return p


def step_3_python_parses(bundle: Path | None) -> int:
    _h("Step 3 — Can Python's ssl module load the bundle?")
    if not bundle:
        _fail("No bundle to load (Step 2 failed).")
        return 0
    try:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=str(bundle))
        cas = ctx.get_ca_certs()
        n = len(cas)
        if n == 0:
            _fail("Python loaded the file but parsed 0 certificates.")
            print("  → Likely a BOM or wrong encoding. Re-save as plain UTF-8.")
        else:
            _ok(f"Python parsed {n} certificate(s) from the bundle.")
            for i, c in enumerate(cas, 1):
                subj = dict(x[0] for x in c.get("subject", ())).get("commonName", "?")
                print(f"      [{i}] CN = {subj}")
        return n
    except ssl.SSLError as e:
        _fail(f"ssl.load_verify_locations failed: {e}")
        return 0
    except Exception as e:
        _fail(f"Unexpected error: {e}")
        return 0


def step_4_handshake(bundle: Path | None) -> bool:
    _h(f"Step 4 — Does a real TLS handshake to {HOST} succeed with the bundle?")
    if not bundle:
        _fail("No bundle to test (Step 2 failed).")
        return False
    try:
        ctx = ssl.create_default_context(cafile=str(bundle))
        with socket.create_connection((HOST, PORT), timeout=10) as s:
            with ctx.wrap_socket(s, server_hostname=HOST) as ss:
                _ok(f"TLS handshake succeeded. Cipher: {ss.cipher()[0]}")
                _ok("Your bundle is correct. scanner probe should now work.")
                return True
    except ssl.SSLCertVerificationError as e:
        _fail(f"Cert verify failed: {e}")
        if "self-signed" in str(e) or "unable to get local issuer" in str(e):
            print("  → The CA in your bundle isn't the one signing SwaggerHub on your network.")
            print("    Step 5 will identify which CA is actually presented.")
        return False
    except (socket.timeout, TimeoutError):
        _fail(f"Connection to {HOST}:{PORT} timed out.")
        print("  → Probably a proxy issue, not a cert issue.")
        print("    Set HTTPS_PROXY and re-test. See installation.md §5.1.")
        return False
    except OSError as e:
        _fail(f"Network error: {e}")
        return False


def step_5_inspect_leaf() -> None:
    _h(f"Step 5 — What cert does {HOST} actually present on this network?")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((HOST, PORT), timeout=10) as s:
            with ctx.wrap_socket(s, server_hostname=HOST) as ss:
                der = ss.getpeercert(binary_form=True)
                if not der:
                    _fail("No certificate received from the server.")
                    return
                _ok(f"Cert received: {len(der)} bytes. Cipher: {ss.cipher()[0]}")
                pem = ssl.DER_cert_to_PEM_cert(der)
                LEAF_CERT_OUT.write_text(pem, encoding="utf-8")
                _ok(f"Leaf cert saved to: {LEAF_CERT_OUT.resolve()}")
    except Exception as e:
        _fail(f"Could not connect to capture cert: {e}")
        return

    # On Windows, certutil is built-in and can dump the cert.
    if platform.system() == "Windows" and shutil.which("certutil"):
        print()
        print("  -- Subject / Issuer (via Windows certutil) --")
        try:
            out = subprocess.run(
                ["certutil", "-dump", str(LEAF_CERT_OUT)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in out.stdout.splitlines():
                stripped = line.strip()
                if any(k in line for k in ("Subject:", "Issuer:", "CN=", "O=")):
                    print(f"    {stripped}")
        except Exception as e:
            _warn(f"certutil failed: {e}")
    elif shutil.which("openssl"):
        print()
        print("  -- Subject / Issuer (via openssl) --")
        try:
            out = subprocess.run(
                ["openssl", "x509", "-in", str(LEAF_CERT_OUT), "-noout",
                 "-subject", "-issuer"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in out.stdout.splitlines():
                print(f"    {line.strip()}")
        except Exception as e:
            _warn(f"openssl failed: {e}")
    else:
        _warn("Neither certutil (Windows) nor openssl is available to decode the cert.")
        print(f"  → Open {LEAF_CERT_OUT} manually, or install openssl, then re-run.")

    print()
    print("  How to read this:")
    print("    - 'Issuer' is the CA that signed the leaf. On a corporate network with")
    print("      TLS inspection, this will be a company-named CA — that's the one your")
    print("      bundle must contain.")
    print("    - If 'Issuer' looks like a public CA (DigiCert / Sectigo / Amazon / etc.),")
    print("      your network is NOT doing TLS inspection on this URL. The SSL error")
    print("      is from something else (BOM in bundle, wrong file, etc.) — back to Steps 2-3.")


def main() -> int:
    print(f"SSL diagnostic for {HOST}:{PORT}")
    print(f"Python : {sys.version.split()[0]} ({sys.executable})")
    print(f"OS     : {platform.system()} {platform.release()}")

    ssl_cert, reqs_ca = step_1_env_vars()
    bundle_path = ssl_cert or reqs_ca
    bundle = step_2_file_exists(bundle_path)
    step_3_python_parses(bundle)
    if step_4_handshake(bundle):
        # Bundle works — no need to inspect the leaf.
        return 0
    step_5_inspect_leaf()

    _h("Next steps")
    print("  Read the Issuer printed in Step 5. Then:")
    print("  - In certlm.msc, find the CA with that Subject in:")
    print("      Trusted Root Certification Authorities → Certificates")
    print("    Export as 'Base-64 encoded X.509 (.CER)'.")
    print("  - Update SSL_CERT_FILE / REQUESTS_CA_BUNDLE to point at the new file.")
    print("  - Close + reopen PowerShell. Re-run this script.")
    print("  - Full walkthrough: docs/troubleshooting.md §1.5 and §1.6.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
