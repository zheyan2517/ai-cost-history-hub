# Python Cost Dashboard

This directory contains the dependency-free Python dashboard used by
AI Cost History Hub. It reads local coding-agent session files and presents
token, model, tool, project, session, and estimated-cost summaries.

The root [README](../README.md) is the canonical installation guide.

## Supported sources

- Claude Code JSONL sessions
- Codex CLI JSONL rollouts
- Gemini CLI JSONL sessions
- Pi and Oh My Pi JSONL sessions

Session paths are read-only. The dashboard accepts multiple roots for each
source and can load them from `config.json` or repeated CLI options.

## Run locally

From the repository root:

```bash
python agent/cost_dashboard.py
```

Use a specific port or source directory:

```bash
python agent/cost_dashboard.py --port 3000 --pi-dir /path/to/pi/sessions
```

The server binds to `127.0.0.1` only. Non-loopback hosts are rejected because
session records can contain prompts, file paths, and tool input.

## Export monthly usage

```bash
python agent/cost_dashboard.py --export-monthly 2026-07 --format csv
python agent/cost_dashboard.py --export-monthly 2026-07 --format json
```

The export includes one row per parsed LLM usage event. Costs reported by a
source are labeled `reported`; fallback table values are labeled `estimated`;
models without a known price are labeled `unknown` and do not receive a fake
zero-dollar estimate.

## Tests

The synthetic fixtures under `../tests/fixtures` contain no real transcripts.
Run the parser and pricing tests from the repository root:

```bash
python -m unittest discover -s tests -v
python scripts/clean_install_test.py
```
