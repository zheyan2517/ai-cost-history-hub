# Maintainer notes

Primary maintainer: **@zheyan2517**  
Repository: https://github.com/zheyan2517/ai-cost-history-hub

## Responsibilities

- Keep `main` installable via documented quick start
- Review issues and pull requests
- Cut tagged releases with changelog entries
- Protect loopback-only defaults and avoid shipping secrets

## Release checklist

1. Update `CHANGELOG.md`
2. Ensure README quick start still works on a clean machine path
3. Commit on `main`
4. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
5. Push: `git push origin main --tags`
6. Create a GitHub Release from the tag

## How AI coding tools are used in maintenance

This project is maintained with assistance from coding agents (including Codex-class tools) for:

- Pull request review and suggested fixes
- Issue triage summaries and reproduction notes
- Documentation edits and release notes
- Refactors that preserve local-only security defaults

Human maintainer remains responsible for merges, security judgments, and releases.
