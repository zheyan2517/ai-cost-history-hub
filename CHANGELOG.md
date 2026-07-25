# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-25

### Added

- Unified local launcher (`start.bat`) and Python coordinator (`scripts/coordinator.py`)
- Cost dashboard sidecar with loopback-only binding (`127.0.0.1`)
- Unified portal UI with light theme and background image
- Desktop history viewer integration entry (Cost Dashboard control)
- Project documentation: README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT
- GitHub issue and pull request templates

### Changed

- Product UI and public docs set to English-only
- Root project branding: **AI Cost History Hub**

### Security

- Default host for cost dashboard forced to loopback
- Security policy published in `SECURITY.md`

## [Unreleased]

### Planned

- Cross-platform launcher scripts for macOS / Linux
- Packaging notes for desktop builds
- Automated smoke tests for coordinator health checks
