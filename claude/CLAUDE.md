# Desktop Viewer Development Notes

The repository root `README.md` is the canonical user-facing guide. This file
contains only development conventions for the optional Tauri application.

## Scope

The desktop viewer is source-only in `v0.1.0`. Do not add public installer,
Homebrew, server-binary, website, or auto-download instructions until the
corresponding artifacts and release checks exist.

## Requirements

- Node.js 20 or newer
- pnpm 10
- Rust 1.77.2 or newer
- Python 3.12 or newer for the local dashboard integration

## Commands

Run from `claude/`:

```bash
pnpm install
pnpm tauri:dev
pnpm lint
pnpm test --run
pnpm build
node scripts/sync-version.cjs
```

Run from `claude/src-tauri/`:

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-features
```

The root CI also runs the Python clean-install check and coordinator smoke
test. Use `python scripts/clean_install_test.py` from the repository root
before opening a pull request that changes the local dashboard integration.

## Versioning

`claude/package.json` is the single source of truth. `node scripts/sync-version.cjs`
updates `src-tauri/Cargo.toml` and `src-tauri/tauri.conf.json`.

## Security

The desktop app starts the local cost dashboard through the root coordinator.
Keep dashboard and portal services on loopback addresses. Session files can
contain prompts, paths, tool arguments, and other private data.

The Rust `webui-server` feature is development code and is not a published
server distribution channel in the current release.
