<#
.SYNOPSIS
    Build the THREE Lambda zips for hand-off (no deploy, no AWS calls).

.DESCRIPTION
    Produces (default <repo>\dist\):
      1. scanner-deps-layer.zip   dependencies, as a Lambda Layer (python\ layout)
      2. scanner-code.zip         scanner code (handler: swagger_studio_scanner.lambda_handler.handler)
      3. reports-code.zip         reports code (handler: lambda_handler.handler)

    Upload the three zips to SharePoint (or wherever) and have whoever owns AWS
    create the functions. Exact settings: docs/aws-lambda-handoff.md.

    The dependency layer is built with manylinux wheels for the Lambda runtime
    via pip --platform, so it is Lambda-correct even though it is built on
    Windows. If your VDI's pip can't do the --platform download, build ONLY the
    layer in CloudShell (see the fallback note printed at the end) — the two
    code zips always build fine here.

.PARAMETER OutDir
    Output directory. Defaults to <repo>\dist\.

.PARAMETER PyVersion
    Target Lambda Python version. Defaults to 3.13.

.EXAMPLE
    ./tools/build-lambda-zips.ps1
#>
#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutDir,
    [string]$PyVersion = '3.13'
)

$ErrorActionPreference = 'Stop'

$RepoRoot  = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ScannerPy = Join-Path $RepoRoot 'projects\swagger-studio-scanner\python'
$Reports   = Join-Path $RepoRoot 'projects\reports'

if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$Stage = Join-Path $env:TEMP ("lambda-zips-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

try {
    # ---- 2. Scanner code (pure Python — always works) -------------------
    Write-Host "==> scanner-code.zip ..."
    $scannerZip = Join-Path $OutDir 'scanner-code.zip'
    if (Test-Path $scannerZip) { Remove-Item $scannerZip -Force }
    # Stage a clean copy without __pycache__, then zip so swagger_studio_scanner\ is at root.
    $pkgStage = Join-Path $Stage 'scanner'
    New-Item -ItemType Directory -Force -Path $pkgStage | Out-Null
    Copy-Item (Join-Path $ScannerPy 'src\swagger_studio_scanner') (Join-Path $pkgStage 'swagger_studio_scanner') -Recurse
    Get-ChildItem $pkgStage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Compress-Archive -Path (Join-Path $pkgStage 'swagger_studio_scanner') -DestinationPath $scannerZip

    # ---- 3. Reports code (+ reportlab/pillow for PDF, manylinux) --------
    Write-Host "==> reports-code.zip  (5 modules + reportlab/pillow for PDF) ..."
    $reportsZip = Join-Path $OutDir 'reports-code.zip'
    if (Test-Path $reportsZip) { Remove-Item $reportsZip -Force }
    $rStage = Join-Path $Stage 'reports'
    New-Item -ItemType Directory -Force -Path $rStage | Out-Null
    @('lambda_handler.py','generate_executive_report.py','generate_platform_report.py','generate_pdf_reports.py','_lib.py') |
        ForEach-Object { Copy-Item (Join-Path $Reports $_) $rStage }
    & python -m pip install `
        -r (Join-Path $Reports 'requirements-pdf.txt') `
        --target $rStage `
        --python-version $PyVersion `
        --only-binary=:all: `
        --platform manylinux2014_x86_64 `
        --quiet
    Get-ChildItem $rStage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Compress-Archive -Path (Join-Path $rStage '*') -DestinationPath $reportsZip

    # ---- 1. Dependency layer (manylinux wheels via pip --platform) ------
    Write-Host "==> scanner-deps-layer.zip  (downloading manylinux wheels for python$PyVersion) ..."
    $layerZip = Join-Path $OutDir 'scanner-deps-layer.zip'
    $layerPy  = Join-Path $Stage 'layer\python'
    New-Item -ItemType Directory -Force -Path $layerPy | Out-Null
    $layerOk = $true
    try {
        & python -m pip install `
            -r (Join-Path $ScannerPy 'requirements.txt') `
            --target $layerPy `
            --python-version $PyVersion `
            --only-binary=:all: `
            --platform manylinux2014_x86_64 `
            --quiet
        if ($LASTEXITCODE -ne 0) { $layerOk = $false }
    } catch { $layerOk = $false }

    if ($layerOk) {
        Get-ChildItem (Join-Path $Stage 'layer') -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force
        if (Test-Path $layerZip) { Remove-Item $layerZip -Force }
        Compress-Archive -Path (Join-Path $Stage 'layer\python') -DestinationPath $layerZip
    }

    Write-Host ""
    Write-Host "Built in $OutDir :" -ForegroundColor Green
    Write-Host ("  {0,-26} {1}" -f 'scanner-code.zip',  (Get-Item $scannerZip).Length)
    Write-Host ("  {0,-26} {1}" -f 'reports-code.zip',  (Get-Item $reportsZip).Length)
    if ($layerOk) {
        Write-Host ("  {0,-26} {1}" -f 'scanner-deps-layer.zip', (Get-Item $layerZip).Length)
    } else {
        Write-Host "  scanner-deps-layer.zip   FAILED on this machine's pip." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Build ONLY the layer in CloudShell instead:" -ForegroundColor Yellow
        Write-Host "    mkdir -p python && pip install -r requirements.txt --target python \\"
        Write-Host "        --python-version $PyVersion --only-binary=:all: --platform manylinux2014_x86_64"
        Write-Host "    zip -r scanner-deps-layer.zip python"
        Write-Host "  (upload the scanner's requirements.txt to CloudShell first)"
    }
    Write-Host ""
    Write-Host "Hand the zips to whoever creates the Lambda functions. Settings: docs/aws-lambda-handoff.md"
}
finally {
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
}
