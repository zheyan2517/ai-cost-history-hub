# Homebrew Cask Maintainer Guide

## Architecture

```
GitHub Release (tag push)
    ↓ updater-release.yml
    ├── Build (macOS, Linux, Windows)
    ├── Generate latest.json (auto-updater)
    ├── Update Homebrew Cask in local/homebrew-tap (direct commit via API)
    ├── Verify Cask version + sha256
    └── Publish Release (only after successful Cask sync)
```

### In-app Updater Compatibility

The app has a built-in Tauri auto-updater that checks `latest.json` from GitHub Releases. The Cask includes `auto_updates true` to handle this:

- The in-app "Update" button works regardless of installation method (Homebrew or manual)
- The Tauri updater replaces the `.app` bundle in `/Applications/` directly — no conflicts with Homebrew
- `brew upgrade` skips this app by default (defers to the built-in updater)
- `brew upgrade --greedy` forces Homebrew to check and update the Cask version
- Homebrew's version tracking may become stale after an in-app update (cosmetic only, no functional impact)

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Cask definition | `local/homebrew-tap/Casks/ai-cost-history-hub.rb` | Homebrew install recipe |
| Release workflow | `.github/workflows/updater-release.yml` | Computes SHA256, updates Cask directly, verifies, then publishes |

### Required Secret

`HOMEBREW_TAP_TOKEN` must be configured in the **ai-cost-history-hub** repository settings:

1. Go to GitHub > Settings > Developer settings > Personal access tokens > Fine-grained tokens
2. Create a token with:
   - Repository access: `local/homebrew-tap`
   - Permissions: Contents (Read and write)
3. Add the token as a repository secret named `HOMEBREW_TAP_TOKEN` in `zheyan2517/ai-cost-history-hub`

## Manual Cask Update

If the automated workflow fails, update the Cask manually:

### 1. Download the DMG

```bash
VERSION="1.3.0"
curl -sL "https://github.com/zheyan2517/ai-cost-history-hub/releases/download/v${VERSION}/AI.Cost.History.Hub_${VERSION}_universal.dmg" \
  -o /tmp/history-hub.dmg
```

### 2. Compute SHA256

```bash
shasum -a 256 /tmp/history-hub.dmg
# Output: <sha256>  /tmp/history-hub.dmg
```

### 3. Update the Cask

```bash
git clone https://github.com/local/homebrew-tap.git /tmp/homebrew-tap
cd /tmp/homebrew-tap

# Edit Casks/ai-cost-history-hub.rb
# Update: version "<VERSION>"
# Update: sha256 "<SHA256>"

git add Casks/ai-cost-history-hub.rb
git commit -m "chore: update ai-cost-history-hub to v${VERSION}"
git push
```

### 4. Verify

```bash
brew tap local/tap
brew info --cask ai-cost-history-hub
brew audit --cask ai-cost-history-hub
```

## Verification Commands

```bash
# Check Cask info
brew info --cask ai-cost-history-hub

# Audit Cask (lint check)
brew audit --cask ai-cost-history-hub

# Test install (dry run)
brew install --cask ai-cost-history-hub --dry-run

# Full install
brew install --cask ai-cost-history-hub

# Verify installed app
ls "/Applications/AI Cost History Hub.app"
```

## Troubleshooting

### `HOMEBREW_TAP_TOKEN` not configured

**Symptom**: Release workflow fails at the Homebrew sync step and release remains draft.

**Fix**: Add the `HOMEBREW_TAP_TOKEN` secret (see Required Secret section above).

### SHA256 mismatch after install

**Symptom**: `brew install` fails with checksum error.

**Fix**: Re-download the DMG and recompute the checksum:

```bash
curl -sL "<dmg-url>" -o /tmp/history-hub.dmg
shasum -a 256 /tmp/history-hub.dmg
# Update the Cask with the correct checksum
```

### Cask not found after `brew tap`

**Symptom**: `brew install --cask ai-cost-history-hub` returns "Cask not found".

**Fix**:

```bash
# Force re-tap
brew untap local/tap
brew tap local/tap

# Verify Cask exists
brew info --cask ai-cost-history-hub
```

### Rollback to previous version

```bash
# In the tap repository
git log --oneline Casks/ai-cost-history-hub.rb
git revert <commit-hash>
git push
```

## User Installation

```bash
brew tap local/tap
brew install --cask ai-cost-history-hub
```

Upgrade:

```bash
brew upgrade --cask ai-cost-history-hub
```

Uninstall:

```bash
brew uninstall --cask ai-cost-history-hub
```
