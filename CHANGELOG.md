# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-25

### Added

- Local cost analytics service and unified portal launcher
- Loopback-only binding (`127.0.0.1`) by default
- Light theme and background for the cost UI
- Desktop history viewer entry for the local cost UI
- Project docs: README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- GitHub issue and pull request templates

### Changed

- Product UI and public docs set to English-only
- Project branding: **AI Cost History Hub**
- Documentation framed as product secondary development / refactor work

### Security

- Default host for the cost service forced to loopback
- Security policy published in `SECURITY.md`

## [Unreleased]

### Added

- Clear first-run errors when Python is missing or ports are exhausted
- `start.sh`, `start-cost-dashboard.sh`, `start-all.sh` for macOS / Linux
- `python scripts/coordinator.py smoke` and `scripts/smoke_test.py`
- Isolated clean-install verification and stable synthetic fixtures for all
  supported providers
- GitHub Actions workflow `.github/workflows/smoke.yml`

### Changed

- Unified the repository and desktop viewer on source-only version `0.1.0`
- Disabled updater metadata and artifact generation until signed release
  assets are published

### Planned

- Packaging notes for desktop builds
