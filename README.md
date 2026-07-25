# AI Cost History Hub

Local workspace for AI coding-agent **conversation history** and **API cost analytics**.

**Maintainer:** [@zheyan2517](https://github.com/zheyan2517)  
**License:** [MIT](LICENSE)  
**Status:** Active development (`v0.1.0`)

---

## Features

- **One-click local launcher** — start cost analytics and a status portal together
- **Multi-agent cost view** — tokens, spend, models, tools, projects, and sessions (local data)
- **History viewer (desktop)** — browse coding-agent conversation history (optional Tauri build)
- **In-app cost dashboard** — open the local cost UI from the desktop top bar
- **Privacy-first defaults** — services bind to `127.0.0.1` only
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
├── start.bat / start.sh              # Main entry: coordinator + portal
├── start-cost-dashboard.bat / .sh    # Cost dashboard only
├── start-all.bat / start-all.sh      # Same as start
├── config.json                       # Ports and path settings
├── scripts/
│   ├── coordinator.py                # Process manager, health checks, portal
│   └── smoke_test.py                 # Lightweight start → HTTP 200 → stop
├── agent/                            # Cost analytics service (Python)
├── claude/                           # History viewer desktop app (Tauri)
├── docs/
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

---

## Quick start (no Rust required)

Requires **Python 3.12+** on your `PATH`.

**Windows:**

```bat
start.bat
```

**macOS / Linux:**

```bash
chmod +x start.sh start-cost-dashboard.sh start-all.sh
./start.sh
```

This will:

1. Start the cost dashboard on `127.0.0.1:8753` (next free port if busy)
2. Open the portal on `127.0.0.1:8740` (next free port if busy)
3. Bind to loopback only

Cost dashboard only:

```bat
start-cost-dashboard.bat
```

```bash
./start-cost-dashboard.sh
```

Status / stop / smoke test:

```bash
python scripts/coordinator.py status
python scripts/coordinator.py stop
python scripts/coordinator.py smoke
# or: python scripts/smoke_test.py
```

### Session data locations (read-only)

When present, local agent session directories are read, for example:

| Agent | Typical path |
|-------|----------------|
| Claude Code | `~/.claude/projects` |
| Codex CLI | `~/.codex/sessions` |
| Gemini CLI | `~/.gemini/tmp` |
| Pi / Oh My Pi | `~/.pi/agent/sessions`, `~/.omp/agent/sessions` |

---

## Desktop app

Requires **Node.js**, **pnpm**, **Rust (cargo)**, and **Python 3.12+**.

```bat
cd claude
pnpm install
pnpm tauri:dev
```

Use the top-bar **Cost Dashboard** control to open the local cost UI.

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
| [docs/MAINTAINER.md](docs/MAINTAINER.md) | Maintainer notes |

---

## Key modules

| Path | Role |
|------|------|
| `scripts/coordinator.py` | Local process manager and portal |
| `claude/src-tauri/src/commands/cost_dashboard.rs` | Desktop cost-UI process commands |
| `claude/src/services/costDashboard.ts` | Frontend API |
| `claude/src/layouts/Header/Header.tsx` | Top-bar entry |

## Troubleshooting

1. **Python not found**
   - Install **Python 3.12+** from https://www.python.org/downloads/
   - Windows: enable **Add python.exe to PATH**, then open a **new** terminal
   - Verify: `py -3 --version` or `python3 --version`
   - Launchers print the same steps when Python is missing
2. **Port in use (8753 / 8740)**
   - Coordinator auto-selects the next free port in range (see `config.json`)
   - Stop a managed instance: `python scripts/coordinator.py stop`
   - Windows: `netstat -ano | findstr ":8753 :8740"`
   - macOS/Linux: `lsof -iTCP:8753 -sTCP:LISTEN`
3. **`pnpm tauri:dev` fails** — Install [Rust](https://rustup.rs) and WebView2 (usually preinstalled on Windows)
4. **Portal iframe blank** — Open the cost dashboard URL from the sidebar directly
5. **Smoke test** — `python scripts/coordinator.py smoke` (exit 0 = OK)

## Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT © 2026 [zheyan2517](https://github.com/zheyan2517). See [LICENSE](LICENSE).

Third-party components retain their original MIT notices under their own trees where applicable.
