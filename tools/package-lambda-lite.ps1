<#
.SYNOPSIS
    Package the LITE Lambda variant as ONE self-contained bundle (Windows VDI).

.DESCRIPTION
    The lite flow ships a single bundle you upload to CloudShell once. Inside
    CloudShell you run the bundled deploy + run scripts — no S3, no SSM.

    Produces (default <repo>\dist\):
      lambda-lite.zip  — requirements.txt, src\swagger_studio_scanner\,
                         reports\*.py, build-scanner-layer.sh,
                         deploy-lambda-lite.sh, run-lambda-lite.sh

.PARAMETER OutDir
    Where to write the zip. Defaults to <repo>\dist\.

.EXAMPLE
    ./tools/package-lambda-lite.ps1

.NOTES
    See docs/aws-lambda-lite.md for the full flow.
#>
#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutDir
)

$ErrorActionPreference = 'Stop'

$RepoRoot  = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ScannerPy = Join-Path $RepoRoot 'projects\swagger-studio-scanner\python'
$Reports   = Join-Path $RepoRoot 'projects\reports'

if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$Stage = Join-Path $env:TEMP ("lambda-lite-" + [System.Guid]::NewGuid().ToString('N'))
$Bundle = Join-Path $Stage 'lambda-lite'
New-Item -ItemType Directory -Force -Path (Join-Path $Bundle 'reports') | Out-Null

try {
    # Scanner source
    Copy-Item (Join-Path $ScannerPy 'requirements.txt') $Bundle
    Copy-Item (Join-Path $ScannerPy 'src') (Join-Path $Bundle 'src') -Recurse

    # Reports source (+ generate_pdf_reports.py + requirements-pdf.txt for PDF)
    @('lambda_handler.py','generate_executive_report.py','generate_platform_report.py',
      'generate_pdf_reports.py','_lib.py','requirements-pdf.txt') |
        ForEach-Object { Copy-Item (Join-Path $Reports $_) (Join-Path $Bundle 'reports') }

    # Bundled scripts
    @('build-scanner-layer.sh','deploy-lambda-lite.sh','run-lambda-lite.sh') |
        ForEach-Object { Copy-Item (Join-Path $PSScriptRoot $_) $Bundle }

    # Strip caches
    Get-ChildItem $Bundle -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem $Bundle -Recurse -File -Filter '*.pyc' -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $zip = Join-Path $OutDir 'lambda-lite.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path $Bundle -DestinationPath $zip

    Write-Host "Built: $zip" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: upload it to CloudShell, then:"
    Write-Host "  unzip lambda-lite.zip && cd lambda-lite"
    Write-Host "  bash deploy-lambda-lite.sh    # creates both Lambda functions"
    Write-Host "  bash run-lambda-lite.sh       # runs scan -> reports -> HTML"
}
finally {
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
}
