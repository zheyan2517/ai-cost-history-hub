# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-29

### Fixed

- Fixed Windows launchers failing on valid Python installations because of
  stale batch error-level expansion
- Fixed Unix launchers reporting the inverted exit status after a failed
  coordinator start
- Made launcher failures return directly instead of waiting for interactive
  input

## [0.2.0] - 2026-07-29

### Added

- Cross-platform clean-install verification and stable synthetic fixtures for
  supported providers
- Smoke-test workflow for the local coordinator and cost dashboard
- Windows path handling and isolated test-home support for Rust tests

### Changed

- Unified the repository and desktop viewer on source-only version `0.2.0`
- Consolidated the public release documentation around the source distribution
- Disabled updater metadata and artifact generation until signed release
  assets are published

### Fixed

- Corrected Windows path parsing for Claude project history
- Removed Unix-only assumptions from cross-platform tests

### Security

- Kept dashboard and portal services loopback-only by default

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
