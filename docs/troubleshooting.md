# Troubleshooting guide

Diagnostics you can copy-paste into a terminal when something breaks. Every command in this guide is **self-contained** — no fill-in-the-blanks, no `<your-path-here>` placeholders. Pick the section that matches your symptom, run the commands top-to-bottom, and stop when something surprises you.

Each section follows the same pattern: **symptom → diagnostic commands → how to read the result → fix.**

If you're already past the install and most things work, the [§5 troubleshooting table in run-commands.md](run-commands.md#5-troubleshooting-quick-table) covers shorter / one-line gotchas.

---

## 1. `SSL: CERTIFICATE_VERIFY_FAILED — self-signed certificate in certificate chain`

The classic corporate-laptop error. Your company's network is intercepting HTTPS with its own root CA. Browsers work because the OS trust store has the CA; Python doesn't see it unless you tell it where the bundle is.

Quick fix overview (full procedure in [installation.md §5.2](installation.md#52-ssl-inspection--corporate-ca)):

1. Export the corporate root CA from `certlm.msc` as **Base-64 X.509 (.CER)**.
2. Save it somewhere stable, e.g. `C:\Users\<you>\corp-ca.cer`.
3. Set `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` env vars pointing at it.
4. **Close + reopen the terminal.**
5. Re-run `scanner probe`.

If you've already done all five and *still* see the error, the diagnostic below tells you which step failed. Run each step in your **activated venv** PowerShell terminal.

> **Shortcut: run the full diagnostic as one script.** From the repo root:
>
> ```powershell
> python tools\diagnose-ssl.py
> ```
>
> [tools/diagnose-ssl.py](../tools/diagnose-ssl.py) is a stdlib-only script that walks through Steps 1.1 → 1.5 in one go, prints `[OK]` / `[WARN]` / `[FAIL]` verdicts at each step, and tells you exactly what to do next. Stop reading the manual steps below — just run the script and read its output. The manual steps are kept for reference / debugging when the script itself misbehaves.

> **Tooling check before you start.** This guide reaches for three commands:
>
> - **`certutil`** — built into Windows. Always available. Used by `diagnose-ssl.py` to decode certs.
> - **`openssl`** — optional. Nicer one-line `subject=` / `issuer=` output than `certutil`. If you have Git for Windows, it ships an `openssl.exe` at `C:\Program Files\Git\usr\bin\openssl.exe` — you can use the full path without changing `PATH`. Confirm with `Get-Command openssl -ErrorAction SilentlyContinue`. If the result is empty, `openssl` isn't on PATH; either use the Git-bundled binary or stick with `certutil`.
> - **PowerShell `Cert:` drive** — built in. The trust-store search commands below use it.
>
> You do **not** need to install OpenSSL separately. Anything OpenSSL does in this guide can be done with `certutil` instead (with slightly less convenient formatting).

### Step 1.1 — Are the env vars visible in *this* terminal?

```powershell
$env:SSL_CERT_FILE
$env:REQUESTS_CA_BUNDLE
```

| Result | Meaning | Next |
|---|---|---|
| Both print a full file path | Env vars visible ✅ | Go to Step 1.2 |
| One or both print blank | Either you set them but didn't reopen the terminal, or the persist call didn't stick | Close PowerShell completely → open a new one → check again. Still blank? Re-run the `SetEnvironmentVariable` lines below. |

**To re-set them persistently (one-time, no admin needed):**

```powershell
[System.Environment]::SetEnvironmentVariable('SSL_CERT_FILE',      "$env:USERPROFILE\corp-ca.cer", 'User')
[System.Environment]::SetEnvironmentVariable('REQUESTS_CA_BUNDLE', "$env:USERPROFILE\corp-ca.cer", 'User')
# Close + reopen PowerShell.
```

(Replace `corp-ca.cer` with whatever you named your bundle file.)

### Step 1.2 — Does the bundle file actually exist and contain a cert?

```powershell
Test-Path $env:SSL_CERT_FILE
Get-Item $env:SSL_CERT_FILE | Select-Object Name, Length
Get-Content $env:SSL_CERT_FILE -TotalCount 1
```

| Result | Meaning | Next |
|---|---|---|
| `True` + Length 1500–4000 + first line `-----BEGIN CERTIFICATE-----` | File looks good ✅ | Go to Step 1.3 |
| `False` | Path in the env var is wrong | Verify the file's actual location with `Get-ChildItem $env:USERPROFILE -Filter *.cer -Recurse`. Update the env var. |
| Length `0` | File is empty | Re-export from `certlm.msc` (see [installation.md §5.2](installation.md#52-ssl-inspection--corporate-ca)) |
| First line is something other than `-----BEGIN CERTIFICATE-----` | Wrong export format (probably DER binary instead of Base-64) | Re-export with **Base-64 encoded X.509 (.CER)** |

### Step 1.3 — Can Python actually parse the bundle?

```powershell
python -c "import ssl, os; print('SSL_CERT_FILE =', os.environ.get('SSL_CERT_FILE')); ctx = ssl.create_default_context(); print('CAs loaded:', len(ctx.get_ca_certs()))"
```

| Result | Meaning | Next |
|---|---|---|
| `CAs loaded: 1` (or more) | Python is reading the file ✅ | Go to Step 1.4 |
| `CAs loaded: 0` | Python sees the env var and the file, but can't parse it as PEM | Most likely a BOM or wrong encoding. Open the file in VS Code, check the bottom-right encoding indicator. It must say `UTF-8` (NOT `UTF-8 with BOM`, NOT `UTF-16 LE`). Re-save with the right encoding via `File → Save with Encoding → UTF-8`. |
| `[Errno 2] No such file or directory` | Path doesn't resolve | Re-check Step 1.2 |

### Step 1.4 — Does TLS to SwaggerHub now succeed?

This bypasses the scanner entirely and tests the raw TLS handshake.

```powershell
python -c "import httpx; r = httpx.get('https://api.swaggerhub.com'); print('HTTP', r.status_code)"
```

| Result | Meaning | Next |
|---|---|---|
| `HTTP 404` or `HTTP 405` or any HTTP status | TLS handshake succeeded ✅ — your bundle is correct | Re-run `scanner probe`. It should also work now. |
| `SSL: CERTIFICATE_VERIFY_FAILED — self-signed certificate in certificate chain` | Same error — the CA in your bundle isn't the one signing SwaggerHub traffic | Go to Step 1.5 |
| `SSL: CERTIFICATE_VERIFY_FAILED — unable to get local issuer certificate` | The root in your bundle is right, but an intermediate CA in the chain is missing | Go to Step 1.6 |

### Step 1.5 — What CA is *actually* signing SwaggerHub on your network?

Sometimes the corporate network has multiple inspection CAs — you might have exported the wrong one. This downloads the leaf cert SwaggerHub presents on your network and decodes it with Windows' built-in `certutil`:

```powershell
python -c "
import ssl, socket
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with socket.create_connection(('api.swaggerhub.com', 443), timeout=10) as s:
    with ctx.wrap_socket(s, server_hostname='api.swaggerhub.com') as ss:
        der = ss.getpeercert(binary_form=True)
        if not der:
            print('NO CERT RECEIVED'); raise SystemExit(1)
        print('Cert received:', len(der), 'bytes')
        print('TLS cipher   :', ss.cipher()[0])
        pem = ssl.DER_cert_to_PEM_cert(der)
        with open('server-cert.pem', 'w') as f: f.write(pem)
        print('Saved to     : server-cert.pem')
"

# Decode the saved cert — built into Windows, no install needed
certutil -dump server-cert.pem | Select-String "Subject:|Issuer:" -Context 0,1
```

> **Why `binary_form=True`:** when `verify_mode = CERT_NONE`, Python's `ssl.getpeercert()` returns `{}` (parsed-dict form) to discourage trusting unverified cert metadata. `binary_form=True` returns the raw DER bytes, which we then convert and dump with `certutil`. If you ever see empty Subject/Issuer arrays from a Python TLS script, this is almost always why.

> **Reading `certutil -dump` output — the formatting gotcha:** `certutil` does NOT put the DN on the same line as `Subject:` or `Issuer:`. Those lines are headers; the actual `CN=`, `O=`, `C=` components appear on **indented lines below** the header. So output like this is **complete, not empty**:
>
> ```
> Subject:
>     CN=api.swaggerhub.com         ← this IS the subject
> Issuer:
>     O=Your Company                ← part of the issuer
>     CN=Your Company SSL Inspect.  ← rest of the issuer — together they ARE the issuer
> ```
>
> If you want everything on single lines, use the OpenSSL fallback below — it formats `subject=` and `issuer=` as one line each.

The **`Issuer`** lines name the CA that signed the leaf cert. On a corporate network with inspection, this will be a corporate-named CA (e.g. `CN=<YourCompany> SSL Inspection CA`, `CN=Zscaler Intermediate Root`, etc.). If it's a public CA name (`DigiCert`, `Sectigo`, `Let's Encrypt`, `Amazon`), your network isn't doing TLS inspection on this URL — the SSL error is from something else (wrong file extension, corrupted bundle, `PYTHONHTTPSVERIFY` env var set to `0`, etc.).

> **TLS-inspection tell-tale:** if Subject is `CN=api.swaggerhub.com` (exact host) rather than `CN=*.swaggerhub.com` (wildcard), and Issuer is a company-named CA, you're definitely being inspected. Public CAs almost always issue wildcards for major SaaS; exact-host certs signed by a non-public CA are a textbook signature of corporate TLS inspection.

#### OpenSSL fallback (if `certutil` output is hard to read)

If you have Git for Windows installed, it ships OpenSSL at `C:\Program Files\Git\usr\bin\openssl.exe`. You can use it without changing PATH:

```powershell
& "C:\Program Files\Git\usr\bin\openssl.exe" x509 -in server-cert.pem -noout -subject -issuer
```

Output looks like:

```
subject=CN=api.swaggerhub.com
issuer=O=Your Company, CN=Your Company SSL Inspection CA
```

One line each — much easier to read than `certutil` for this purpose. If OpenSSL isn't bundled with Git either, stick with the `certutil` output; the data is the same, just split across more lines.

**To see the entire chain (leaf → intermediate → root):** if `openssl` is on PATH:

```powershell
openssl s_client -connect api.swaggerhub.com:443 -showcerts < $null 2>$null |
    Select-String "s:|i:"
```

Each `s:` is a Subject, each `i:` is its Issuer, listed in chain order. The last `i:` is the root — that's what needs to be in your bundle.

### Step 1.5a — Find the matching CA in your trust store, then export it

Once you know the Issuer's `CN`, find it in your Windows trust stores. **Don't open `certlm.msc` and scroll** — PowerShell finds it in one command and can also export it directly, which is safer than the GUI wizard (no risk of picking DER or saving with a BOM).

#### Find it

```powershell
# Replace with the CN value you saw under Issuer
$search = "Your Company SSL Inspection CA"

Get-ChildItem -Recurse Cert:\LocalMachine, Cert:\CurrentUser -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -like "*CN=$search*" } |
    Select-Object @{N='Location';E={$_.PSParentPath -replace '.*Certificate::',''}},
                  Subject, Thumbprint, NotAfter |
    Format-Table -AutoSize
```

You'll see one or more rows. Common outcomes:

| Result | Meaning | Next |
|---|---|---|
| One row | Single cert match — easy | Export it (next block) |
| Multiple rows, **same Thumbprint** | Same cert listed in multiple stores (often `LocalMachine\Root` + `CurrentUser\Root` because Group Policy pushed it to both) | Pick any row — export once |
| Multiple rows, **different Thumbprints** | Multiple distinct certs sharing the name (e.g. old + new rotation pair) | Export each; **append** into one bundle file |

> **`certlm.msc` vs `certmgr.msc` — important distinction:** `certlm.msc` shows **only Local Machine** certs. To see Current User certs (anything reported by PowerShell as `CurrentUser\...`), open `certmgr.msc` instead (note the `mgr`, not `lm`). Mapping:
>
> | PowerShell `Location` | MMC snap-in | Folder inside |
> |---|---|---|
> | `LocalMachine\Root` | `certlm.msc` | Trusted Root Certification Authorities → Certificates |
> | `LocalMachine\CA` | `certlm.msc` | Intermediate Certification Authorities → Certificates |
> | `CurrentUser\Root` | `certmgr.msc` | Trusted Root Certification Authorities → Certificates |
> | `CurrentUser\CA` | `certmgr.msc` | Intermediate Certification Authorities → Certificates |
>
> But you don't need either MMC for the export below — they're listed only for when you want to visually verify what PowerShell found.

#### Export directly via PowerShell (recommended — no wizard, no encoding mistakes)

```powershell
# Paste the Thumbprint from the search output (40-char hex string)
$tp = '7A3F9C12B4D8E5F6A1B2C3D4E5F6A1B2C3D4E5F6'

$cert = Get-ChildItem -Recurse Cert:\LocalMachine, Cert:\CurrentUser -ErrorAction SilentlyContinue |
        Where-Object Thumbprint -eq $tp |
        Select-Object -First 1

if (-not $cert) {
    Write-Host "Cert with thumbprint $tp not found" -ForegroundColor Red
} else {
    $pem = "-----BEGIN CERTIFICATE-----`n" +
           [System.Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks') +
           "`n-----END CERTIFICATE-----"
    Set-Content -Path "$env:USERPROFILE\corp-ca.cer" -Value $pem -Encoding ASCII -Force
    Write-Host "Exported to: $env:USERPROFILE\corp-ca.cer" -ForegroundColor Green

    # Sanity check — should print -----BEGIN CERTIFICATE-----
    Get-Content "$env:USERPROFILE\corp-ca.cer" -TotalCount 1
}
```

This is the **safer alternative to the `certlm.msc` export wizard**:

- Always writes Base-64 PEM (no risk of accidentally picking DER)
- Always writes plain ASCII (no UTF-16 BOM headaches)
- One command, no clicks, no wizard

#### If you need both certs (different thumbprints from the search)

```powershell
# First cert (overwrite)
$tp = '<first-thumbprint>'
$cert = Get-ChildItem -Recurse Cert:\LocalMachine, Cert:\CurrentUser -ErrorAction SilentlyContinue |
        Where-Object Thumbprint -eq $tp | Select-Object -First 1
$pem = "-----BEGIN CERTIFICATE-----`n" +
       [System.Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks') +
       "`n-----END CERTIFICATE-----"
Set-Content -Path "$env:USERPROFILE\corp-ca.cer" -Value $pem -Encoding ASCII -Force

# Second cert (append)
$tp = '<second-thumbprint>'
$cert = Get-ChildItem -Recurse Cert:\LocalMachine, Cert:\CurrentUser -ErrorAction SilentlyContinue |
        Where-Object Thumbprint -eq $tp | Select-Object -First 1
$pem = "-----BEGIN CERTIFICATE-----`n" +
       [System.Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks') +
       "`n-----END CERTIFICATE-----"
Add-Content -Path "$env:USERPROFILE\corp-ca.cer" -Value $pem -Encoding ASCII

# Verify both landed
(Get-Content "$env:USERPROFILE\corp-ca.cer") -match 'BEGIN CERTIFICATE' | Measure-Object | Select Count
# Expect: Count : 2
```

#### Update env vars and re-verify

```powershell
[System.Environment]::SetEnvironmentVariable('SSL_CERT_FILE',      "$env:USERPROFILE\corp-ca.cer", 'User')
[System.Environment]::SetEnvironmentVariable('REQUESTS_CA_BUNDLE', "$env:USERPROFILE\corp-ca.cer", 'User')

# Close PowerShell completely, open a fresh window, then:
python tools\diagnose-ssl.py
```

Step 4 of the diagnostic should now print `[OK] TLS handshake succeeded`. If yes, `scanner probe` will work too. If it still fails with `unable to get local issuer certificate`, you're missing an intermediate — see Step 1.6.

### Step 1.6 — Missing intermediate CA in the chain

If the error specifically says `unable to get local issuer certificate`, the chain looks like:

```
SwaggerHub leaf  →  Corporate Intermediate  →  Corporate Root  ← you have this
                    ↑ but Python can't build through here
```

You need to append the intermediate to your bundle.

#### Find the intermediate

The intermediate's **Subject** equals the **Issuer of your existing root-CA cert**. To see what to search for, run:

```powershell
# Get the Issuer DN of the root you already exported
& "C:\Program Files\Git\usr\bin\openssl.exe" x509 -in $env:USERPROFILE\corp-ca.cer -noout -issuer
# Or with certutil if openssl isn't available:
certutil -dump $env:USERPROFILE\corp-ca.cer | Select-String "Issuer:" -Context 0,3
```

Then search for that Subject in the **Intermediate** store:

```powershell
$search = "<CN from the issuer line above>"

Get-ChildItem -Recurse Cert:\LocalMachine\CA, Cert:\CurrentUser\CA -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -like "*CN=$search*" } |
    Select-Object @{N='Location';E={$_.PSParentPath -replace '.*Certificate::',''}},
                  Subject, Thumbprint, NotAfter |
    Format-Table -AutoSize
```

(`Cert:\...\CA` is where Windows stores intermediate CAs, even though the variable name might suggest otherwise.)

#### Append the intermediate to your existing bundle

Use the same PowerShell-direct-export pattern from Step 1.5a, but with `Add-Content` to append rather than overwrite:

```powershell
$tp = '<intermediate-cert-thumbprint>'

$cert = Get-ChildItem -Recurse Cert:\LocalMachine, Cert:\CurrentUser -ErrorAction SilentlyContinue |
        Where-Object Thumbprint -eq $tp |
        Select-Object -First 1

$pem = "-----BEGIN CERTIFICATE-----`n" +
       [System.Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks') +
       "`n-----END CERTIFICATE-----"
Add-Content -Path "$env:USERPROFILE\corp-ca.cer" -Value $pem -Encoding ASCII

# Verify the bundle now has two certs
(Get-Content "$env:USERPROFILE\corp-ca.cer") -match 'BEGIN CERTIFICATE' | Measure-Object | Select Count
# Expect: Count : 2 (or higher if you appended multiple)
```

Order in the bundle doesn't matter — OpenSSL / Python parse all the `BEGIN CERTIFICATE` blocks and pick the right one to verify against. Just make sure both are in there.

#### Alternative: combine separate `.cer` files into one bundle

If you already exported the intermediate to its own file (e.g. via the wizard), combine them:

```powershell
Get-Content "$env:USERPROFILE\corp-ca.cer", "$env:USERPROFILE\corp-intermediate.cer" |
    Set-Content -Encoding ASCII "$env:USERPROFILE\corp-ca-bundle.pem"

# Verify
(Get-Content "$env:USERPROFILE\corp-ca-bundle.pem") -match 'BEGIN CERTIFICATE' | Measure-Object | Select Count

# Then point env vars at the combined file
[System.Environment]::SetEnvironmentVariable('SSL_CERT_FILE',      "$env:USERPROFILE\corp-ca-bundle.pem", 'User')
[System.Environment]::SetEnvironmentVariable('REQUESTS_CA_BUNDLE', "$env:USERPROFILE\corp-ca-bundle.pem", 'User')
```

Reopen the terminal and retry from Step 1.4 (or just re-run `python tools\diagnose-ssl.py` and look at Step 4's verdict).

---

## 2. `Activate.ps1 cannot be loaded because running scripts is disabled on this system`

PowerShell's default execution policy blocks unsigned local scripts. Fix is one line, no admin needed:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# Answer Y to the confirmation prompt.

# Verify:
Get-ExecutionPolicy -Scope CurrentUser
# Expect: RemoteSigned
```

This allows local scripts (like `.venv\Scripts\Activate.ps1`) to run while still blocking unsigned remote scripts you might download.

---

## 3. `scanner: The term 'scanner' is not recognized`

The venv either isn't activated, or activation didn't add the venv's `Scripts\` folder to PATH.

```powershell
# Check whether you're in a venv
$env:VIRTUAL_ENV
```

| Result | Meaning | Fix |
|---|---|---|
| Prints a full path ending in `\.venv` | venv is active, but `scanner` still missing | Re-install: `pip install -e . --no-deps` from inside the project folder |
| Prints blank | venv isn't active | Activate it: `.\.venv\Scripts\Activate.ps1` from the project folder |

After activation, your prompt prefix should change to `(.venv)`. Confirm `scanner` resolves to the venv copy:

```powershell
Get-Command scanner | Select-Object Source
# Expect: ...\.venv\Scripts\scanner.exe
```

---

## 4. `scanner probe` returns `auth_failed`

TLS works, but SwaggerHub rejected your API key.

```powershell
# Check that .env actually has a key set
Get-Content projects\swagger-studio-scanner\.env | Select-String "SWAGGERHUB_API_KEY"
```

If the line is empty or `SWAGGERHUB_API_KEY=`, paste your key in. If a key is set but probe still fails:

1. Go to https://app.swaggerhub.com/settings/apiKey
2. Verify the key hasn't expired
3. Verify the key is **org-owner scope** (member-scoped keys return partial API lists and may fail probe)
4. If unsure, generate a fresh key and replace the value in `.env`

---

## 5. `scanner probe` returns `org_unreachable`

TLS + auth work, but the org slug in `.env` is wrong.

```powershell
Get-Content projects\swagger-studio-scanner\.env | Select-String "SWAGGERHUB_ORG"
```

Compare what you see to the URL when you open your org in SwaggerHub: `https://app.swaggerhub.com/organization/<slug>`. The `<slug>` portion is what `SWAGGERHUB_ORG` should equal. Common gotchas:

- It's **case-sensitive**
- It's the URL slug, not the human display name
- It's the org's **Name**, not its numeric / UUID **Organization ID**

---

## 6. `pip install` fails with `SSL: CERTIFICATE_VERIFY_FAILED`

Same root cause as §1, but pip has its own override. The `SSL_CERT_FILE` env var should cover it too, but if pip is stubborn:

```powershell
# Tell pip explicitly to use your bundle
pip config set global.cert "$env:SSL_CERT_FILE"

# Verify
pip config list
# Expect: global.cert='C:\Users\...\corp-ca-bundle.pem'
```

If pip then fails with a different error like `Could not fetch URL` or timeout, the issue is the corporate proxy, not the cert — set:

```powershell
$env:HTTPS_PROXY = "http://proxy.corp.example:8080"
$env:HTTP_PROXY  = "http://proxy.corp.example:8080"
# Get the right proxy URL from your IT team — same one your browser uses.
```

To persist these too, use `SetEnvironmentVariable(..., 'User')` the same way you did for SSL_CERT_FILE.

---

## 7. `python -m venv .venv` fails or produces an unusable venv

Most common cause on Windows: an old `.venv` folder from a previous Python version is sitting in the project directory. `python -m venv` won't always overwrite it cleanly.

```powershell
# From the project folder (e.g. projects\swagger-studio-scanner\python)
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python --version       # confirm 3.13 or higher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
```

If `python --version` shows something below 3.13, you're picking up an older Python from PATH. Either install 3.13+ explicitly, or use the full path: `& "C:\Path\To\Python313\python.exe" -m venv .venv`.

---

## 8. Reports complain about ownership YAML

The reports project's built-in YAML parser only handles **flat** `key: value` files. Nested YAML (with team/domain/contact_email blocks under each key) needs PyYAML installed:

```powershell
pip install --user pyyaml
```

`--user` installs into your user profile rather than the venv — that way every venv on your machine can use it without a separate install. Confirm:

```powershell
python -c "import yaml; print('PyYAML version:', yaml.__version__)"
```

---

## 9. Reports run but the output looks wrong / sections missing

The reports degrade gracefully when optional inputs (ownership map, rule display names, CoP guidance, asks file) are missing — they print a tier-status summary at the end of each run showing exactly what fell back. Read that summary first:

```
Wrote output/executive-report.html
Executive report — render summary
  Tier 1 sections: title, headline, tiles 1-4, Pareto, severity, methodology
  Tier 1 substitute: 'unpublished among failing' tile (...)
  Tier 3 rule display names: not provided
  Tier 3 asks file: placeholder mode
```

Lines starting with `Tier 1 substitute` mean a default fallback rendered. Lines starting with `Tier 3 ... not provided` mean an optional input file was omitted. Neither is a bug — they're the report telling you exactly which sections are running from which input. See [reports.md §6](reports.md#6-reading-the-tier-status-stdout-summary) for the full list of summary lines.

---

## 10. Still stuck?

If none of the above match your symptom, capture the following and share it (the SSL pieces are scrubbed-safe — no secrets in here):

```powershell
# Run from your activated venv
python --version
pip --version
Get-Command python | Select-Object Source
Get-Command scanner | Select-Object Source
$env:VIRTUAL_ENV
$env:SSL_CERT_FILE
$env:REQUESTS_CA_BUNDLE
Test-Path $env:SSL_CERT_FILE
$env:HTTPS_PROXY
scanner version
scanner probe
```

That output identifies: Python version, venv state, cert config, proxy state, and the actual probe failure mode. With that, the next debugging step is almost always obvious.

---

## See also

- [installation.md](installation.md) — toolchain install (Python 3.13+, venv, pip) and corporate-laptop gotchas in §5
- [run-commands.md](run-commands.md) — every command + every flag, with a one-line troubleshooting table in §5
- [reports.md](reports.md) — report generators and their tier-status summary lines
