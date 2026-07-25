#Requires -Version 5.1
<#
  One-shot GitHub setup for AI Cost History Hub.
  Requires: gh auth login (or GH_TOKEN)

  Usage:
    cd E:\xiangmu\wangquanti
    pwsh -File docs\github-setup\run-github-setup.ps1
#>

$ErrorActionPreference = "Stop"
$Repo = "zheyan2517/ai-cost-history-hub"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path (Join-Path $Root ".git"))) {
  $Root = "E:\xiangmu\wangquanti"
}
Set-Location $Root

function Ensure-Gh {
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) not found. Install from https://cli.github.com/"
  }
  $status = gh auth status 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged in. Starting gh auth login (browser)..."
    gh auth login -h github.com -p https -w
  }
}

Ensure-Gh

Write-Host "==> Ensure public visibility"
gh repo edit $Repo --visibility public 2>$null
gh repo edit $Repo --accept-visibility-change-consequences 2>$null

Write-Host "==> About description + homepage"
gh repo edit $Repo `
  --description "Local AI coding-agent history + API cost analytics (loopback-only)." `
  --homepage "https://github.com/zheyan2517/ai-cost-history-hub"

Write-Host "==> Topics"
gh repo edit $Repo --add-topic cost-tracking
gh repo edit $Repo --add-topic coding-agents
gh repo edit $Repo --add-topic python
gh repo edit $Repo --add-topic tauri
gh repo edit $Repo --add-topic dashboard
gh repo edit $Repo --add-topic openai
gh repo edit $Repo --add-topic open-source
gh repo edit $Repo --add-topic local-first

Write-Host "==> Release v0.1.0"
$notes = Join-Path $PSScriptRoot "RELEASE_v0.1.0.md"
$existing = gh release view v0.1.0 --repo $Repo 2>$null
if ($LASTEXITCODE -eq 0) {
  Write-Host "Release v0.1.0 already exists — skipping create"
} else {
  gh release create v0.1.0 `
    --repo $Repo `
    --title "v0.1.0" `
    --notes-file $notes
}

Write-Host "==> Issues"
function Ensure-Issue([string]$title, [string]$body) {
  $found = gh issue list --repo $Repo --state all --search "$title" --json number,title --jq ".[].title" 2>$null
  if ($found -and ($found | Where-Object { $_ -eq $title })) {
    Write-Host "Issue already exists: $title"
    return
  }
  gh issue create --repo $Repo --title $title --body $body | Write-Host
}

Ensure-Issue `
  "[Bug] Improve first-run errors when Python or ports are unavailable" `
  @"
## Summary
New users may see unclear failures when Python is missing from PATH or when ports 8753/8740 are busy.

## Expected
Clear, actionable error messages with install/next-step hints.

## Acceptance criteria
- [ ] Missing Python shows a clear message and download hint
- [ ] Port-in-use message includes the next free port behavior
- [ ] Documented in README troubleshooting
"@

Ensure-Issue `
  "[Feature] Add macOS and Linux start scripts" `
  @"
## Problem
Windows has start.bat / start-cost-dashboard.bat, but macOS/Linux users need shell equivalents.

## Proposed solution
Add start.sh and start-cost-dashboard.sh with the same loopback defaults (127.0.0.1).

## Acceptance criteria
- [ ] Scripts are executable and documented in README
- [ ] Behavior matches Windows launchers
"@

Ensure-Issue `
  "[Feature] Automated smoke test for coordinator health checks" `
  @"
## Problem
Coordinator start/status/stop is manual; regressions are easy to miss.

## Proposed solution
Add a lightweight script or CI job that starts the cost dashboard on a free loopback port, checks HTTP 200, and stops cleanly.

## Acceptance criteria
- [ ] Can run locally without external network
- [ ] Documented under development/testing notes
"@

Write-Host ""
Write-Host "Done."
Write-Host "Repo:     https://github.com/$Repo"
Write-Host "Releases: https://github.com/$Repo/releases"
Write-Host "Issues:   https://github.com/$Repo/issues"
Write-Host "Apply:    https://openai.com/form/codex-for-oss/"
Write-Host "Draft:    docs/OPENAI_APPLICATION_DRAFT.md"
