<#
.SYNOPSIS
    Package the Python Lambda artifacts out of this mixed-language repo.

.DESCRIPTION
    The repo holds scanner + ruleset-publisher + reports in BOTH Python and
    TypeScript. For AWS Lambda we only ship two small Python payloads. This
    script stages JUST those (an allow-list) and ignores everything else —
    no node_modules, no TypeScript, no ruleset-publisher, no tests, no caches.

    Produces two zips (default: <repo>\dist\):

      scanner-source.zip   TRANSPORT — requirements.txt + the scanner package
                           source. Upload this to CloudShell, where you build
                           the deps layer + code zip (deps need Linux wheels).

      reports-lambda.zip   DEPLOYMENT — the 4 stdlib-only report files, already
                           in Lambda's required layout (files at the zip root).
                           Upload this straight to the Lambda Console — no build.

    Built for Windows PowerShell 5.1 (the VDI default). No extra tools needed —
    Compress-Archive is built in.

.PARAMETER OutDir
    Where to write the zips. Defaults to <repo>\dist\.

.EXAMPLE
    ./tools/package-lambda.ps1

.EXAMPLE
    ./tools/package-lambda.ps1 -OutDir C:\temp\lambda-out

.NOTES
    See docs/aws-lambda-walkthrough.md for what to do with each zip.
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

# Clean temp staging area; always removed at the end.
$Stage = Join-Path $env:TEMP ("lambda-stage-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

try {
    # ---- Scanner: source transport zip ----------------------------------
    $scanStage = Join-Path $Stage 'scanner'
    New-Item -ItemType Directory -Force -Path $scanStage | Out-Null

    Copy-Item (Join-Path $ScannerPy 'requirements.txt') $scanStage
    Copy-Item (Join-Path $ScannerPy 'src') (Join-Path $scanStage 'src') -Recurse
    # Bundle the CloudShell build script so the transport zip is self-contained:
    # unzip it in CloudShell, then `bash build-scanner-layer.sh` builds the layer.
    Copy-Item (Join-Path $PSScriptRoot 'build-scanner-layer.sh') $scanStage

    # Strip Python caches so they don't bloat the transport zip.
    Get-ChildItem $scanStage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem $scanStage -Recurse -File -Filter '*.pyc' -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $scannerZip = Join-Path $OutDir 'scanner-source.zip'
    if (Test-Path $scannerZip) { Remove-Item $scannerZip -Force }
    Compress-Archive -Path (Join-Path $scanStage '*') -DestinationPath $scannerZip

    # ---- Reports: deployment-ready zip (4 files at the root) ------------
    $reportsZip = Join-Path $OutDir 'reports-lambda.zip'
    if (Test-Path $reportsZip) { Remove-Item $reportsZip -Force }

    $reportFiles = @(
        'lambda_handler.py',
        'generate_executive_report.py',
        'generate_platform_report.py',
        '_lib.py'
    ) | ForEach-Object { Join-Path $Reports $_ }

    Compress-Archive -Path $reportFiles -DestinationPath $reportsZip

    Write-Host ""
    Write-Host "Built:" -ForegroundColor Green
    Write-Host "  $scannerZip   ->  upload to CloudShell, then build layer + code"
    Write-Host "  $reportsZip   ->  upload straight to the Lambda Console"
    Write-Host ""
    Write-Host "Contents check:"
    Write-Host "  scanner-source.zip:"
    Expand-Archive -Path $scannerZip -DestinationPath (Join-Path $Stage 'verify-scanner') -Force
    Get-ChildItem (Join-Path $Stage 'verify-scanner') -Recurse -File |
        ForEach-Object { Write-Host ("    " + $_.FullName.Substring((Join-Path $Stage 'verify-scanner').Length + 1)) }
    Write-Host "  reports-lambda.zip:"
    Expand-Archive -Path $reportsZip -DestinationPath (Join-Path $Stage 'verify-reports') -Force
    Get-ChildItem (Join-Path $Stage 'verify-reports') -Recurse -File |
        ForEach-Object { Write-Host ("    " + $_.Name) }
}
finally {
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
}
