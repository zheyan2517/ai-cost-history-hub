# Contributing

Thanks for your interest in **AI Cost History Hub**.

## Ways to help

- Report bugs and installation issues
- Suggest features that improve local agent cost tracking or history browsing
- Improve docs, screenshots, and platform setup notes (Windows / macOS / Linux)
- Submit focused pull requests (one concern per PR when possible)

## Development setup

### Cost dashboard + portal (Python)

Requirements: **Python 3.12+**

```bat
# Windows
start.bat
```

```bash
# macOS / Linux
chmod +x start.sh start-cost-dashboard.sh
./start.sh
```

Useful commands:

```bash
python scripts/coordinator.py status
python scripts/coordinator.py stop
python scripts/coordinator.py open-cost
python scripts/coordinator.py smoke
```

### Desktop history viewer (optional)

Requirements: **Node.js**, **pnpm**, **Rust (cargo)**, **Python 3.12+**

```bash
cd claude
pnpm install
pnpm tauri:dev
```

## Pull request checklist

1. Fork the repository and create a branch from `main`
2. Keep changes focused and easy to review
3. Test the path you changed (`start.bat` / coordinator and/or `pnpm tauri:dev`)
4. Update README or docs if behavior changes
5. Open a PR with:
   - What changed
   - Why it is needed
   - How you tested it

## Code style

- Prefer clear names and small modules over clever one-liners
- Do not commit secrets, API keys, local session dumps, or `.runtime/` logs
- Keep the cost dashboard bound to `127.0.0.1` by default (loopback only)

## Reporting security issues

Please do **not** open a public issue for security vulnerabilities.  
See [SECURITY.md](SECURITY.md).

## Maintainer

- Primary maintainer: [@zheyan2517](https://github.com/zheyan2517)
- Repository: https://github.com/zheyan2517/ai-cost-history-hub
