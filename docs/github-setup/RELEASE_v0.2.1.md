## AI Cost History Hub v0.2.1

Patch release for reliable cross-platform launchers.

### Fixed

- Windows BAT launchers now handle Python detection and exit codes without
  stale variable expansion
- Unix launchers now preserve coordinator failure status
- Launcher failures return directly so automated checks do not hang on `pause`

### Verification

- Windows `start-cost-dashboard.bat` launch verified
- Windows `start.bat` background launch verified
- Dashboard tests: 10 passed
- Coordinator smoke test passed
- Loopback guard test passed
