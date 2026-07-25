# Maintainer notes

Primary maintainer: **@zheyan2517**  
Repository: https://github.com/zheyan2517/ai-cost-history-hub

## Responsibilities

- Keep `main` installable via the documented quick start
- Review issues and pull requests
- Cut tagged releases with changelog entries
- Protect loopback-only defaults and avoid shipping secrets

## Release checklist

1. Update `CHANGELOG.md`
2. Ensure README quick start still works
3. Commit on `main`
4. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
5. Push: `git push origin main --tags`
6. Create a GitHub Release from the tag

## Tooling used for maintenance

Coding agents (including Codex-class tools) may assist with:

- Pull request review and suggested fixes
- Issue triage summaries
- Documentation and release notes
- Refactors that preserve local-only security defaults

The human maintainer remains responsible for merges, security judgments, and releases.
