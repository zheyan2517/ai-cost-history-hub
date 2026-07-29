# AI Cost History Hub

Local-first tools for browsing AI coding-agent history and estimating API
costs from session files already stored on your machine.

**Status:** source-only development release `v0.1.0`
**License:** [MIT](LICENSE)

This repository currently publishes source code only. It does not publish a
website, Homebrew formula, server installer, or pre-built desktop binaries.
Use the source instructions below; the GitHub release is a source checkpoint,
not a binary download page.

## What ships

- Python cost dashboard for Claude Code, Codex CLI, Gemini CLI, Pi, and Oh My Pi
- Local coordinator with loopback-only dashboard and portal services
- CSV and JSON monthly usage exports
- Optional Tauri desktop history viewer built from source
- Synthetic, de-identified parser fixtures and regression tests

The Python dashboard has no third-party runtime dependencies. The desktop
viewer is optional and requires Node.js, pnpm, Rust, and Python.

## Quick start

Requirements: Python 3.12 or newer.

Windows:

```bat
start.bat
```

macOS or Linux:

```bash
chmod +x start.sh start-cost-dashboard.sh
./start.sh
```

The coordinator starts the dashboard on `127.0.0.1:8753` and the portal on
`127.0.0.1:8740`, selecting a nearby free port when necessary.

Useful commands:

```bash
python scripts/coordinator.py status
python scripts/coordinator.py stop
python scripts/coordinator.py smoke
python scripts/clean_install_test.py
```

The clean-install command copies the source to a temporary directory and
checks compilation, tests, loopback guards, exports, and the HTTP smoke path.

## Session directories

Default locations are read-only:

| Agent | Typical location |
| --- | --- |
| Claude Code | `~/.claude/projects` |
| Codex CLI | `~/.codex/sessions` |
| Gemini CLI | `~/.gemini/tmp` |
| Pi | `~/.pi/agent/sessions` |
| Oh My Pi | `~/.omp/agent/sessions` |

Add multiple directories with repeated CLI options or `config.json`:

```bash
python agent/cost_dashboard.py --pi-dir /path/to/pi-a --pi-dir /path/to/pi-b
```

Export one month without starting a server:

```bash
python agent/cost_dashboard.py --export-monthly 2026-07 --format csv
python agent/cost_dashboard.py --export-monthly 2026-07 --format json
```

Unknown models are reported as `unknown` pricing rather than silently treated
as free. Estimated values are marked separately from costs reported by an
agent.

## Desktop viewer from source

```bash
cd claude
pnpm install
pnpm tauri:dev
```

Run the frontend checks from the same directory:

```bash
pnpm lint
pnpm test --run
pnpm build
```

## Privacy and security

- Session directories are read locally and are not uploaded by this project.
- Dashboard and portal services accept loopback addresses only.
- Test fixtures contain synthetic paths and content, not user transcripts.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and
[CONTRIBUTING.md](CONTRIBUTING.md) for development conventions.

## Project layout

```text
agent/       Python dashboard, parsers, exporters, and synthetic fixtures
scripts/     Coordinator, smoke checks, and clean-install verification
claude/      Optional Tauri desktop viewer
tests/       Python parser, pricing, export, and privacy regression tests
docs/        Roadmap and maintainer notes
```

## License

MIT. See [LICENSE](LICENSE). Components under `agent/` and `claude/` retain
their respective license files.
