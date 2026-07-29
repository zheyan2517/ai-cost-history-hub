#!/usr/bin/env python3
"""Serve a dynamic HTML dashboard with cost statistics for all pi-agent sessions."""

import json
import re
import subprocess
import tempfile
import urllib.parse
import uuid
import csv
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import html
import http.server
import ipaddress
import socketserver
import argparse
import shlex
import shutil
import sys
from typing import TypedDict, DefaultDict, Sequence


LOOPBACK_HOSTNAMES = {"localhost"}


def is_loopback_host(host: str) -> bool:
    """Return True when *host* can only be reached from this machine."""
    normalized = host.strip().lower().rstrip(".")
    if normalized in LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def require_loopback_host(host: str) -> str:
    """Validate that *host* is loopback-only, rejecting external exposure."""
    if not is_loopback_host(host):
        raise argparse.ArgumentTypeError(
            f"Refusing to bind dashboard to '{host}'. "
            "This dashboard serves local session data without authentication; "
            "use 127.0.0.1, ::1, or localhost."
        )
    return host


# Type definitions
class ModelStats(TypedDict):
    messages: int
    tokens: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    cost: float
    llm_time: float
    known_pricing_events: int
    unknown_pricing_events: int
    pricing_status: str


class ToolStats(TypedDict):
    calls: int
    time: float
    errors: int


class DailyStats(TypedDict):
    messages: int
    cost: float
    # Per-model cost breakdown for stacked bar chart.
    # Keys are model names, values are accumulated costs.
    models: dict[str, float]


class SessionStats(TypedDict):
    messages: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    total_tokens: int
    cost_total: float
    models: DefaultDict[str, ModelStats]
    timestamps: list[datetime]
    start: datetime | None
    end: datetime | None
    llm_time: float
    tool_time: float
    tools: DefaultDict[str, ToolStats]
    tps_samples: list[tuple[int, float, str]]
    cost_events: list[tuple[datetime, str, float]]
    llm_events: list[dict]
    cwd: str


class ProjectStats(TypedDict):
    name: str
    agent_cmd: str
    sessions: list["Session"]
    total_messages: int
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    total_reasoning_tokens: int
    total_cost: float
    total_llm_time: float
    total_tool_time: float
    models: DefaultDict[str, ModelStats]
    tools: DefaultDict[str, ToolStats]
    daily_stats: DefaultDict[str, DailyStats]
    first_activity: datetime | None
    last_activity: datetime | None
    tps_samples: list[tuple[int, float, str]]
    usage_events: list[dict]


class GlobalStats(TypedDict):
    total_cost: float
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    total_reasoning_tokens: int
    total_messages: int
    total_sessions: int
    total_projects: int
    total_llm_time: float
    total_tool_time: float
    models: DefaultDict[str, ModelStats]
    tools: DefaultDict[str, ToolStats]
    daily_stats: DefaultDict[str, DailyStats]
    tps_samples: list[tuple[int, float, str]]
    usage_events: list[dict]


class Session(TypedDict):
    """Session data for a single agent session."""

    file: str
    path: str
    uid: str
    relative_path: str
    cwd: str
    agent_cmd: str
    messages: int
    tokens: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    cost: float
    start: datetime | None
    end: datetime | None
    duration: float
    llm_time: float
    tool_time: float
    tools: dict[str, ToolStats]
    avg_tps: float
    subagent_sessions: list["Session"]
    pricing_status: str


class PricingResult(TypedDict):
    cost: float
    status: str


# Helper functions to create properly-typed defaultdicts
def create_model_stats() -> ModelStats:
    return {
        "messages": 0,
        "tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "cost": 0.0,
        "llm_time": 0.0,
        "known_pricing_events": 0,
        "unknown_pricing_events": 0,
        "pricing_status": "",
    }


def create_tool_stats() -> ToolStats:
    return {"calls": 0, "time": 0.0, "errors": 0}


def create_daily_stats() -> DailyStats:
    return {"messages": 0, "cost": 0.0, "models": {}}


# Session directories for different agents: (path, agent_command, source_type)
# source_type: "standard" (pi/omp), "claude" (~/.claude/projects),
# "codex" (~/.codex/sessions), "gemini" (~/.gemini/tmp).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_SESSIONS_DIRS = [
    (Path.home() / ".pi" / "agent" / "sessions", "pi", "standard"),
    (Path.home() / "agentbox" / "config" / ".pi" / "agent" / "sessions", "pi", "standard"),
    (Path.home() / ".omp" / "agent" / "sessions", "omp", "standard"),
    (Path.home() / ".claude" / "projects", "claude", "claude"),
    (Path.home() / ".codex" / "sessions", "codex", "codex"),
    (Path.home() / ".gemini" / "tmp", "gemini-cli", "gemini"),
]
# Kept as a public mutable list for existing integrations and tests.
SESSIONS_DIRS = list(DEFAULT_SESSIONS_DIRS)

SESSION_DIR_SPECS = {
    "session-dir": ("pi", "standard"),
    "pi-dir": ("pi", "standard"),
    "omp-dir": ("omp", "standard"),
    "claude-dir": ("claude", "claude"),
    "codex-dir": ("codex", "codex"),
    "gemini-dir": ("gemini-cli", "gemini"),
}
TEMP_DIR = Path(tempfile.gettempdir()) / "pi-dashboard"
ASSETS_DIR = Path(__file__).parent / "assets"

# Registry mapping session UUIDs to session data
# This keeps sensitive path/command info server-side only
SESSION_REGISTRY: dict[str, Session] = {}


def clear_session_registry() -> None:
    """Clear all sessions from the registry."""
    SESSION_REGISTRY.clear()


def get_session_id_from_file(
    filepath: str, source_type: str = "standard"
) -> str | None:
    """Extract session ID from a JSONL file.

    For standard (pi/omp): first line {"type":"session","id":"..."}
    For claude: use the filename stem (UUID)
    For codex: read session_meta.payload.id
    """
    if source_type == "claude":
        return Path(filepath).stem

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            if first_line:
                data = json.loads(first_line)
                if source_type == "codex":
                    if data.get("type") == "session_meta":
                        return data.get("payload", {}).get("id")
                else:
                    if data.get("type") == "session" and "id" in data:
                        return data["id"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


# Fallback pricing used when a session does not report a billed cost
# (price per million tokens). The dashboard labels these values as estimated.
#
# Format: model_pattern -> {"input": price_per_M, "output": price_per_M,
# "cache_read": price_per_M, "cache_write": price_per_M}
#
# Rules:
#  - Only add entries for specific known model versions. No broad family prefixes
#    (e.g. "gpt-5", "gpt-4") — a generic pattern can silently misprice a totally
#    different model in the same family at a wildly wrong rate.
#  - More specific patterns must appear before less specific ones (dict is ordered).
#  - Cache pricing is included where available; 0.0 where unknown.
MANUAL_PRICING = {
    # ── Gemini ───────────────────────────────────────────────────────────────
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 10.00,
        "cache_read": 0.125,
        "cache_write": 0.375,
    },
    "gemini-2.5-flash-lite": {
        "input": 0.10,
        "output": 0.40,
        "cache_read": 0.025,
        "cache_write": 0.083,
    },
    "gemini-2.5-flash": {
        "input": 0.30,
        "output": 2.50,
        "cache_read": 0.03,
        "cache_write": 0.083,
    },
    "gemini-2.0-flash": {
        "input": 0.10,
        "output": 0.40,
        "cache_read": 0.025,
        "cache_write": 0.083,
    },
    "gemini-1.5-pro": {
        "input": 1.25,
        "output": 5.00,
        "cache_read": 0.31,
        "cache_write": 1.25,
    },
    "gemini-1.5-flash": {
        "input": 0.075,
        "output": 0.30,
        "cache_read": 0.01875,
        "cache_write": 0.075,
    },
    "gemini-3-flash-preview": {
        "input": 0.50,
        "output": 3.00,
        "cache_read": 0.05,
        "cache_write": 0.083,
    },
    "gemini-3-pro-preview": {
        "input": 2.00,
        "output": 12.00,
        "cache_read": 0.20,
        "cache_write": 0.375,
    },
    "gemini-3.1-pro-preview": {
        "input": 2.00,
        "output": 12.00,
        "cache_read": 0.20,
        "cache_write": 0.375,
    },
    # ── Claude (Anthropic API pricing per 1M tokens) ──────────────────────────
    # Specific version strings avoid mislabelling different-priced variants.
    # pi sessions use hyphens (claude-opus-4-5); direct API / OR use dots (4.5).
    # claude-opus-4.5 / 4.6 — $5/$25
    "claude-opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-5": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4.6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    # claude-opus-4.7 / 4.8 — same $5/$25 tier as 4.5/4.6
    "claude-opus-4.7": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-7": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4.8": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-8": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    # claude-opus-4.0 / 4.1 — $15/$75 (different, more expensive model)
    "claude-opus-4.1": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-opus-4-1": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-opus-4.0": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-opus-4-0": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-sonnet-4": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-haiku-4": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.1,
        "cache_write": 1.25,
    },
    # ── GLM (Z-AI / ZhipuAI) ─────────────────────────────────────────────────
    "glm-4.7": {
        "input": 0.38,
        "output": 1.74,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
    "glm-4.5-air": {
        "input": 0.13,
        "output": 0.85,
        "cache_read": 0.025,
        "cache_write": 0.0,
    },
    # ── Grok (xAI) ───────────────────────────────────────────────────────────
    "grok-code-fast-1": {
        "input": 0.20,
        "output": 1.50,
        "cache_read": 0.02,
    },
    # ── OpenAI / Codex ────────────────────────────────────────────────────────
    # More specific patterns before less specific ones.
    # Cache pricing ~10% of input (Codex CLI product rate).
    "gpt-5.3-codex": {
        "input": 1.75,
        "output": 14.0,
        "cache_read": 0.175,
    },
    "gpt-5.2-codex": {
        "input": 1.75,
        "output": 14.0,
        "cache_read": 0.175,
    },
    "gpt-5.1-codex": {
        "input": 1.25,
        "output": 10.0,
        "cache_read": 0.125,
    },
    "gpt-5-codex": {
        "input": 1.25,
        "output": 10.0,
        "cache_read": 0.125,
    },
    "gpt-5.4": {
        "input": 2.50,
        "output": 15.0,
        "cache_read": 0.25,
    },
    "o3": {
        "input": 2.0,
        "output": 8.0,
        "cache_read": 0.5,
    },
    "o4-mini": {
        "input": 1.1,
        "output": 4.4,
        "cache_read": 0.275,
    },
}


def _unknown_pricing() -> PricingResult:
    return {"cost": 0.0, "status": "unknown"}


def _reported_pricing(cost: float) -> PricingResult:
    return {"cost": max(0.0, float(cost)), "status": "reported"}


def find_pricing_record(model: str) -> tuple[str, dict[str, float | str]] | None:
    """Return the most specific fallback record matching *model*.

    Matching is against normalized ids so vendor prefixes and dated model
    ids work consistently, while the longest pattern prevents a generic model
    from winning over a more specific variant.
    """
    normalized_model = _normalize_model_name(model)
    best_pattern: str | None = None
    for pattern in MANUAL_PRICING:
        normalized_pattern = _normalize_model_name(pattern)
        if normalized_pattern in normalized_model and (
            best_pattern is None or len(normalized_pattern) > len(_normalize_model_name(best_pattern))
        ):
            best_pattern = pattern
    if best_pattern is None:
        return None
    return best_pattern, MANUAL_PRICING[best_pattern]


def price_model(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
) -> PricingResult:
    """Estimate a model's cost from the local fallback pricing table."""
    match = find_pricing_record(model)
    if match is None:
        return _unknown_pricing()

    _, pricing = match
    cost = (
        (input_tokens / 1_000_000) * float(pricing.get("input", 0))
        + (output_tokens / 1_000_000) * float(pricing.get("output", 0))
        + (cache_read_tokens / 1_000_000) * float(pricing.get("cache_read", 0))
        + (cache_write_tokens / 1_000_000) * float(pricing.get("cache_write", 0))
    )
    return {"cost": cost, "status": "estimated"}


def resolve_usage_pricing(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
    reported_cost: float = 0.0,
) -> PricingResult:
    """Prefer a cost explicitly reported by the agent, then estimate it."""
    if reported_cost > 0:
        return _reported_pricing(reported_cost)
    return price_model(
        model,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
    )


def _normalize_model_name(name: str) -> str:
    """Collapse a model id to a vendor-/format-agnostic key for matching.

    Drops any 'vendor/' prefix, lowercases, strips a trailing YYYYMMDD date
    stamp, and unifies '.'/'-' version separators so 'claude-opus-4-8',
    'anthropic/claude-opus-4.8' and 'claude-opus-4-8-20260528' all collapse to
    the same key.
    """
    name = name.split("/")[-1].lower()
    name = re.sub(r"-20\d{6}$", "", name)
    return name.replace(".", "-")


def get_manual_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
) -> float:
    """Return the fallback-table estimate, or zero when pricing is unknown.

    New code should use :func:`price_model` so it can preserve the status and
    distinguish an unknown model from a zero-cost model.
    """
    return price_model(
        model,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
    )["cost"]


def parse_timestamp(ts):
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def to_nonnegative_int(value) -> int:
    """Normalize optional token fields without aborting a whole session."""
    try:
        if value is None:
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            return 0


def format_duration(seconds):
    """Format seconds into human-readable duration like 1h23m45s."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m{secs:02d}s" if secs else f"{mins}m"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h{mins:02d}m" if mins else f"{hours}h"


def load_asset(name: str) -> str:
    """Read a dashboard asset bundled with the script."""
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def format_full_number(value: int | float) -> str:
    """Render a count without locale-dependent grouping."""
    return str(int(round(value)))


def trim_one_decimal(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def format_tokens(value: int | float) -> str:
    """Compact count for high-level cards and summary columns."""
    n = float(value or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for size, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "k"),
    ):
        if n >= size:
            return f"{sign}{trim_one_decimal(n / size)}{suffix}"
    return f"{sign}{format_full_number(n)}"


def json_for_script(data) -> str:
    """Serialize JSON safely for embedding in a script tag."""
    return json.dumps(data).replace("</", "<\\/")


def display_project_name(path: str) -> str:
    """Return a non-sensitive project label for browser/export payloads."""
    text = str(path or "").rstrip("/\\")
    if not text:
        return "unknown"
    return re.split(r"[\\/]", text)[-1] or "unknown"


def cost_display(cost: float, pricing_status: str = "") -> str:
    if pricing_status == "unknown":
        return "unknown"
    prefix = "~" if pricing_status == "estimated" else ""
    return f"{prefix}${cost:.2f}"


def render_token_summary_card(global_stats: GlobalStats) -> str:
    """Render the global token card with separated cache read/write counts."""
    items = [
        ("Input", global_stats["total_input_tokens"]),
        ("Output", global_stats["total_output_tokens"]),
        ("Cache read", global_stats["total_cache_read_tokens"]),
        ("Cache write", global_stats["total_cache_write_tokens"]),
        ("Reasoning", global_stats["total_reasoning_tokens"]),
    ]
    rows = "".join(
        f'<div><span>{label}</span><strong title="{format_full_number(count)}">{format_tokens(count)}</strong></div>'
        for label, count in items
    )
    return f"""
            <div class="stat-card token-card">
                <div class="label">Total Tokens</div>
                <div class="value">{format_tokens(global_stats["total_tokens"])}</div>
                <div class="token-breakdown">{rows}</div>
            </div>"""


def calc_avg_tokens_per_sec(tps_samples):
    """Calculate average tokens/second from samples.

    Each sample is (output_tokens, llm_seconds, model).
    Returns a token-time-weighted average (sum tokens / sum seconds), or 0 if
    no valid samples — averaging per-call ratios directly would let a small,
    fast call skew the result as much as a large, slow one.
    """
    if not tps_samples:
        return 0.0

    total_tokens = sum(tokens for tokens, secs, _ in tps_samples if secs > 0)
    total_secs = sum(secs for _, secs, _ in tps_samples if secs > 0)
    if total_secs <= 0:
        return 0.0

    return total_tokens / total_secs


TOKEN_DETAIL_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)
MODEL_STAT_FIELDS = (
    "messages",
    "tokens",
    *TOKEN_DETAIL_FIELDS,
    "cost",
    "llm_time",
)

MODEL_PRICING_FIELDS = (
    "known_pricing_events",
    "unknown_pricing_events",
)


def create_session_stats() -> SessionStats:
    """Create a zeroed stats record for one session file."""
    return {
        "messages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "cost_total": 0.0,
        "models": defaultdict(create_model_stats),
        "timestamps": [],
        "start": None,
        "end": None,
        "llm_time": 0.0,
        "tool_time": 0.0,
        "tools": defaultdict(create_tool_stats),
        "tps_samples": [],
        "cost_events": [],
        "llm_events": [],
        "cwd": "",
    }


def _record_timestamp(stats: SessionStats, ts: datetime | None) -> None:
    if not ts:
        return
    stats["timestamps"].append(ts)
    if stats["start"] is None or ts < stats["start"]:
        stats["start"] = ts
    if stats["end"] is None or ts > stats["end"]:
        stats["end"] = ts


def _merge_pricing_status(current: str, new: str) -> str:
    """Collapse event statuses for a model/session summary."""
    if new == "unknown" or current == "unknown":
        return "unknown"
    if new == "estimated" or current == "estimated":
        return "estimated"
    if new == "reported" or current == "reported":
        return "reported"
    return new or current or "unknown"


def _record_model_pricing(mstats: ModelStats, pricing: PricingResult) -> None:
    status = pricing["status"]
    if status == "unknown":
        mstats["unknown_pricing_events"] += 1
    else:
        mstats["known_pricing_events"] += 1
    mstats["pricing_status"] = _merge_pricing_status(
        mstats["pricing_status"], status
    )


def record_llm_usage(
    stats: SessionStats,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    total_tokens: int | None = None,
    cost: float = 0.0,
    ts: datetime | None = None,
    llm_delta: float = 0.0,
    pricing: PricingResult | None = None,
) -> None:
    """Record one LLM usage event into session and per-model stats."""
    total = (
        total_tokens
        if total_tokens is not None
        else input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
    )
    model_name = model or "unknown"
    if pricing is None:
        pricing = _reported_pricing(cost) if cost > 0 else _unknown_pricing()
    else:
        cost = pricing["cost"]

    stats["messages"] += 1
    stats["input_tokens"] += input_tokens
    stats["output_tokens"] += output_tokens
    stats["cache_read_tokens"] += cache_read_tokens
    stats["cache_write_tokens"] += cache_write_tokens
    stats["reasoning_tokens"] += reasoning_tokens
    stats["total_tokens"] += total
    stats["cost_total"] += cost

    mstats = stats["models"][model_name]
    mstats["messages"] += 1
    mstats["tokens"] += total
    mstats["input_tokens"] += input_tokens
    mstats["output_tokens"] += output_tokens
    mstats["cache_read_tokens"] += cache_read_tokens
    mstats["cache_write_tokens"] += cache_write_tokens
    mstats["reasoning_tokens"] += reasoning_tokens
    mstats["cost"] += cost
    _record_model_pricing(mstats, pricing)

    if llm_delta > 0 and output_tokens > 0:
        stats["tps_samples"].append((output_tokens, llm_delta, model_name))
        mstats["llm_time"] += llm_delta

    if ts:
        stats["cost_events"].append((ts, model_name, cost))

    stats["llm_events"].append(
        {
            "timestamp": ts,
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total,
            "cost": cost,
            "pricing_status": pricing["status"],
        }
    )

    _record_timestamp(stats, ts)


def create_project_stats(name: str, agent_cmd: str) -> ProjectStats:
    """Create a zeroed project aggregate."""
    return {
        "name": name,
        "agent_cmd": agent_cmd,
        "sessions": [],
        "total_messages": 0,
        "total_tokens": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_cost": 0.0,
        "total_llm_time": 0.0,
        "total_tool_time": 0.0,
        "models": defaultdict(create_model_stats),
        "tools": defaultdict(create_tool_stats),
        "daily_stats": defaultdict(create_daily_stats),
        "first_activity": None,
        "last_activity": None,
        "tps_samples": [],
        "usage_events": [],
    }


def build_session_record(
    filepath: Path,
    uid: str,
    relative_path: str,
    stats: SessionStats,
    agent_cmd: str,
    duration: float,
    subagent_sessions: list[Session] | None = None,
) -> Session:
    """Build the serializable session record used by the UI and registry."""
    pricing_status = ""
    for model_stats in stats["models"].values():
        pricing_status = _merge_pricing_status(
            pricing_status, model_stats.get("pricing_status", "unknown")
        )
    return Session(
        file=filepath.name,
        path=str(filepath),
        uid=uid,
        relative_path=relative_path,
        cwd=stats["cwd"],
        agent_cmd=agent_cmd,
        messages=stats["messages"],
        tokens=stats["total_tokens"],
        input_tokens=stats["input_tokens"],
        output_tokens=stats["output_tokens"],
        cache_read_tokens=stats["cache_read_tokens"],
        cache_write_tokens=stats["cache_write_tokens"],
        reasoning_tokens=stats["reasoning_tokens"],
        cost=stats["cost_total"],
        start=stats["start"],
        end=stats["end"],
        duration=duration,
        llm_time=stats["llm_time"],
        tool_time=stats["tool_time"],
        tools=dict(stats["tools"]),
        avg_tps=calc_avg_tokens_per_sec(stats["tps_samples"]),
        subagent_sessions=subagent_sessions or [],
        pricing_status=pricing_status or "unknown",
    )


def merge_model_stats(
    target: DefaultDict[str, ModelStats], source: DefaultDict[str, ModelStats]
) -> None:
    for model, source_stats in source.items():
        target_stats = target[model]
        for field in MODEL_STAT_FIELDS:
            target_stats[field] += source_stats.get(field, 0)
        for field in MODEL_PRICING_FIELDS:
            target_stats[field] += source_stats.get(field, 0)
        target_stats["pricing_status"] = _merge_pricing_status(
            target_stats["pricing_status"], source_stats.get("pricing_status", "unknown")
        )


def merge_tool_stats(
    target: DefaultDict[str, ToolStats], source: DefaultDict[str, ToolStats]
) -> None:
    for tool_name, source_stats in source.items():
        target_stats = target[tool_name]
        target_stats["calls"] += source_stats["calls"]
        target_stats["time"] += source_stats["time"]
        target_stats["errors"] += source_stats["errors"]


def accumulate_session_into_project(
    project_stats: ProjectStats,
    stats: SessionStats,
    *,
    session_uid: str = "",
) -> None:
    """Add a parsed session (or subagent session) to a project aggregate."""
    project_stats["total_messages"] += stats["messages"]
    project_stats["total_tokens"] += stats["total_tokens"]
    project_stats["total_input_tokens"] += stats["input_tokens"]
    project_stats["total_output_tokens"] += stats["output_tokens"]
    project_stats["total_cache_read_tokens"] += stats["cache_read_tokens"]
    project_stats["total_cache_write_tokens"] += stats["cache_write_tokens"]
    project_stats["total_reasoning_tokens"] += stats["reasoning_tokens"]
    project_stats["total_cost"] += stats["cost_total"]
    project_stats["total_llm_time"] += stats["llm_time"]
    project_stats["total_tool_time"] += stats["tool_time"]
    project_stats["tps_samples"].extend(stats["tps_samples"])

    merge_model_stats(project_stats["models"], stats["models"])
    merge_tool_stats(project_stats["tools"], stats["tools"])

    for event in stats["llm_events"]:
        project_stats["usage_events"].append(
            {
                **event,
                "agent": project_stats["agent_cmd"],
                "project": project_stats["name"],
                "session_id": session_uid,
            }
        )

    # Attribute cost to the day/model it was actually incurred on, using each
    # LLM call's own (timestamp, model, cost) rather than splitting the
    # session total evenly across every timestamp — an even split misattributes
    # cost across a midnight boundary or across models when a session uses
    # more than one.
    for ts, mdl, cost in stats["cost_events"]:
        day_key = ts.strftime("%Y-%m-%d")
        project_stats["daily_stats"][day_key]["messages"] += 1
        project_stats["daily_stats"][day_key]["cost"] += cost
        project_stats["daily_stats"][day_key]["models"][mdl] = (
            project_stats["daily_stats"][day_key]["models"].get(mdl, 0.0) + cost
        )

    if stats["start"]:
        if (
            project_stats["first_activity"] is None
            or stats["start"] < project_stats["first_activity"]
        ):
            project_stats["first_activity"] = stats["start"]
    if stats["end"]:
        if (
            project_stats["last_activity"] is None
            or stats["end"] > project_stats["last_activity"]
        ):
            project_stats["last_activity"] = stats["end"]


def get_project_path_from_jsonl(project_dir, source_type: str = "standard"):
    """Get the actual project path from the first session file's cwd field."""
    jsonl_files = sorted(project_dir.glob("*.jsonl"))
    for filepath in jsonl_files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if source_type == "claude":
                        # Most Claude records carry cwd (user, assistant, ...)
                        # but header/meta lines (permission-mode,
                        # file-history-snapshot, summary, ...) do not. Keep
                        # scanning the file until one with cwd shows up rather
                        # than giving up on the first line.
                        if data.get("cwd"):
                            return data["cwd"]
                        continue
                    elif source_type == "codex":
                        if data.get("type") == "session_meta":
                            cwd = data.get("payload", {}).get("cwd")
                            if cwd:
                                return cwd
                    elif source_type == "gemini":
                        # For Gemini, the project name is the parent of the chats directory
                        return project_dir.parent.name
                    else:
                        if data.get("type") == "session" and "cwd" in data:
                            return data["cwd"]
                    break  # Only check first relevant line
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return project_dir.name


def analyze_jsonl_file(filepath: Path) -> SessionStats:
    """Analyze a single JSONL file and return stats."""
    stats = create_session_stats()

    last_request_ts = None  # Timestamp of last user message or toolResult
    pending_tool_calls = {}  # tool_call_id -> {"name": str, "timestamp": datetime}
    cwd = ""

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            # First, try to read cwd from the session line
            first_line = f.readline().strip()
            if first_line:
                try:
                    session_data = json.loads(first_line)
                    if session_data.get("type") == "session":
                        cwd = session_data.get("cwd", "")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Now process the rest of the file
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("type") != "message" or "message" not in data:
                        continue

                    msg = data["message"]
                    ts = parse_timestamp(data.get("timestamp"))
                    role = msg.get("role")

                    # Process assistant messages (with or without usage)
                    if role == "assistant":
                        # Calculate LLM time for this call
                        llm_delta = 0
                        if ts and last_request_ts:
                            llm_delta = (ts - last_request_ts).total_seconds()
                            if 0 < llm_delta < 300:  # Cap at 5 min to filter outliers
                                stats["llm_time"] += llm_delta
                            else:
                                llm_delta = 0  # Invalid, don't use for tokens/sec
                            last_request_ts = None

                        # Process usage data if present
                        if "usage" in msg:
                            usage = msg["usage"]
                            cost = usage.get("cost", {})
                            model = msg.get("model", "unknown")

                            input_tok = to_nonnegative_int(usage.get("input", 0))
                            output_tok = to_nonnegative_int(usage.get("output", 0))
                            cache_read_tok = to_nonnegative_int(usage.get("cacheRead", 0))
                            cache_write_tok = to_nonnegative_int(usage.get("cacheWrite", 0))
                            total_tok = to_nonnegative_int(usage.get("totalTokens")) or (
                                input_tok
                                + output_tok
                                + cache_read_tok
                                + cache_write_tok
                            )
                            reported_cost = cost.get("total", 0)
                            try:
                                reported_cost = float(reported_cost or 0)
                            except (TypeError, ValueError):
                                reported_cost = 0.0
                            pricing = resolve_usage_pricing(
                                model,
                                input_tok,
                                output_tok,
                                cache_read_tok,
                                cache_write_tok,
                                reported_cost,
                            )

                            record_llm_usage(
                                stats,
                                model,
                                input_tok,
                                output_tok,
                                cache_read_tok,
                                cache_write_tok,
                                total_tokens=total_tok,
                                cost=pricing["cost"],
                                ts=ts,
                                llm_delta=llm_delta,
                                pricing=pricing,
                            )

                        # Track tool calls from assistant messages
                        if ts:
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if (
                                        isinstance(item, dict)
                                        and item.get("type") == "toolCall"
                                    ):
                                        tool_id = item.get("id")
                                        tool_name = item.get("name", "unknown")
                                        if tool_id:
                                            pending_tool_calls[tool_id] = {
                                                "name": tool_name,
                                                "timestamp": ts,
                                            }

                    elif role == "user":
                        if ts:
                            last_request_ts = ts

                    elif role == "toolResult":
                        if ts:
                            last_request_ts = ts
                            # Match tool result with pending call
                            tool_call_id = msg.get("toolCallId")
                            tool_name = msg.get("toolName", "unknown")
                            is_error = msg.get("isError", False)

                            if tool_call_id and tool_call_id in pending_tool_calls:
                                call_info = pending_tool_calls.pop(tool_call_id)
                                tool_delta = (
                                    ts - call_info["timestamp"]
                                ).total_seconds()
                                if (
                                    0 < tool_delta < 600
                                ):  # Cap at 10 min to filter outliers
                                    stats["tool_time"] += tool_delta
                                    stats["tools"][tool_name]["calls"] += 1
                                    stats["tools"][tool_name]["time"] += tool_delta
                                    if is_error:
                                        stats["tools"][tool_name]["errors"] += 1

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

    stats["cwd"] = cwd
    return stats


def analyze_claude_jsonl_file(filepath: Path) -> SessionStats:
    """Analyze a Claude Code JSONL session file and return stats.

    Claude Code format: each line is a JSON record with top-level 'type' field.
    Types include: user, assistant, progress, file-history-snapshot, summary.
    Usage is in message.usage with input_tokens, output_tokens, cache_read_input_tokens,
    cache_creation_input_tokens. No embedded cost - compute via get_manual_cost().
    """
    stats = create_session_stats()

    last_request_ts = None
    pending_tool_calls = {}  # tool_use id -> {"name": str, "timestamp": datetime}
    cwd = ""

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                record_type = data.get("type")

                # Skip progress records (subagent data - avoid double-counting)
                # Skip file-history-snapshot and summary records
                if record_type in ("progress", "file-history-snapshot", "summary"):
                    continue

                # Extract cwd from first record that has it
                if not cwd and data.get("cwd"):
                    cwd = data["cwd"]

                ts = parse_timestamp(data.get("timestamp"))

                if record_type == "user":
                    if ts:
                        last_request_ts = ts
                    # Check for tool_result in user message content
                    msg = data.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if not isinstance(item, dict):
                                continue
                            if item.get("type") == "tool_result":
                                tool_use_id = item.get("tool_use_id")
                                is_error = item.get("is_error", False)
                                if (
                                    ts
                                    and tool_use_id
                                    and tool_use_id in pending_tool_calls
                                ):
                                    call_info = pending_tool_calls.pop(tool_use_id)
                                    tool_delta = (
                                        ts - call_info["timestamp"]
                                    ).total_seconds()
                                    if 0 < tool_delta < 600:
                                        stats["tool_time"] += tool_delta
                                        tool_name = call_info["name"]
                                        stats["tools"][tool_name]["calls"] += 1
                                        stats["tools"][tool_name][
                                            "time"
                                        ] += tool_delta
                                        if is_error:
                                            stats["tools"][tool_name]["errors"] += 1

                elif record_type == "assistant":
                    msg = data.get("message", {})
                    usage = msg.get("usage", {})
                    model = msg.get("model", "")

                    # Skip synthetic records
                    if model == "<synthetic>":
                        continue

                    # Calculate LLM time
                    llm_delta = 0
                    if ts and last_request_ts:
                        llm_delta = (ts - last_request_ts).total_seconds()
                        if 0 < llm_delta < 300:
                            stats["llm_time"] += llm_delta
                        else:
                            llm_delta = 0
                        last_request_ts = None

                    # Process usage data if present
                    if usage and model:
                        input_tok = to_nonnegative_int(usage.get("input_tokens", 0))
                        output_tok = to_nonnegative_int(usage.get("output_tokens", 0))
                        cache_read_tok = to_nonnegative_int(
                            usage.get("cache_read_input_tokens", 0)
                        )
                        cache_write_tok = to_nonnegative_int(
                            usage.get("cache_creation_input_tokens", 0)
                        )
                        total_tok = input_tok + output_tok + cache_read_tok + cache_write_tok

                        pricing = price_model(
                            model,
                            input_tok,
                            output_tok,
                            cache_read_tok,
                            cache_write_tok,
                        )

                        record_llm_usage(
                            stats,
                            model,
                            input_tok,
                            output_tok,
                            cache_read_tok,
                            cache_write_tok,
                            total_tokens=total_tok,
                            cost=pricing["cost"],
                            ts=ts,
                            llm_delta=llm_delta,
                            pricing=pricing,
                        )

                    # Track tool_use calls from assistant content
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if (
                                isinstance(item, dict)
                                and item.get("type") == "tool_use"
                            ):
                                tool_id = item.get("id")
                                tool_name = item.get("name", "unknown")
                                if tool_id and ts:
                                    pending_tool_calls[tool_id] = {
                                        "name": tool_name,
                                        "timestamp": ts,
                                    }

    except Exception as e:
        print(f"Error reading Claude session {filepath}: {e}")

    stats["cwd"] = cwd
    return stats


def analyze_codex_jsonl_file(filepath: Path) -> SessionStats:
    """Analyze a Codex CLI JSONL session file and return stats.

    Codex format uses record types: session_meta, turn_context, event_msg, response_item.
    Usage is in event_msg records where payload.type == "token_count".
    We prefer last_token_usage deltas when available, otherwise derive deltas from
    total_token_usage using running totals.
    """

    def to_nonneg_int(value) -> int:
        try:
            if value is None:
                return 0
            return max(0, int(value))
        except (TypeError, ValueError):
            try:
                return max(0, int(float(value)))
            except (TypeError, ValueError):
                return 0

    def parse_usage(usage_obj: dict | None) -> dict | None:
        if not isinstance(usage_obj, dict):
            return None

        raw_input = to_nonneg_int(usage_obj.get("input_tokens", 0))
        cache_read = to_nonneg_int(usage_obj.get("cached_input_tokens", 0))
        output = to_nonneg_int(usage_obj.get("output_tokens", 0))
        reasoning = to_nonneg_int(usage_obj.get("reasoning_output_tokens", 0))
        reported_total = to_nonneg_int(usage_obj.get("total_tokens", 0))

        # Codex input_tokens includes cached_input_tokens. Store net input to avoid
        # double counting input + cache read in totals and manual pricing.
        input_net = max(0, raw_input - cache_read)

        computed_total = input_net + output + cache_read
        total = reported_total or computed_total

        return {
            "input_tokens": input_net,
            "output_tokens": output,
            "reasoning_tokens": reasoning,
            "cache_read_tokens": cache_read,
            "total_tokens": total,
        }

    def subtract_usage(current: dict, previous: dict) -> dict:
        return {
            "input_tokens": max(
                0, current["input_tokens"] - previous["input_tokens"]
            ),
            "output_tokens": max(
                0, current["output_tokens"] - previous["output_tokens"]
            ),
            "reasoning_tokens": max(
                0, current["reasoning_tokens"] - previous["reasoning_tokens"]
            ),
            "cache_read_tokens": max(
                0,
                current["cache_read_tokens"] - previous["cache_read_tokens"],
            ),
            "total_tokens": max(
                0, current["total_tokens"] - previous["total_tokens"]
            ),
        }

    def add_usage(left: dict, right: dict) -> dict:
        return {
            "input_tokens": left["input_tokens"] + right["input_tokens"],
            "output_tokens": left["output_tokens"] + right["output_tokens"],
            "reasoning_tokens": left["reasoning_tokens"]
            + right["reasoning_tokens"],
            "cache_read_tokens": left["cache_read_tokens"]
            + right["cache_read_tokens"],
            "total_tokens": left["total_tokens"] + right["total_tokens"],
        }

    stats = create_session_stats()

    cwd = ""
    model = ""
    pending_tool_calls = {}  # call_id -> {"name": str, "timestamp": datetime}
    previous_total_usage = None
    previous_token_count_sig = None

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                record_type = data.get("type")
                payload = data.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                ts = parse_timestamp(data.get("timestamp"))

                if record_type == "session_meta":
                    if not cwd:
                        cwd = payload.get("cwd", "")
                    if ts:
                        if stats["start"] is None or ts < stats["start"]:
                            stats["start"] = ts

                elif record_type == "turn_context":
                    if payload.get("model"):
                        model = payload["model"]

                elif record_type == "event_msg":
                    if payload.get("type") != "token_count":
                        continue

                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue

                    # Codex emits each token_count event twice in a row with
                    # identical usage. Skip the duplicate so we don't count it
                    # (and its cost) twice. total_token_usage is cumulative and
                    # monotonic, so distinct real turns never share a signature.
                    token_count_sig = (
                        info.get("last_token_usage"),
                        info.get("total_token_usage"),
                    )
                    if token_count_sig == previous_token_count_sig:
                        continue
                    previous_token_count_sig = token_count_sig

                    last_usage = parse_usage(info.get("last_token_usage"))
                    total_usage = parse_usage(info.get("total_token_usage"))

                    delta_usage = None
                    latest_total_usage = None

                    if last_usage:
                        delta_usage = last_usage
                        latest_total_usage = total_usage
                    elif total_usage:
                        if previous_total_usage and (
                            total_usage["total_tokens"]
                            < previous_total_usage["total_tokens"]
                        ):
                            # The cumulative counter decreased (e.g. a context
                            # compaction/reset shrank the running total).
                            # subtract_usage would clamp every field to 0 here
                            # and silently drop this turn's usage forever, so
                            # treat the new cumulative value as a fresh epoch
                            # and charge it directly instead.
                            delta_usage = total_usage
                        else:
                            delta_usage = (
                                subtract_usage(total_usage, previous_total_usage)
                                if previous_total_usage
                                else total_usage
                            )
                        latest_total_usage = total_usage

                    if not delta_usage:
                        continue

                    has_usage_signal = (
                        delta_usage["input_tokens"] > 0
                        or delta_usage["output_tokens"] > 0
                        or delta_usage["reasoning_tokens"] > 0
                        or delta_usage["cache_read_tokens"] > 0
                        or delta_usage["total_tokens"] > 0
                    )
                    if not has_usage_signal:
                        if latest_total_usage:
                            previous_total_usage = latest_total_usage
                        continue

                    input_tok = delta_usage["input_tokens"]
                    output_tok = delta_usage["output_tokens"]
                    cache_read_tok = delta_usage["cache_read_tokens"]
                    reasoning_tok = delta_usage["reasoning_tokens"]
                    total_tok = delta_usage["total_tokens"]

                    pricing = price_model(
                        model, input_tok, output_tok, cache_read_tok
                    )

                    record_llm_usage(
                        stats,
                        model,
                        input_tok,
                        output_tok,
                        cache_read_tok,
                        reasoning_tokens=reasoning_tok,
                        total_tokens=total_tok,
                        cost=pricing["cost"],
                        ts=ts,
                        pricing=pricing,
                    )

                    if latest_total_usage:
                        previous_total_usage = latest_total_usage
                    elif previous_total_usage:
                        previous_total_usage = add_usage(
                            previous_total_usage, delta_usage
                        )
                    else:
                        previous_total_usage = delta_usage

                elif record_type == "response_item":
                    payload_type = payload.get("type")

                    if payload_type == "function_call":
                        call_id = payload.get("call_id")
                        tool_name = payload.get("name", "unknown")
                        if call_id and ts:
                            pending_tool_calls[call_id] = {
                                "name": tool_name,
                                "timestamp": ts,
                            }

                    elif payload_type == "function_call_output":
                        call_id = payload.get("call_id")
                        if ts and call_id and call_id in pending_tool_calls:
                            call_info = pending_tool_calls.pop(call_id)
                            tool_delta = (
                                ts - call_info["timestamp"]
                            ).total_seconds()
                            if 0 < tool_delta < 600:
                                stats["tool_time"] += tool_delta
                                tool_name = call_info["name"]
                                stats["tools"][tool_name]["calls"] += 1
                                stats["tools"][tool_name]["time"] += tool_delta

                    if ts:
                        if stats["end"] is None or ts > stats["end"]:
                            stats["end"] = ts

    except Exception as e:
        print(f"Error reading Codex session {filepath}: {e}")

    stats["cwd"] = cwd
    return stats


def analyze_gemini_jsonl_file(filepath: Path) -> SessionStats:
    """Analyze a Gemini CLI JSONL session file and return stats."""
    stats = create_session_stats()

    # Prefer an explicit cwd in the record; Gemini's history sidecar is only
    # a fallback for older sessions.
    project_name = filepath.parent.parent.name
    history_root = Path.home() / ".gemini" / "history" / project_name / ".project_root"
    if history_root.exists():
        try:
            stats["cwd"] = history_root.read_text().strip()
        except Exception:
            pass

    last_request_ts = None

    try:
        with open(filepath, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                record_type = data.get("type")
                if not stats["cwd"] and data.get("cwd"):
                    stats["cwd"] = str(data["cwd"])
                # Gemini format uses startTime for the session meta line, and timestamp for others
                ts_str = data.get("timestamp") or data.get("startTime")
                ts = parse_timestamp(ts_str)

                if ts:
                    if stats["start"] is None or ts < stats["start"]:
                        stats["start"] = ts
                    if stats["end"] is None or ts > stats["end"]:
                        stats["end"] = ts

                if record_type == "user":
                    if ts:
                        last_request_ts = ts
                
                elif record_type == "gemini":
                    model = data.get("model", "unknown")
                    tokens = data.get("tokens", {})
                    
                    # Calculate LLM time
                    llm_delta = 0
                    if ts and last_request_ts:
                        llm_delta = (ts - last_request_ts).total_seconds()
                        if 0 < llm_delta < 300:
                            stats["llm_time"] += llm_delta
                        else:
                            llm_delta = 0
                        last_request_ts = None

                    raw_input_tok = to_nonnegative_int(tokens.get("input", 0))
                    output_tok = to_nonnegative_int(tokens.get("output", 0))
                    cache_read_tok = to_nonnegative_int(tokens.get("cached", 0))
                    cache_write_tok = to_nonnegative_int(tokens.get("cacheWrite", 0))

                    # Gemini's reported "input" token count is inclusive of any
                    # cached tokens served from context cache, so bill/store
                    # only the net (uncached) portion at the input rate to
                    # avoid double counting input + cache read (mirrors the
                    # same fix applied to the Codex analyzer above).
                    input_tok = max(0, raw_input_tok - cache_read_tok)
                    total_tok = to_nonnegative_int(tokens.get("total")) or (
                        input_tok + output_tok + cache_read_tok + cache_write_tok
                    )

                    pricing = price_model(
                        model,
                        input_tok,
                        output_tok,
                        cache_read_tok,
                        cache_write_tok,
                    )

                    record_llm_usage(
                        stats,
                        model,
                        input_tok,
                        output_tok,
                        cache_read_tok,
                        cache_write_tok,
                        total_tokens=total_tok,
                        cost=pricing["cost"],
                        ts=ts,
                        llm_delta=llm_delta,
                        pricing=pricing,
                    )

                    # Process tool calls
                    tool_calls = data.get("toolCalls", [])
                    for tc in tool_calls:
                        tool_name = tc.get("name", "unknown")
                        # Tool execution completion timestamp
                        tc_ts = parse_timestamp(tc.get("timestamp"))
                        if tc_ts and ts:
                            tool_delta = (tc_ts - ts).total_seconds()
                            if 0 < tool_delta < 600:
                                stats["tool_time"] += tool_delta
                                stats["tools"][tool_name]["calls"] += 1
                                stats["tools"][tool_name]["time"] += tool_delta
                                if tc.get("status") == "error":
                                    stats["tools"][tool_name]["errors"] += 1

    except Exception as e:
        print(f"Error reading Gemini session {filepath}: {e}")

    return stats


def analyze_session_file(filepath: Path, source_type: str) -> SessionStats:
    """Dispatch to the correct parser based on source type."""
    if source_type == "claude":
        return analyze_claude_jsonl_file(filepath)
    elif source_type == "codex":
        return analyze_codex_jsonl_file(filepath)
    elif source_type == "gemini":
        return analyze_gemini_jsonl_file(filepath)
    else:
        return analyze_jsonl_file(filepath)


def analyze_project(
    project_dir: Path, agent_cmd: str, source_type: str = "standard"
) -> ProjectStats | None:
    """Analyze all sessions in a project directory."""

    # Gemini sessions are in a 'chats' subdirectory within the project folder
    if source_type == "gemini" and project_dir.name != "chats":
        chats_dir = project_dir / "chats"
        if chats_dir.exists() and chats_dir.is_dir():
            project_dir = chats_dir
        else:
            return None

    project_stats = create_project_stats(
        get_project_path_from_jsonl(project_dir, source_type), agent_cmd
    )

    # Only get top-level JSONL files (not in subdirectories)
    jsonl_files = list(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    for filepath in sorted(jsonl_files):
        stats = analyze_session_file(filepath, source_type)
        if stats["messages"] == 0:
            continue

        duration = (
            (stats["end"] - stats["start"]).total_seconds()
            if stats["start"] and stats["end"]
            else 0
        )

        # Look for subagent sessions in a matching subdirectory
        # e.g., "session.jsonl" -> "session/" directory
        session_name = filepath.stem  # filename without .jsonl extension
        subagent_dir = filepath.parent / session_name

        subagent_sessions = []
        if subagent_dir.exists() and subagent_dir.is_dir():
            # Find all JSONL files in the subagent directory
            for sub_jsonl in sorted(subagent_dir.rglob("*.jsonl")):
                sub_stats = analyze_session_file(sub_jsonl, source_type)
                if sub_stats["messages"] > 0:
                    sub_duration = (
                        (sub_stats["end"] - sub_stats["start"]).total_seconds()
                        if sub_stats["start"] and sub_stats["end"]
                        else 0
                    )
                    try:
                        sub_relative = sub_jsonl.relative_to(project_dir)
                    except ValueError:
                        sub_relative = sub_jsonl

                    # Get UID from file or generate random one
                    sub_uid = get_session_id_from_file(
                        str(sub_jsonl), source_type
                    ) or str(uuid.uuid4())

                    sub_session = build_session_record(
                        sub_jsonl,
                        sub_uid,
                        str(sub_relative),
                        sub_stats,
                        agent_cmd,
                        sub_duration,
                    )
                    SESSION_REGISTRY[sub_uid] = sub_session
                    subagent_sessions.append(sub_session)
                    accumulate_session_into_project(
                        project_stats, sub_stats, session_uid=sub_uid
                    )

        # Get UID from file or generate random one
        session_uid = get_session_id_from_file(str(filepath), source_type) or str(
            uuid.uuid4()
        )

        session = build_session_record(
            filepath,
            session_uid,
            filepath.name,
            stats,
            agent_cmd,
            duration,
            subagent_sessions,
        )
        SESSION_REGISTRY[session_uid] = session
        project_stats["sessions"].append(session)
        accumulate_session_into_project(
            project_stats, stats, session_uid=session_uid
        )

    return project_stats if project_stats["sessions"] else None


def split_agent_command(agent_cmd: str) -> list[str]:
    """Split an agent command while respecting platform quoting rules."""
    try:
        parts = shlex.split(agent_cmd, posix=sys.platform != "win32")
    except ValueError:
        parts = agent_cmd.split()

    if sys.platform == "win32":
        parts = [part.strip('"') for part in parts]

    return parts


def shell_quote_path(path: str) -> str:
    """Quote a local path for the shell used by the resume command."""
    if os.name == "nt":
        return subprocess.list2cmdline([path])
    return shlex.quote(path)


def build_resume_command(session: Session) -> str:
    """Build a resume command from server-side session data."""
    cwd = session.get("cwd", "")
    agent_cmd = session.get("agent_cmd", "")
    uid = session.get("uid", "")
    if agent_cmd == "claude":
        command = f"claude --resume {shell_quote_path(uid)}"
    elif agent_cmd == "codex":
        command = f"codex --resume {shell_quote_path(uid)}"
    else:
        command = (
            f"{agent_cmd} --session {shell_quote_path(session.get('path', ''))}"
        )
    if not cwd:
        return command
    if os.name == "nt":
        return f"cd /d {shell_quote_path(cwd)} && {command}"
    return f"cd {shell_quote_path(cwd)} && {command}"


def resolve_command_executable(cmd: list[str]) -> list[str]:
    """Resolve console shims like pi.cmd on Windows before subprocess runs."""
    if not cmd:
        return cmd

    resolved = shutil.which(cmd[0])
    if not resolved and sys.platform == "win32" and not Path(cmd[0]).suffix:
        for ext in (".cmd", ".bat", ".exe"):
            resolved = shutil.which(cmd[0] + ext)
            if resolved:
                break

    return [resolved or cmd[0], *cmd[1:]]


def run_export_subprocess(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an export command, handling Windows .cmd/.bat shims correctly."""
    run_kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
    }

    if sys.platform == "win32" and cmd:
        suffix = Path(cmd[0]).suffix.lower()
        if suffix in {".cmd", ".bat"}:
            return subprocess.run(
                subprocess.list2cmdline(cmd),
                shell=True,
                **run_kwargs,
            )

    try:
        return subprocess.run(cmd, **run_kwargs)
    except FileNotFoundError:
        if sys.platform == "win32":
            return subprocess.run(
                subprocess.list2cmdline(cmd),
                shell=True,
                **run_kwargs,
            )
        raise


def export_session_to_html(session_path: str, agent_cmd: str) -> str:
    """Export a session file to HTML.

    For pi/omp: use agent_cmd --export.
    For claude/codex: use standalone export scripts.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # Create a unique output filename based on the session path
    session_hash = hash(session_path) & 0xFFFFFFFF
    output_file = TEMP_DIR / f"session_{session_hash}.html"

    try:
        base_cmd = split_agent_command(agent_cmd)
        base_cmd = resolve_command_executable(base_cmd)

        agent_name = Path(base_cmd[0]).name.lower() if base_cmd else ""

        if agent_name.startswith("claude"):
            script = Path(__file__).parent / "claude_export.py"
            cmd = [sys.executable or "python3", str(script), session_path, str(output_file)]
        elif agent_name.startswith("codex"):
            script = Path(__file__).parent / "codex_export.py"
            cmd = [sys.executable or "python3", str(script), session_path, str(output_file)]
        elif agent_name.startswith("gemini"):
            script = Path(__file__).parent / "gemini_export.py"
            cmd = [sys.executable or "python3", str(script), session_path, str(output_file)]
        else:
            cmd = [*base_cmd, "--export", session_path, str(output_file)]

        result = run_export_subprocess(cmd)
        if result.returncode == 0 and output_file.exists():
            return output_file.read_text(encoding="utf-8")
    except Exception as e:
        return f"<html><body><h1>Error exporting session</h1><pre>{html.escape(str(e))}</pre></body></html>"

    error_text = result.stderr or result.stdout or "Unknown export error"
    return f"<html><body><h1>Error exporting session</h1><pre>{html.escape(error_text)}</pre></body></html>"


def get_session_cwd(session_path: str, source_type: str = "standard") -> str:
    """Get the working directory from a session file."""
    try:
        with open(session_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if source_type == "claude":
                    if data.get("type") in ("file-history-snapshot", "summary"):
                        continue
                    if data.get("cwd"):
                        return data["cwd"]
                    break
                elif source_type == "codex":
                    if data.get("type") == "session_meta":
                        return data.get("payload", {}).get("cwd", "")
                    # session_meta can be preceded by other record types in a
                    # resumed/forked session — keep scanning instead of giving
                    # up after one line (which would otherwise dump this
                    # session into the catch-all "unknown" project bucket).
                    continue
                else:
                    if data.get("type") == "session" and "cwd" in data:
                        return data["cwd"]
                    continue
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass
    return ""


def _build_codex_project_stats(
    project_cwd: str, files: list[Path], agent_cmd: str
) -> ProjectStats | None:
    """Build a ProjectStats from a list of Codex session files grouped by cwd."""
    project_stats = create_project_stats(project_cwd, agent_cmd)

    for filepath in sorted(files):
        stats = analyze_codex_jsonl_file(filepath)
        if stats["messages"] == 0:
            continue

        duration = (
            (stats["end"] - stats["start"]).total_seconds()
            if stats["start"] and stats["end"]
            else 0
        )

        session_uid = get_session_id_from_file(str(filepath), "codex") or str(
            uuid.uuid4()
        )

        session = build_session_record(
            filepath,
            session_uid,
            filepath.name,
            stats,
            agent_cmd,
            duration,
        )
        SESSION_REGISTRY[session_uid] = session
        project_stats["sessions"].append(session)
        accumulate_session_into_project(
            project_stats, stats, session_uid=session_uid
        )

    return project_stats if project_stats["sessions"] else None


def _accumulate_global_stats(
    global_stats: GlobalStats, project_stats: ProjectStats
) -> None:
    """Accumulate project stats into global stats."""
    global_stats["total_cost"] += project_stats["total_cost"]
    global_stats["total_tokens"] += project_stats["total_tokens"]
    global_stats["total_input_tokens"] += project_stats["total_input_tokens"]
    global_stats["total_output_tokens"] += project_stats["total_output_tokens"]
    global_stats["total_cache_read_tokens"] += project_stats["total_cache_read_tokens"]
    global_stats["total_cache_write_tokens"] += project_stats["total_cache_write_tokens"]
    global_stats["total_reasoning_tokens"] += project_stats["total_reasoning_tokens"]
    global_stats["total_messages"] += project_stats["total_messages"]
    global_stats["total_sessions"] += len(project_stats["sessions"])
    global_stats["total_projects"] += 1
    global_stats["total_llm_time"] += project_stats["total_llm_time"]
    global_stats["total_tool_time"] += project_stats["total_tool_time"]
    global_stats["tps_samples"].extend(project_stats["tps_samples"])
    global_stats["usage_events"].extend(project_stats["usage_events"])

    merge_model_stats(global_stats["models"], project_stats["models"])
    merge_tool_stats(global_stats["tools"], project_stats["tools"])

    for day, dstats in project_stats["daily_stats"].items():
        global_stats["daily_stats"][day]["messages"] += dstats["messages"]
        global_stats["daily_stats"][day]["cost"] += dstats["cost"]
        for mdl, mcost in dstats.get("models", {}).items():
            global_stats["daily_stats"][day]["models"][
                mdl
            ] = global_stats["daily_stats"][day]["models"].get(
                mdl, 0.0
            ) + mcost


def _as_path_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item]
    return []


def _config_session_values(config: dict) -> dict[str, list[str]]:
    raw = config.get("sessionDirs")
    if raw is None:
        raw = config.get("paths", {}).get("sessionDirs", {})
    if not isinstance(raw, dict):
        return {}

    aliases = {
        "session-dir": ("session", "sessionDirs", "standard"),
        "pi-dir": ("pi", "piDirs"),
        "omp-dir": ("omp", "ompDirs"),
        "claude-dir": ("claude", "claudeDirs"),
        "codex-dir": ("codex", "codexDirs"),
        "gemini-dir": ("gemini", "geminiDirs", "gemini-cli"),
    }
    result: dict[str, list[str]] = {}
    for arg_name, keys in aliases.items():
        values: list[str] = []
        for key in keys:
            values.extend(_as_path_values(raw.get(key)))
        if values:
            result[arg_name] = values
    return result


def build_session_dirs(
    *,
    config_path: Path | None = None,
    cli_values: dict[str, list[str] | None] | None = None,
    include_defaults: bool = True,
) -> list[tuple[Path, str, str]]:
    """Build a deduplicated, read-only list of session roots.

    Paths can be repeated on the command line and are resolved relative to the
    current process. Config-file paths are resolved relative to that config
    file. Missing paths are retained so a portable config can be shared across
    machines without failing startup.
    """
    config_path = config_path or CONFIG_PATH
    entries: list[tuple[Path, str, str]] = []
    if include_defaults:
        entries.extend(DEFAULT_SESSIONS_DIRS)

    config_values: dict[str, list[str]] = {}
    if config_path.is_file():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(config_data, dict):
                config_values = _config_session_values(config_data)
        except (OSError, json.JSONDecodeError):
            config_values = {}

    def append_values(
        arg_name: str, values: list[str], base_dir: Path
    ) -> None:
        spec = SESSION_DIR_SPECS.get(arg_name)
        if spec is None:
            return
        agent_cmd, source_type = spec
        for raw_value in values:
            path = Path(raw_value).expanduser()
            if not path.is_absolute():
                path = base_dir / path
            entries.append((path.resolve(), agent_cmd, source_type))

    for arg_name, values in config_values.items():
        append_values(arg_name, values, config_path.parent)
    for arg_name, values in (cli_values or {}).items():
        if values:
            append_values(arg_name, values, Path.cwd())

    result: list[tuple[Path, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path, agent_cmd, source_type in entries:
        key_path = str(path).casefold() if os.name == "nt" else str(path)
        key = (key_path, source_type)
        if key in seen:
            continue
        seen.add(key)
        result.append((path, agent_cmd, source_type))
    return result


def iter_project_dirs(sessions_dir: Path):
    """Yield project roots from a session directory or direct fixture path."""
    if not sessions_dir.is_dir():
        return
    if any(sessions_dir.glob("*.jsonl")):
        yield sessions_dir
        return
    try:
        children = sorted(sessions_dir.iterdir())
    except OSError:
        return
    for project_dir in children:
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            yield project_dir


def collect_all_stats(
    sessions_dirs: Sequence[tuple[Path, str, str]] | None = None,
) -> tuple[list[ProjectStats], GlobalStats]:
    """Collect statistics from all projects."""
    # Clear the session registry to avoid stale entries on reload
    clear_session_registry()

    all_projects: list[ProjectStats] = []
    global_stats: GlobalStats = {
        "total_cost": 0.0,
        "total_tokens": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_messages": 0,
        "total_sessions": 0,
        "total_projects": 0,
        "total_llm_time": 0.0,
        "total_tool_time": 0.0,
        "models": defaultdict(create_model_stats),
        "tools": defaultdict(create_tool_stats),
        "daily_stats": defaultdict(create_daily_stats),
        "tps_samples": [],
        "usage_events": [],
    }

    active_dirs = SESSIONS_DIRS if sessions_dirs is None else sessions_dirs
    for sessions_dir, agent_cmd, source_type in active_dirs:
        if not sessions_dir.exists():
            continue

        if source_type == "codex":
            # Codex: date-based hierarchy (YYYY/MM/DD/file.jsonl)
            # Group sessions by cwd to create virtual "projects"
            codex_projects: dict[str, list[Path]] = defaultdict(list)
            for jsonl_file in sessions_dir.rglob("*.jsonl"):
                cwd = get_session_cwd(str(jsonl_file), "codex")
                key = cwd if cwd else "unknown"
                codex_projects[key].append(jsonl_file)

            for project_cwd, files in codex_projects.items():
                # Create a temporary directory-like structure for analyze
                # by building ProjectStats directly
                project_stats = _build_codex_project_stats(
                    project_cwd, files, agent_cmd
                )
                if project_stats and project_stats["sessions"]:
                    all_projects.append(project_stats)
                    _accumulate_global_stats(global_stats, project_stats)
            continue

        # Standard, Claude, Gemini: iterate per-project subdirectories
        for project_dir in iter_project_dirs(sessions_dir):
            project_stats = analyze_project(project_dir, agent_cmd, source_type)

            if project_stats:
                all_projects.append(project_stats)
                _accumulate_global_stats(global_stats, project_stats)

    return all_projects, global_stats


MONTHLY_EXPORT_FIELDS = (
    "date",
    "timestamp",
    "agent",
    "project",
    "session_id",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "pricing_status",
)


def usage_event_to_export_row(event: dict) -> dict[str, object]:
    timestamp = event.get("timestamp")
    timestamp_text = timestamp.isoformat() if isinstance(timestamp, datetime) else ""
    status = str(event.get("pricing_status") or "unknown")
    return {
        "date": timestamp.strftime("%Y-%m-%d") if isinstance(timestamp, datetime) else "",
        "timestamp": timestamp_text,
        "agent": event.get("agent", ""),
        "project": display_project_name(str(event.get("project", ""))),
        "session_id": event.get("session_id", ""),
        "model": event.get("model", "unknown"),
        "input_tokens": event.get("input_tokens", 0),
        "output_tokens": event.get("output_tokens", 0),
        "cache_read_tokens": event.get("cache_read_tokens", 0),
        "cache_write_tokens": event.get("cache_write_tokens", 0),
        "reasoning_tokens": event.get("reasoning_tokens", 0),
        "total_tokens": event.get("total_tokens", 0),
        "estimated_cost_usd": (
            None if status == "unknown" else round(float(event.get("cost", 0.0)), 10)
        ),
        "pricing_status": status,
    }


def export_monthly_usage(
    month: str,
    output_format: str,
    output_path: Path | None = None,
    sessions_dirs: Sequence[tuple[Path, str, str]] | None = None,
) -> Path:
    """Export one calendar month's LLM calls to CSV or JSON."""
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("month must use YYYY-MM format")
    if output_format not in {"csv", "json"}:
        raise ValueError("output format must be csv or json")

    _, global_stats = collect_all_stats(sessions_dirs)
    rows = [
        usage_event_to_export_row(event)
        for event in global_stats["usage_events"]
        if isinstance(event.get("timestamp"), datetime)
        and event["timestamp"].strftime("%Y-%m") == month
    ]
    rows.sort(key=lambda row: (str(row["timestamp"]), str(row["session_id"])))

    output_path = output_path or Path.cwd() / f"monthly-{month}.{output_format}"
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MONTHLY_EXPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:
        output_path.write_text(
            json.dumps(
                {
                    "month": month,
                    "events": rows,
                    "event_count": len(rows),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return output_path


def generate_html(
    sessions_dirs: Sequence[tuple[Path, str, str]] | None = None,
):
    """Generate HTML dashboard."""
    all_projects, global_stats = collect_all_stats(sessions_dirs)

    # Sort projects by cost for initial display
    all_projects.sort(key=lambda p: -p["total_cost"])

    # Build projects JSON for client-side sorting
    projects_json = []
    for p in all_projects:
        sessions_json = []
        for s in p["sessions"]:
            duration_secs = s["duration"] if s["duration"] else 0
            llm_secs = s["llm_time"] if s["llm_time"] else 0
            project_label = display_project_name(p["name"])

            # Include subagent sessions in JSON
            sub_sessions_json = []
            for sub in s.get("subagent_sessions", []):
                sub_duration = sub["duration"] if sub["duration"] else 0
                sub_llm = sub["llm_time"] if sub["llm_time"] else 0
                sub_tool = sub.get("tool_time", 0) if sub.get("tool_time") else 0
                sub_tps = sub.get("avg_tps", 0)
                sub_sessions_json.append(
                    {
                        "file": sub["file"],
                        "uid": sub["uid"],
                        "relative_path": sub["relative_path"],
                        "project_name": display_project_name(sub["cwd"] or p["name"]),
                        "messages": sub["messages"],
                        "tokens": sub["tokens"],
                        "input_tokens": sub["input_tokens"],
                        "output_tokens": sub["output_tokens"],
                        "cache_read_tokens": sub["cache_read_tokens"],
                        "cache_write_tokens": sub["cache_write_tokens"],
                        "reasoning_tokens": sub["reasoning_tokens"],
                        "cost": sub["cost"],
                        "start": sub["start"].isoformat() if sub["start"] else "",
                        "start_display": sub["start"].strftime("%Y-%m-%d %H:%M")
                        if sub["start"]
                        else "N/A",
                        "end": sub["end"].isoformat() if sub["end"] else "",
                        "duration": sub_duration,
                        "duration_display": format_duration(sub_duration),
                        "llm_time": sub_llm,
                        "llm_time_display": format_duration(sub_llm),
                        "tool_time": sub_tool,
                        "tool_time_display": format_duration(sub_tool),
                        "avg_tps": sub_tps,
                        "pricing_status": sub["pricing_status"],
                    }
                )

            tool_secs = s.get("tool_time", 0) if s.get("tool_time") else 0
            session_tps = s.get("avg_tps", 0)
            sessions_json.append(
                {
                    "file": s["file"],
                    "uid": s["uid"],
                    "relative_path": s.get("relative_path", s["file"]),
                    "project_name": project_label,
                    "messages": s["messages"],
                    "tokens": s["tokens"],
                    "input_tokens": s["input_tokens"],
                    "output_tokens": s["output_tokens"],
                    "cache_read_tokens": s["cache_read_tokens"],
                    "cache_write_tokens": s["cache_write_tokens"],
                    "reasoning_tokens": s["reasoning_tokens"],
                    "cost": s["cost"],
                    "start": s["start"].isoformat() if s["start"] else "",
                    "start_display": s["start"].strftime("%Y-%m-%d %H:%M")
                    if s["start"]
                    else "N/A",
                    "end": s["end"].isoformat() if s["end"] else "",
                    "duration": duration_secs,
                    "duration_display": format_duration(duration_secs),
                    "llm_time": llm_secs,
                    "llm_time_display": format_duration(llm_secs),
                    "tool_time": tool_secs,
                    "tool_time_display": format_duration(tool_secs),
                    "avg_tps": session_tps,
                    "pricing_status": s["pricing_status"],
                    "subagent_sessions": sub_sessions_json,
                }
            )
        # Build model breakdown for this project
        models_list = []
        for model_name, mstats in sorted(
            p["models"].items(), key=lambda x: -x[1]["cost"]
        ):
            model_tps = (
                mstats.get("output_tokens", 0) / mstats.get("llm_time", 1)
                if mstats.get("llm_time", 0) > 0
                else 0
            )
            models_list.append(
                {
                    "name": model_name,
                    "messages": mstats["messages"],
                    "tokens": mstats["tokens"],
                    "input_tokens": mstats["input_tokens"],
                    "output_tokens": mstats["output_tokens"],
                    "cache_read_tokens": mstats["cache_read_tokens"],
                    "cache_write_tokens": mstats["cache_write_tokens"],
                    "reasoning_tokens": mstats["reasoning_tokens"],
                    "cost": mstats["cost"],
                    "pricing_status": mstats["pricing_status"] or "unknown",
                    "avg_tps": model_tps,
                }
            )

        # Build tool breakdown for this project
        tools_list = []
        for tool_name, tstats in sorted(
            p["tools"].items(), key=lambda x: -x[1]["time"]
        ):
            tools_list.append(
                {
                    "name": tool_name,
                    "calls": tstats["calls"],
                    "time": tstats["time"],
                    "time_display": format_duration(tstats["time"]),
                    "errors": tstats["errors"],
                    "avg_time": tstats["time"] / tstats["calls"]
                    if tstats["calls"] > 0
                    else 0,
                    "avg_time_display": format_duration(
                        tstats["time"] / tstats["calls"]
                    )
                    if tstats["calls"] > 0
                    else "0s",
                }
            )

        project_avg_tps = calc_avg_tokens_per_sec(p["tps_samples"])
        project_pricing_status = ""
        for model_stats in p["models"].values():
            project_pricing_status = _merge_pricing_status(
                project_pricing_status,
                model_stats.get("pricing_status", "unknown"),
            )
        projects_json.append(
            {
                "name": display_project_name(p["name"]),
                "agent_cmd": p["agent_cmd"],  # Needed for resume command
                "sessions": len(p["sessions"]),
                "sessions_list": sessions_json,
                "messages": p["total_messages"],
                "tokens": p["total_tokens"],
                "input_tokens": p["total_input_tokens"],
                "output_tokens": p["total_output_tokens"],
                "cache_read_tokens": p["total_cache_read_tokens"],
                "cache_write_tokens": p["total_cache_write_tokens"],
                "reasoning_tokens": p["total_reasoning_tokens"],
                "cost": p["total_cost"],
                "pricing_status": project_pricing_status or "unknown",
                "llm_time": p["total_llm_time"],
                "llm_time_display": format_duration(p["total_llm_time"]),
                "tool_time": p["total_tool_time"],
                "tool_time_display": format_duration(p["total_tool_time"]),
                "avg_tps": project_avg_tps,
                "last_activity": p["last_activity"].isoformat()
                if p["last_activity"]
                else "",
                "last_activity_display": p["last_activity"].strftime("%Y-%m-%d %H:%M")
                if p["last_activity"]
                else "N/A",
                "models": models_list,
                "tools": tools_list,
            }
        )

    # Build daily stats JSON for client-side chart rendering.
    # Each entry: {day, cost, models: {modelName: cost}}
    daily_stats_list = []
    for day in sorted(global_stats["daily_stats"].keys()):
        day_data = global_stats["daily_stats"][day]
        daily_stats_list.append(
            {
                "day": day,
                "cost": day_data["cost"],
                "models": day_data.get("models", {}),
            }
        )

    # Build global models JSON for client-side sorting
    total_cost_val = global_stats["total_cost"] if global_stats["total_cost"] > 0 else 1
    models_json = []
    for model_name, mstats in global_stats["models"].items():
        model_tps = (
            mstats.get("output_tokens", 0) / mstats.get("llm_time", 1)
            if mstats.get("llm_time", 0) > 0
            else 0
        )
        models_json.append(
            {
                "name": model_name,
                "messages": mstats["messages"],
                "tokens": mstats["tokens"],
                "input_tokens": mstats.get("input_tokens", 0),
                "output_tokens": mstats.get("output_tokens", 0),
                "cache_read_tokens": mstats.get("cache_read_tokens", 0),
                "cache_write_tokens": mstats.get("cache_write_tokens", 0),
                "reasoning_tokens": mstats.get("reasoning_tokens", 0),
                "llm_time": mstats.get("llm_time", 0),
                "cost": mstats["cost"],
                "pricing_status": mstats.get("pricing_status") or "unknown",
                "avg_tps": model_tps,
                "pct": mstats["cost"] / total_cost_val * 100,
            }
        )

    # Build global tools JSON for client-side sorting
    total_tool_time_val = global_stats["total_tool_time"] if global_stats["total_tool_time"] > 0 else 1
    tools_json = []
    for tool_name, tstats in global_stats["tools"].items():
        tools_json.append(
            {
                "name": tool_name,
                "calls": tstats["calls"],
                "time": tstats["time"],
                "time_display": format_duration(tstats["time"]),
                "errors": tstats["errors"],
                "avg_time": tstats["time"] / tstats["calls"]
                if tstats["calls"] > 0
                else 0,
                "avg_time_display": format_duration(
                    tstats["time"] / tstats["calls"]
                )
                if tstats["calls"] > 0
                else "0s",
                "pct": tstats["time"] / total_tool_time_val * 100,
            }
        )

    global_pricing_status = ""
    for model_stats in global_stats["models"].values():
        global_pricing_status = _merge_pricing_status(
            global_pricing_status,
            model_stats.get("pricing_status", "unknown"),
        )

    dashboard_css = load_asset("dashboard.css")
    dashboard_js = load_asset("dashboard.js")
    dashboard_data_json = json_for_script(
        {
            "projects": projects_json,
            "dailyStats": daily_stats_list,
            "models": models_json,
            "tools": tools_json,
            "totalCost": global_stats["total_cost"],
            "totalToolTime": global_stats["total_tool_time"],
        }
    )
    token_summary_card = render_token_summary_card(global_stats)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cost Dashboard</title>
    <style>
{dashboard_css}
    </style>
</head>
<body>
    <div class="container">
        <h1>Cost Dashboard</h1>
        <p class="subtitle">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} <span class="refresh-note">Refresh page for updated stats</span></p>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Cost</div>
                <div class="value cost">{cost_display(global_stats["total_cost"], global_pricing_status or "unknown")}</div>
            </div>
            <div class="stat-card">
                <div class="label">Projects</div>
                <div class="value">{global_stats["total_projects"]}</div>
            </div>
            <div class="stat-card">
                <div class="label">Sessions</div>
                <div class="value">{global_stats["total_sessions"]}</div>
            </div>
            <div class="stat-card">
                <div class="label">LLM Calls</div>
                <div class="value" title="{format_full_number(global_stats["total_messages"])}">{format_tokens(global_stats["total_messages"])}</div>
            </div>
            {token_summary_card}
            <div class="stat-card">
                <div class="label">LLM Time</div>
                <div class="value" style="color: var(--accent-purple)">{format_duration(global_stats["total_llm_time"])}</div>
            </div>
            <div class="stat-card">
                <div class="label">Tool Time</div>
                <div class="value" style="color: var(--accent-yellow)">{format_duration(global_stats["total_tool_time"])}</div>
            </div>
            <div class="stat-card">
                <div class="label">Avg Tokens/s</div>
                <div class="value" style="color: var(--accent-blue)">{calc_avg_tokens_per_sec(global_stats["tps_samples"]):.1f}</div>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <span>Daily Spending</span>
            </div>
            <div class="daily-chart" id="daily-chart-content"></div>
        </div>

        <div class="section">
            <div class="section-header">
                <span>Models Used</span>
            </div>
            <table id="models-table">
                <thead>
                    <tr>
                        <th data-sort="name">Model <span class="sort-icon">▼</span></th>
                        <th data-sort="messages">Messages <span class="sort-icon">▼</span></th>
                        <th data-sort="tokens">Total <span class="sort-icon">▼</span></th>
                        <th data-sort="input_tokens">Input <span class="sort-icon">▼</span></th>
                        <th data-sort="output_tokens">Output <span class="sort-icon">▼</span></th>
                        <th data-sort="cache_read_tokens">Cache Read <span class="sort-icon">▼</span></th>
                        <th data-sort="cache_write_tokens">Cache Write <span class="sort-icon">▼</span></th>
                        <th data-sort="reasoning_tokens">Reasoning <span class="sort-icon">▼</span></th>
                        <th data-sort="avg_tps">Avg Tokens/s <span class="sort-icon">▼</span></th>
                        <th data-sort="cost">Cost <span class="sort-icon">▼</span></th>
                        <th data-sort="pct">% of Total <span class="sort-icon">▼</span></th>
                    </tr>
                </thead>
                <tbody id="models-tbody">
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-header">
                <span>Tools Used</span>
            </div>
            <table id="tools-table">
                <thead>
                    <tr>
                        <th data-sort="name">Tool <span class="sort-icon">▼</span></th>
                        <th data-sort="calls">Calls <span class="sort-icon">▼</span></th>
                        <th data-sort="time">Total Time <span class="sort-icon">▼</span></th>
                        <th data-sort="avg_time">Avg Time <span class="sort-icon">▼</span></th>
                        <th data-sort="errors">Errors <span class="sort-icon">▼</span></th>
                        <th data-sort="pct">% of Time <span class="sort-icon">▼</span></th>
                    </tr>
                </thead>
                <tbody id="tools-tbody">
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-header">
                <span>Projects</span>
                <span class="badge">{len(all_projects)} projects</span>
            </div>
            <table id="projects-table">
                <thead>
                    <tr>
                        <th data-sort="name">Project <span class="sort-icon">▼</span></th>
                        <th data-sort="sessions">Sessions <span class="sort-icon">▼</span></th>
                        <th data-sort="messages">Messages <span class="sort-icon">▼</span></th>
                        <th data-sort="tokens">Tokens <span class="sort-icon">▼</span></th>
                        <th data-sort="llm_time">LLM Time <span class="sort-icon">▼</span></th>
                        <th data-sort="tool_time">Tool Time <span class="sort-icon">▼</span></th>
                        <th data-sort="avg_tps">Tok/s <span class="sort-icon">▼</span></th>
                        <th data-sort="cost">Cost <span class="sort-icon">▼</span></th>
                        <th data-sort="last_activity" class="sorted">Last Activity <span class="sort-icon">▼</span></th>
                    </tr>
                </thead>
                <tbody id="projects-tbody">
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-header">
                <span>All Sessions</span>
                <span class="badge" id="sessions-count"></span>
            </div>
            <table id="sessions-table">
                <thead>
                    <tr>
                        <th data-sort="project">Project / Session <span class="sort-icon">▼</span></th>
                        <th data-sort="start">Date <span class="sort-icon">▼</span></th>
                        <th data-sort="duration">Duration <span class="sort-icon">▼</span></th>
                        <th data-sort="llm_time">LLM Time <span class="sort-icon">▼</span></th>
                        <th data-sort="tool_time">Tool Time <span class="sort-icon">▼</span></th>
                        <th data-sort="avg_tps">Tok/s <span class="sort-icon">▼</span></th>
                        <th data-sort="messages">Messages <span class="sort-icon">▼</span></th>
                        <th data-sort="tokens">Tokens <span class="sort-icon">▼</span></th>
                        <th data-sort="cost">Cost <span class="sort-icon">▼</span></th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="sessions-tbody">
                </tbody>
            </table>
        </div>

        <footer>
            Cost Dashboard • Data from local agent session directories
        </footer>
    </div>
    <script>
        window.dashboardData = {dashboard_data_json};
    </script>
    <script>
{dashboard_js}
    </script>
</body>
</html>
"""

    return html_content


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the dashboard."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html_content = generate_html(
                getattr(self.server, "session_dirs", None)
            )
            self.wfile.write(html_content.encode("utf-8"))

        elif parsed.path.startswith("/assets/"):
            # Serve static dashboard assets (background image, etc.)
            name = Path(parsed.path).name
            if name in {".", ".."} or "/" in name or "\\" in name:
                self.send_response(400)
                self.end_headers()
                return
            asset_path = ASSETS_DIR / name
            if not asset_path.is_file():
                self.send_response(404)
                self.end_headers()
                return
            suffix = asset_path.suffix.lower()
            content_type = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }.get(suffix, "application/octet-stream")
            data = asset_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        elif parsed.path == "/resume":
            uid = query.get("uid", [""])[0]
            session_info = SESSION_REGISTRY.get(uid)
            if not session_info:
                self.send_response(404)
                self.end_headers()
                return
            command = build_resume_command(session_info)
            payload = command.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif parsed.path == "/session":
            uid = query.get("uid", [""])[0]
            session_info = SESSION_REGISTRY.get(uid)

            if session_info:
                session_path = session_info["path"]
                agent_cmd = session_info["agent_cmd"]
                if Path(session_path).exists():
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    html_content = export_session_to_html(session_path, agent_cmd)
                    self.wfile.write(html_content.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h1>Session file not found</h1></body></html>"
                    )
            else:
                self.send_response(404)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h1>Invalid session ID</h1></body></html>"
                )

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


def main():
    parser = argparse.ArgumentParser(description="Cost Dashboard Server")
    parser.add_argument(
        "-H",
        "--host",
        type=require_loopback_host,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1 — loopback only; "
        "non-loopback addresses are rejected)",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=8753, help="Port to serve on (default: 8753)"
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="JSON config containing optional sessionDirs paths",
    )
    parser.add_argument(
        "--no-default-session-dirs",
        action="store_true",
        help="Only scan explicitly configured or command-line session directories",
    )
    for option_name in SESSION_DIR_SPECS:
        parser.add_argument(
            f"--{option_name}",
            dest=option_name.replace("-", "_"),
            action="append",
            metavar="PATH",
            help=f"Additional {option_name} path; repeat to scan multiple paths",
        )
    parser.add_argument(
        "--export-monthly",
        metavar="YYYY-MM",
        help="Export LLM calls for a month and exit",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        dest="export_format",
        help="Monthly export format (default: csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Monthly export output file (default: monthly-YYYY-MM.<format>)",
    )
    args = parser.parse_args()

    cli_values = {
        option_name: getattr(args, option_name.replace("-", "_"))
        for option_name in SESSION_DIR_SPECS
    }
    sessions_dirs = build_session_dirs(
        config_path=Path(args.config).expanduser(),
        cli_values=cli_values,
        include_defaults=not args.no_default_session_dirs,
    )

    if args.export_monthly:
        try:
            output_path = export_monthly_usage(
                args.export_monthly,
                args.export_format,
                args.output,
                sessions_dirs,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(output_path)
        return

    # Check if any sessions directory exists
    any_exists = any(sessions_dir.exists() for sessions_dir, _, _ in sessions_dirs)
    if not any_exists:
        print("[info] No sessions directories found. No data to display yet.")

    # Start server
    class DashboardServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        daemon_threads = True  # clean shutdown on Ctrl+C

        def server_bind(self):
            # Allow port reuse to avoid "Address already in use" on quick restart
            self.allow_reuse_address = True
            socketserver.TCPServer.server_bind(self)

    httpd = DashboardServer((args.host, args.port), DashboardHandler)
    httpd.session_dirs = sessions_dirs
    print("Cost Dashboard (local agent sessions)")
    print(f"   Serving on: http://{args.host}:{args.port}")
    print("   Data from:")
    for sessions_dir, agent_cmd, source_type in sessions_dirs:
        exists = "[ok]" if sessions_dir.exists() else "[--]"
        print(f"     {exists} {sessions_dir} ({agent_cmd})")
    print("\n   Press Ctrl+C to stop\n")

    # Set a timeout on the socket so we can check for shutdown periodically
    httpd.timeout = 0.5

    try:
        while True:
            httpd.handle_request()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
