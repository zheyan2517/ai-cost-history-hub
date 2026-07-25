# Security Policy

## Supported versions

Security fixes are applied on the latest `main` branch and tagged releases when practical.

| Version | Supported |
|---------|-----------|
| `main`  | Yes |
| Latest tagged release (e.g. `v0.x`) | Yes |
| Older tags | Best effort |

## Product security defaults

AI Cost History Hub is designed for **local, private use**:

- Cost dashboard and portal bind to **`127.0.0.1` only** by default
- Session data is read from local agent directories (read-only usage patterns)
- Do not expose the dashboard to `0.0.0.0` / LAN without your own authentication

## Reporting a vulnerability

Please report security issues privately:

1. Email: **zheyan2517@outlook.com**
2. Or use GitHub **Security Advisories** for this repository (if enabled):  
   https://github.com/zheyan2517/ai-cost-history-hub/security/advisories/new

Include:

- Description of the issue
- Steps to reproduce
- Affected OS / Python / Node versions
- Impact assessment (if known)

We aim to acknowledge reports within **7 days**.

## Please avoid

- Public GitHub issues for unfixed vulnerabilities
- Testing against systems you do not own
- Publishing exploit details before a fix is available
