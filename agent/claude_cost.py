#!/usr/bin/env python3
import os
import json
import argparse
import re
import sys

from typing import TypedDict
from glob import glob


class CacheCreation(TypedDict):
    ephemeral_5m_input_tokens: int
    ephemeral_1h_input_tokens: int


class Usage(TypedDict):
    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cache_creation: CacheCreation
    output_tokens: int
    service_tier: str


class Cost(TypedDict):
    input: float
    output: float
    cache_read: float
    cache_write: float


COST_MAP: dict[str, Cost] = {
    "claude-opus-4-5-20251101": {
        "input": 5,
        "output": 25,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    # Opus 4.6/4.7/4.8 are priced at the same $5/$25 tier as 4.5 — kept in
    # sync with MANUAL_PRICING in cost_dashboard.py.
    "claude-opus-4-6": {
        "input": 5,
        "output": 25,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-7": {
        "input": 5,
        "output": 25,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-opus-4-8": {
        "input": 5,
        "output": 25,
        "cache_read": 0.5,
        "cache_write": 6.25,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1,
        "output": 5,
        "cache_read": 0.1,
        "cache_write": 1.25,
    },
    "claude-sonnet-4-20250514": {
        "input": 3,
        "output": 15,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3,
        "output": 15,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    # Sonnet has held $3/$15 across 4/4.5/5 so far; verify against Anthropic's
    # published pricing if that changes for a future Sonnet release.
    "claude-sonnet-5": {
        "input": 3,
        "output": 15,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    # Kept in sync with MANUAL_PRICING in cost_dashboard.py — update both when
    # a price changes.
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
}


def _normalize_model_name(name: str) -> str:
    """Strip a trailing YYYYMMDD date stamp and lowercase for fuzzy matching."""
    return re.sub(r"-\d{8}$", "", name.lower())


def match_cost(model: str) -> Cost | None:
    """Look up pricing for a model, falling back to the longest matching
    known model family (date-stamp-agnostic) instead of requiring an exact
    match — an unrecognized dated snapshot of a known model family (e.g. a
    new Sonnet release) should still get priced rather than aborting the
    whole run."""
    if model in COST_MAP:
        return COST_MAP[model]
    norm_model = _normalize_model_name(model)
    best_pattern = None
    for pattern in COST_MAP:
        norm_pattern = _normalize_model_name(pattern)
        if norm_pattern in norm_model or norm_model in norm_pattern:
            if best_pattern is None or len(norm_pattern) > len(
                _normalize_model_name(best_pattern)
            ):
                best_pattern = pattern
    return COST_MAP[best_pattern] if best_pattern else None


def session_cost(path: str) -> tuple[int, float]:
    acc_tokens = 0
    acc_cost = 0.0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f.readlines():
            data: dict = json.loads(line)
            message: dict = data.get("message", {})
            usage: Usage = message.get("usage", {})
            if usage:
                input = usage.get("input_tokens", 0)
                output = usage.get("output_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
                cache_write = usage.get("cache_creation_input_tokens", 0)
                total = input + output + cache_read + cache_write
                model = message.get("model", "")
                assert model, "missing model"
                if model == "<synthetic>":
                    continue
                cost = match_cost(model)
                if cost is None:
                    print(
                        f"warning: missing cost for model {model!r} in {path}, "
                        "counting tokens but treating cost as $0",
                        file=sys.stderr,
                    )
                    acc_tokens += total
                    continue
                input_cost = input * cost["input"]
                output_cost = output * cost["output"]
                cache_read_cost = cache_read * cost["cache_read"]
                cache_write_cost = cache_write * cost["cache_write"]
                total_cost = (
                    input_cost + output_cost + cache_read_cost + cache_write_cost
                )
                acc_tokens += total
                acc_cost += total_cost
    acc_cost /= 1e6
    return acc_tokens, acc_cost


def main():
    parser = argparse.ArgumentParser("Claude code cost calculator")
    parser.add_argument(
        "path", help="Path to folder of claude sessions or single jsonl"
    )
    args = parser.parse_args()
    path = args.path
    files = []
    if os.path.isdir(path):
        files = list(glob(os.path.join(path, "**/*.jsonl"), recursive=True))
        files.sort()
        if not files:
            assert False, "no sessions found"
    elif os.path.isfile(path):
        files = [path]
    else:
        assert False, "bad"
    acc_tokens = 0
    acc_cost = 0.0
    for file in files:
        if not os.path.exists(file):
            assert False, "badad"
        tokens, cost = session_cost(file)
        if tokens == 0:
            assert cost == 0.0, "unexpected cost"
            continue
        print(file)
        print(f"  Tokens: {tokens}")
        print(f"    Cost: ${cost:.2f}")
        acc_tokens += tokens
        acc_cost += cost

    if len(files) > 1:
        print("\n===\n")
        print(f"Total tokens: {acc_tokens}")
        print(f"  Total cost: ${acc_cost:.2f}")


if __name__ == "__main__":
    main()
