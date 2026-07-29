#!/usr/bin/env python3
"""Verify the source-only Python install from an isolated temporary copy."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def copy_source_tree(destination: Path) -> None:
    """Copy the repository without local build state or installed dependencies."""

    ignored_names = {
        ".git",
        ".runtime",
        "node_modules",
        "target",
        "__pycache__",
        "dist",
    }

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in ignored_names
            or name.endswith((".pyc", ".pyo", ".log"))
        }

    shutil.copytree(ROOT, destination, ignore=ignore)


def run_step(label: str, command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(f"[clean-install] {label}")
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(
            f"{label} failed with exit code {result.returncode}: {' '.join(command)}"
        )
    print(f"[clean-install] PASS: {label}")


def main() -> int:
    env = os.environ.copy()
    # Prevent local checkout paths or user-installed Python packages from
    # making this verification pass for the wrong source tree.
    env.pop("AGENT_COST_DASHBOARD_DIR", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"

    with tempfile.TemporaryDirectory(prefix="ai-cost-history-hub-clean-") as temp_dir:
        clean_root = Path(temp_dir) / "repo"
        copy_source_tree(clean_root)
        export_path = Path(temp_dir) / "monthly.json"

        run_step(
            "compile Python sources",
            [sys.executable, "-m", "compileall", "-q", "agent", "scripts", "tests"],
            clean_root,
            env,
        )
        run_step(
            "run parser, pricing, export, and privacy tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            clean_root,
            env,
        )
        run_step(
            "run loopback guard",
            [sys.executable, "scripts/loopback_guard_test.py"],
            clean_root,
            env,
        )
        run_step(
            "run coordinator HTTP smoke test",
            [sys.executable, "scripts/coordinator.py", "smoke"],
            clean_root,
            env,
        )
        run_step(
            "run monthly export from a clean source tree",
            [
                sys.executable,
                "agent/cost_dashboard.py",
                "--no-default-session-dirs",
                "--pi-dir",
                "tests/fixtures/pi",
                "--export-monthly",
                "2026-07",
                "--format",
                "json",
                "--output",
                str(export_path),
            ],
            clean_root,
            env,
        )
        if not export_path.is_file() or '"event_count"' not in export_path.read_text(
            encoding="utf-8"
        ):
            raise RuntimeError("clean source export did not produce a valid JSON file")

    print("[clean-install] PASS: source-only install verification")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"[clean-install] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
