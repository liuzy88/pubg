[CmdletBinding()]
param(
    [ValidateRange(0, 30)]
    [int]$DaysAgo = 1,
    [string]$Config = "conf.json",
    [ValidateRange(1, 100)]
    [int]$Pages,
    [string]$Player,
    [switch]$NoScreenshot
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
$pyLauncherWorks = $false
if ($pyLauncher) {
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $pyLauncher.Source -3 --version *> $null
    $pyLauncherWorks = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $savedErrorActionPreference
}

if ($pyLauncherWorks) {
    $script:PythonCommand = $pyLauncher.Source
    $script:PythonPrefix = @("-3")
}
elseif ($pythonCommand = Get-Command python -ErrorAction SilentlyContinue) {
    $script:PythonCommand = $pythonCommand.Source
    $script:PythonPrefix = @()
}
else {
    throw "Python was not found. Install Python 3.9 or newer and add it to PATH."
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & $script:PythonCommand @script:PythonPrefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

Write-Host "PUBG daily report - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

Write-Host "[1/2] Fetching DAK.GG data..."
$fetchArguments = @(
    "fetch_matches.py",
    "--config", $Config,
    "--days-ago", $DaysAgo
)
if ($PSBoundParameters.ContainsKey("Pages")) {
    $fetchArguments += @("--pages", $Pages)
}
if ($Player) {
    $fetchArguments += @("--player", $Player)
}
Invoke-Python @fetchArguments

Write-Host "[2/2] Generating report..."
$reportArguments = @(
    "generate_report.py",
    "--config", $Config,
    "--days-ago", $DaysAgo
)
if ($NoScreenshot) {
    $reportArguments += "--no-screenshot"
}
Invoke-Python @reportArguments

Write-Host "Done. The report is in the reports directory."
