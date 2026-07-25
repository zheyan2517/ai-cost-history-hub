# AI Cost History Hub

Local workspace for AI coding-agent **conversation history** and **API cost analytics**.

**Maintainer:** [@zheyan2517](https://github.com/zheyan2517)  
**License:** [MIT](LICENSE)  
**Status:** Active development (`v0.1.0`)

[Features](#features) · [Quick start](#quick-start-no-rust-required) · [Desktop app](#desktop-app-history-viewer--one-click-cost-dashboard) · [Security](#security) · [Contributing](#contributing)

---

## Features

- **Unified local launcher** — start cost analytics and a small status portal in one step
- **Multi-agent cost view** — tokens, spend, models, tools, projects, and sessions (local data)
- **History viewer desktop app** — browse coding-agent conversation history (optional Tauri build)
- **One-click cost dashboard** from the desktop app top bar (sidecar process)
- **Privacy-first defaults** — services bind to `127.0.0.1` only (not exposed on your LAN)
- **No cloud account required** for the Python dashboard path

### Screenshots

| Cost dashboard | Sessions |
|----------------|----------|
| ![Dashboard overview](agent/screenshots/dashboard-overview.png) | ![Sessions](agent/screenshots/sessions.png) |

| Models | Tools |
|--------|-------|
| ![Model stats](agent/screenshots/model-stats.png) | ![Tool stats](agent/screenshots/tool-stats.png) |

---

## Layout

```
ai-cost-history-hub/
├── start.bat                 # Main entry: coordinator + unified portal
├── start-cost-dashboard.bat  # Cost dashboard only
├── start-all.bat             # Same as start.bat
├── config.json               # Ports and path settings
├── scripts/
│   └── coordinator.py        # Process manager, health checks, portal
├── agent/                    # Cost dashboard (Python)
├── claude/                   # History viewer desktop app (Tauri)
├── docs/                     # Roadmap and maintainer notes
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

---

## Quick start (no Rust required)

Requires **Python 3.12+**.

```bat
start.bat
```

This will:

1. Start the cost dashboard on `127.0.0.1:8753` (next free port if busy)
2. Open the unified portal at `http://127.0.0.1:8740/` (embedded dashboard + status)
3. Bind to loopback only (not exposed on the LAN)

Cost dashboard only:

```bat
start-cost-dashboard.bat
```

Status / stop:

```bat
python scripts\coordinator.py status
python scripts\coordinator.py stop
```

### Session data locations (read-only)

The dashboard reads local agent session directories when present, for example:

| Agent | Typical path |
|-------|----------------|
| Claude Code | `~/.claude/projects` |
| Codex CLI | `~/.codex/sessions` |
| Gemini CLI | `~/.gemini/tmp` |
| Pi / Oh My Pi | `~/.pi/agent/sessions`, `~/.omp/agent/sessions` |

---

## Desktop app (history viewer + one-click cost dashboard)

Requires **Node.js**, **pnpm**, **Rust (cargo)**, and **Python 3.12+**.

```bat
cd claude
pnpm install
pnpm tauri:dev
```

After launch, use the top-bar **wallet / Cost Dashboard** control to:

- Start or reuse the local cost dashboard
- Open `http://127.0.0.1:<port>` in the browser
- Stop the sidecar process when the app exits (if started by the app)

Optional environment variable:

| Variable | Meaning |
|----------|---------|
| `AGENT_COST_DASHBOARD_DIR` | Directory that contains `cost_dashboard.py` |

---

## Security

| Item | Behavior |
|------|----------|
| Listen address | Forced to `127.0.0.1` |
| Data access | Read-only local agent session directories |
| Process lifecycle | Managed by the coordinator and/or desktop app |
| Logs | `.runtime/cost-dashboard.log` or system temp |

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

---

## Project docs

| Doc | Purpose |
|-----|---------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to report bugs and open PRs |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community standards |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Near-term plans |
| [docs/MAINTAINER.md](docs/MAINTAINER.md) | Maintainer responsibilities |

---

## Key integration files

| File | Role |
|------|------|
| `scripts/coordinator.py` | Unified coordination and portal |
| `claude/src-tauri/src/commands/cost_dashboard.rs` | Tauri sidecar commands |
| `claude/src/services/costDashboard.ts` | Frontend API |
| `claude/src/layouts/Header/Header.tsx` | Top-bar entry point |

## Capabilities

| Capability | Component |
|------------|-----------|
| Multi-provider sessions, messages, search | History viewer (`claude/`) |
| Cross-agent cost, model, and tool billing views | Cost dashboard (`agent/`) |

## Troubleshooting

1. **Python not found** — Install Python 3.12+ and add it to `PATH`
2. **Port in use** — Coordinator picks the next free port, or run `coordinator.py stop`
3. **`pnpm tauri:dev` fails** — Install [Rust](https://rustup.rs) and WebView2 (usually preinstalled on Windows)
4. **Portal iframe blank** — Open the cost dashboard URL from the sidebar directly

## Contributing

Issues and PRs are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting.

## License

MIT © 2026 [zheyan2517](https://github.com/zheyan2517). See [LICENSE](LICENSE).

Component trees under `claude/` and `agent/` also include their own `LICENSE` files.
