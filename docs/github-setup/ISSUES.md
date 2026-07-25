# Issues to create (copy into GitHub if CLI is unavailable)

## Issue 1 — Bug

**Title:** `[Bug] Improve first-run errors when Python or ports are unavailable`

**Body:**

```markdown
## Summary
New users may see unclear failures when Python is missing from PATH or when ports 8753/8740 are busy.

## Expected
Clear, actionable error messages with install/next-step hints.

## Actual
Errors can be opaque depending on how the launcher is started.

## Environment
- OS: Windows (primary)
- Python: 3.12+

## Acceptance criteria
- [ ] Missing Python shows a clear message and download hint
- [ ] Port-in-use message includes the next free port behavior
- [ ] Documented in README troubleshooting
```

## Issue 2 — Feature

**Title:** `[Feature] Add macOS and Linux start scripts`

**Body:**

```markdown
## Problem
Windows has `start.bat` / `start-cost-dashboard.bat`, but macOS/Linux users need shell equivalents.

## Proposed solution
Add:
- `start.sh` (coordinator + portal)
- `start-cost-dashboard.sh` (cost UI only)

Same loopback defaults (`127.0.0.1`).

## Acceptance criteria
- [ ] Scripts are executable and documented in README
- [ ] Behavior matches Windows launchers
```

## Issue 3 — Feature

**Title:** `[Feature] Automated smoke test for coordinator health checks`

**Body:**

```markdown
## Problem
Coordinator start/status/stop is manual; regressions are easy to miss.

## Proposed solution
Add a lightweight script or CI job that:
1. Starts the cost dashboard on a free loopback port
2. Checks HTTP 200 on `/` and (if applicable) portal status
3. Stops cleanly

## Acceptance criteria
- [ ] Can run locally without network
- [ ] Documented under development/testing notes
```
