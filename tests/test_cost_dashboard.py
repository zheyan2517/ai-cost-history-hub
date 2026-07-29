from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

import cost_dashboard as dashboard  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures"


class ParserAndPricingTests(unittest.TestCase):
    def test_claude_parser_keeps_known_and_unknown_pricing(self):
        stats = dashboard.analyze_claude_jsonl_file(
            FIXTURES / "claude" / "session.jsonl"
        )

        self.assertEqual(stats["messages"], 2)
        self.assertEqual(stats["input_tokens"], 1300)
        self.assertEqual(stats["output_tokens"], 240)
        self.assertEqual(stats["cache_read_tokens"], 50)
        self.assertEqual(stats["cache_write_tokens"], 25)
        self.assertEqual(len(stats["llm_events"]), 2)
        self.assertEqual(
            stats["llm_events"][0]["pricing_status"], "estimated"
        )
        self.assertEqual(stats["llm_events"][1]["pricing_status"], "unknown")
        self.assertGreater(stats["cost_total"], 0)

    def test_codex_parser_deduplicates_token_count_events(self):
        stats = dashboard.analyze_codex_jsonl_file(
            FIXTURES / "codex" / "session.jsonl"
        )

        self.assertEqual(stats["messages"], 3)
        self.assertEqual(stats["total_tokens"], 247)
        self.assertEqual(stats["input_tokens"], 148)
        self.assertEqual(stats["output_tokens"], 54)
        self.assertEqual(stats["cache_read_tokens"], 32)
        self.assertEqual(stats["reasoning_tokens"], 14)
        self.assertEqual(len(stats["llm_events"]), 3)
        self.assertEqual(
            [event["pricing_status"] for event in stats["llm_events"]],
            ["estimated", "estimated", "unknown"],
        )

    def test_gemini_parser_handles_cache_and_bad_lines(self):
        stats = dashboard.analyze_gemini_jsonl_file(
            FIXTURES / "gemini" / "project" / "chats" / "session.jsonl"
        )

        self.assertEqual(stats["messages"], 2)
        self.assertEqual(stats["input_tokens"], 1010)
        self.assertEqual(stats["output_tokens"], 105)
        self.assertEqual(stats["cache_read_tokens"], 200)
        self.assertEqual(stats["cache_write_tokens"], 10)
        self.assertEqual(stats["cwd"], "/fixtures/gemini-project")
        self.assertEqual(stats["llm_events"][1]["pricing_status"], "unknown")

    def test_pricing_status_and_unknown_model(self):
        known = dashboard.price_model(
            "anthropic/claude-sonnet-4-20250514", 1_000_000, 0, 0
        )
        unknown = dashboard.price_model("model-without-a-price", 1_000_000, 0, 0)

        self.assertEqual(known["status"], "estimated")
        self.assertEqual(known["cost"], 3.0)
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(
            dashboard.get_manual_cost("model-without-a-price", 1_000_000, 0, 0),
            0.0,
        )

    def test_pricing_table_has_nonnegative_rates(self):
        self.assertGreater(len(dashboard.MANUAL_PRICING), 0)
        for pattern, record in dashboard.MANUAL_PRICING.items():
            for field in ("input", "output", "cache_read", "cache_write"):
                self.assertGreaterEqual(float(record.get(field, 0)), 0, pattern)

    def test_all_provider_parsers_tolerate_bad_lines_and_unknown_models(self):
        cases = (
            (
                "claude",
                FIXTURES / "claude" / "session.jsonl",
                dashboard.analyze_claude_jsonl_file,
                "C:\\fixtures\\project",
            ),
            (
                "codex",
                FIXTURES / "codex" / "session.jsonl",
                dashboard.analyze_codex_jsonl_file,
                "/fixtures/project",
            ),
            (
                "gemini",
                FIXTURES / "gemini" / "project" / "chats" / "session.jsonl",
                dashboard.analyze_gemini_jsonl_file,
                "/fixtures/gemini-project",
            ),
            (
                "pi",
                FIXTURES / "pi" / "project" / "session.jsonl",
                dashboard.analyze_jsonl_file,
                "/fixtures/pi-project",
            ),
        )

        for agent, path, parser, expected_cwd in cases:
            with self.subTest(agent=agent):
                stats = parser(path)
                self.assertGreater(stats["messages"], 0)
                self.assertEqual(stats["cwd"], expected_cwd)
                unknown_events = [
                    event
                    for event in stats["llm_events"]
                    if event["pricing_status"] == "unknown"
                ]
                self.assertEqual(len(unknown_events), 1)
                self.assertGreater(unknown_events[0]["total_tokens"], 0)


class DirectoryAndExportTests(unittest.TestCase):
    def test_custom_directories_are_repeatable_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {"sessionDirs": {"pi": ["relative-pi", "relative-pi"]}}
                ),
                encoding="utf-8",
            )
            cli_pi = Path(temp_dir) / "cli-pi"
            dirs = dashboard.build_session_dirs(
                config_path=config_path,
                cli_values={
                    "pi-dir": [str(cli_pi), str(cli_pi)],
                    "codex-dir": [],
                },
                include_defaults=False,
            )

        self.assertEqual(len(dirs), 2)
        self.assertEqual(dirs[0][1:], ("pi", "standard"))
        self.assertEqual(dirs[1][1:], ("pi", "standard"))
        self.assertTrue(str(dirs[0][0]).endswith("relative-pi"))
        self.assertEqual(dirs[1][0], cli_pi.resolve())

    def test_monthly_exports_include_one_row_per_llm_call(self):
        source_dirs = [
            (FIXTURES / "pi", "pi", "standard"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = dashboard.export_monthly_usage(
                "2026-07", "csv", temp_path / "usage.csv", source_dirs
            )
            json_path = dashboard.export_monthly_usage(
                "2026-07", "json", temp_path / "usage.json", source_dirs
            )

            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["agent"], "pi")
        self.assertEqual(rows[0]["model"], "claude-sonnet-4")
        self.assertEqual(rows[0]["pricing_status"], "estimated")
        self.assertNotIn("price_provider", rows[0])
        self.assertEqual(rows[1]["pricing_status"], "unknown")
        self.assertEqual(rows[1]["estimated_cost_usd"], "")
        self.assertEqual(payload["event_count"], 2)
        self.assertEqual(payload["events"][0]["output_tokens"], 20)
        self.assertIsNone(payload["events"][1]["estimated_cost_usd"])

    def test_multiple_custom_directories_are_aggregated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dirs = []
            fixture_text = (
                FIXTURES / "pi" / "project" / "session.jsonl"
            ).read_text(encoding="utf-8")
            for name in ("first", "second"):
                project_dir = root / name / "project"
                project_dir.mkdir(parents=True)
                (project_dir / "session.jsonl").write_text(
                    fixture_text, encoding="utf-8"
                )
                source_dirs.append((root / name, "pi", "standard"))

            projects, global_stats = dashboard.collect_all_stats(source_dirs)

        self.assertEqual(len(projects), 2)
        self.assertEqual(global_stats["total_projects"], 2)
        self.assertEqual(global_stats["total_sessions"], 2)
        self.assertEqual(global_stats["total_messages"], 4)

    def test_browser_payload_does_not_contain_session_paths_for_any_provider(self):
        source_dirs = [
            (FIXTURES / "claude", "claude", "claude"),
            (FIXTURES / "codex", "codex", "codex"),
            (FIXTURES / "gemini", "gemini", "gemini"),
            (FIXTURES / "pi", "pi", "standard"),
        ]
        html = dashboard.generate_html(source_dirs)

        for source_dir in ("claude", "codex", "gemini", "pi"):
            self.assertNotIn(str((FIXTURES / source_dir).resolve()), html)
        for fake_cwd in (
            "C:\\fixtures\\project",
            "/fixtures/project",
            "/fixtures/gemini-project",
            "/fixtures/pi-project",
        ):
            self.assertNotIn(fake_cwd, html)
        self.assertIn("data-resume-uid", html)
        self.assertIn("/resume?uid=", html)
        self.assertTrue(dashboard.SESSION_REGISTRY)


if __name__ == "__main__":
    unittest.main()
