#!/usr/bin/env python3
"""Regression test: dashboards and the portal must refuse non-loopback binds.

Run from the repo root:

    python scripts/loopback_guard_test.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

import coordinator  # noqa: E402
import cost_dashboard  # noqa: E402

LOOPBACK_CASES = ["127.0.0.1", "::1", "localhost", "LOCALHOST", "localhost."]
NON_LOOPBACK_CASES = ["0.0.0.1", "::", "192.168.1.10", "10.0.0.5", "example.com"]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_dashboard_validator() -> None:
    for host in LOOPBACK_CASES:
        try:
            cost_dashboard.require_loopback_host(host)
        except argparse.ArgumentTypeError as e:
            fail(f"cost_dashboard rejected loopback host {host!r}: {e}")
    for host in NON_LOOPBACK_CASES:
        try:
            cost_dashboard.require_loopback_host(host)
        except argparse.ArgumentTypeError:
            continue
        fail(f"cost_dashboard accepted non-loopback host {host!r}")


def check_dashboard_cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=cost_dashboard.require_loopback_host)
    for host in NON_LOOPBACK_CASES:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            try:
                parser.parse_args(["--host", host])
            except SystemExit as exit_exc:
                if exit_exc.code != 2:
                    fail(
                        f"dashboard CLI exit for {host!r} was {exit_exc.code}, expected 2"
                    )
                continue
        fail(f"dashboard CLI accepted --host {host!r}")


def check_coordinator_guard() -> None:
    for host in LOOPBACK_CASES:
        try:
            coordinator.require_loopback_host(host, label="service")
        except RuntimeError as e:
            fail(f"coordinator rejected loopback host {host!r}: {e}")
    for host in NON_LOOPBACK_CASES:
        try:
            coordinator.require_loopback_host(host, label="service")
        except RuntimeError:
            continue
        fail(f"coordinator accepted non-loopback host {host!r}")


def check_coordinator_config_path() -> None:
    cfg = coordinator.load_config()
    cfg["costDashboard"]["host"] = "0.0.0.1"
    stderr = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
        try:
            coordinator.ensure_cost_dashboard(cfg)
        except RuntimeError as e:
            if "Refusing to start" not in str(e):
                fail(f"coordinator error message missing refusal: {e}")
            return
    fail("coordinator started cost dashboard with a non-loopback host from config")


def main() -> int:
    check_dashboard_validator()
    check_dashboard_cli()
    check_coordinator_guard()
    check_coordinator_config_path()
    print("OK: non-loopback bind hosts are rejected everywhere")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
