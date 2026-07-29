# Desktop Viewer Development

The `claude/` directory contains the optional Tauri desktop viewer for
AI Cost History Hub. The repository root [README](../README.md) is the only
user-facing installation guide.

This `v0.2.1` release is source-only. No desktop installer, Homebrew package,
server binary, website, or automatic-download release metadata is published.

## Requirements

- Node.js 20 or newer
- pnpm 10
- Rust 1.77.2 or newer
- Python 3.12 or newer for the local cost dashboard integration

## Development

```bash
pnpm install
pnpm tauri:dev
```

Run the checks used by the root GitHub Actions workflow:

```bash
pnpm lint
pnpm test --run
pnpm build
```

The Rust checks run from `src-tauri`:

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-features
```

The Tauri app can open the Python cost dashboard through the local coordinator.
Keep the coordinator and dashboard on loopback addresses when testing local
session data.

## Versioning

`package.json` is the version source of truth. Sync the Rust and Tauri values
after changing it:

```bash
node scripts/sync-version.cjs
```

The current source version is `0.2.1`.

## Scope

Pre-built desktop distribution and server packaging are intentionally outside
the current release. Do not add download URLs or package-manager commands here
until the corresponding artifacts and release checks exist.
