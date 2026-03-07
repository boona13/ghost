import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import ghost_code_index
from ghost_code_index import CodeIndex
from ghost_autonomy import (
    _active_evolution_ready_for_verify,
    _extract_evolution_id_from_scratch_text,
    _latest_test_passed_after_last_change,
    _phase_wrote_scratch_file,
    _resolve_verify_scratch_path,
)
from ghost_code_tools import (
    PROJECT_DIR as CODE_TOOLS_PROJECT_DIR,
    _resolve_search_path,
    build_code_search_tools,
)
from ghost_evolve import EvolutionEngine
from ghost_loop import _check_incomplete_workflows
from ghost_memory import MemoryDB, STALE_MEMORY_PURGE_THRESHOLD
from ghost_tools import _normalize_ghost_repo_path


def _write(path, content):
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


class EnhancementGapTests(unittest.TestCase):
    def test_code_index_nested_lookup_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            stats_path = tmp_path / "code_index_lookup_stats.json"

            _write(
                tmp_path / "ghost_alpha.py",
                """
                import ghost_beta

                def helper_blob() -> str:
                    return "alpha-" + "-".join([
                        "one", "two", "three", "four", "five", "six", "seven",
                        "eight", "nine", "ten", "eleven", "twelve", "thirteen",
                        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                        "nineteen", "twenty",
                    ])

                class Outer:
                    class Inner:
                        def method(self, value: int) -> int:
                            return value + 1
                """,
            )
            _write(
                tmp_path / "ghost_beta.py",
                """
                from ghost_alpha import Outer

                def use_outer() -> int:
                    return Outer.Inner().method(3)
                """,
            )

            with patch.object(ghost_code_index, "LOOKUP_STATS_PATH", stats_path):
                idx = CodeIndex(project_dir=tmp_path)
                idx.build(force=True)

                nested_source = idx.lookup_symbol("Outer.Inner.method")
                self.assertIsNotNone(nested_source)
                self.assertIn("def method(self, value: int) -> int:", nested_source)

                nested_symbol = next(
                    sym for sym in idx._all_symbols if sym.qualified_name == "Outer.Inner.method"
                )
                stable_source = idx.lookup_symbol(nested_symbol.symbol_id)
                self.assertIsNotNone(stable_source)
                self.assertIn(nested_symbol.symbol_id, stable_source)

                repo_map = idx.generate_repo_map()
                self.assertIn("class Outer:", repo_map)
                self.assertIn("class Inner:", repo_map)
                self.assertIn("def method(value: int) -> int", repo_map)

                stats = json.loads(stats_path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(stats["lookups"], 2)
                self.assertGreater(stats["estimated_tokens_saved"], 0)

    def test_memory_search_verified_purges_repeatedly_stale_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = MemoryDB(db_path=Path(tmp_dir) / "memory.db")
            db.save(
                content="Nested lookup bug fix note",
                type="note",
                citations='[{"file": "missing_module.py", "line": 1, "snippet": "class Missing:"}]',
            )

            for _ in range(STALE_MEMORY_PURGE_THRESHOLD - 1):
                results = db.search_verified("nested lookup")
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0]["_citation_valid"])
                self.assertIn("[STALE:", results[0]["_citation_status"])

            self.assertEqual(db.count(), 1)
            self.assertEqual(db.search_verified("nested lookup"), [])
            self.assertEqual(db.count(), 0)

    def test_recent_memories_include_citation_status_when_verified(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = MemoryDB(db_path=Path(tmp_dir) / "memory.db")
            db.save(
                content="Memory verification status should be exposed",
                type="note",
                citations='[{"file": "ghost_memory.py", "line": 1, "snippet": "\\"\\"\\""}]',
            )

            results = db.get_recent(limit=5, verify=True)
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0]["_citation_valid"])
            self.assertEqual(results[0]["_citation_status"], " [VERIFIED]")

    def test_latest_test_must_pass_after_last_change(self):
        self.assertTrue(
            _latest_test_passed_after_last_change([
                {"tool": "evolve_apply", "step": 1, "result": "Applied"},
                {"tool": "evolve_test", "step": 2, "result": "Tests PASSED"},
            ])
        )
        self.assertFalse(
            _latest_test_passed_after_last_change([
                {"tool": "evolve_apply", "step": 1, "result": "Applied"},
                {"tool": "evolve_test", "step": 2, "result": "Tests PASSED"},
                {"tool": "evolve_apply", "step": 3, "result": "Applied again"},
            ])
        )
        self.assertFalse(
            _latest_test_passed_after_last_change([
                {"tool": "evolve_apply", "step": 1, "result": "Applied"},
                {"tool": "evolve_test", "step": 2, "result": "Tests FAILED"},
            ])
        )

    def test_verify_readiness_requires_active_tested_pass_evolution(self):
        fake_engine = type("FakeEngine", (), {
            "_active_evolutions": {
                "abc12345": {"status": "tested_pass", "test_results": {"passed": True}},
                "def67890": {"status": "approved", "test_results": None},
            }
        })()

        with patch("ghost_evolve.get_engine", return_value=fake_engine):
            ready, reason = _active_evolution_ready_for_verify("abc12345")
            self.assertTrue(ready)
            self.assertEqual(reason, "")

            ready, reason = _active_evolution_ready_for_verify("def67890")
            self.assertFalse(ready)
            self.assertIn("not verify-ready", reason)

    def test_extract_evolution_id_from_scratch_text(self):
        scratch = """
        ## Phase 2 Results
        **Evolution ID:** 7846805b725d
        """
        self.assertEqual(_extract_evolution_id_from_scratch_text(scratch), "7846805b725d")

        scratch = """
        ## Phase 2 Results
        **evolution_id:** 4f59135743ec
        """
        self.assertEqual(_extract_evolution_id_from_scratch_text(scratch), "4f59135743ec")

    def test_new_changes_invalidate_prior_test_results(self):
        evo = {"approved": True, "status": "tested_pass", "test_results": {"passed": True}}
        EvolutionEngine._invalidate_test_state(evo)
        self.assertEqual(evo["status"], "approved")
        self.assertIsNone(evo["test_results"])

    def test_incomplete_workflow_respects_phase_toolset(self):
        implement_tools = {"evolve_plan", "evolve_apply", "evolve_test", "file_write", "task_complete"}
        self.assertIsNone(
            _check_incomplete_workflows(
                [
                    {"tool": "evolve_plan"},
                    {"tool": "evolve_apply"},
                    {"tool": "evolve_test", "result": "Tests PASSED"},
                ],
                implement_tools,
            )
        )

        scout_tools = {"start_future_feature", "file_write", "task_complete"}
        self.assertIsNone(
            _check_incomplete_workflows(
                [
                    {"tool": "start_future_feature"},
                    {"tool": "file_write"},
                ],
                scout_tools,
            )
        )

        self.assertIn(
            "never called evolve_submit_pr",
            _check_incomplete_workflows(
                [
                    {"tool": "evolve_plan"},
                    {"tool": "evolve_apply"},
                    {"tool": "evolve_test", "result": "Tests PASSED"},
                ],
                {"evolve_plan", "evolve_apply", "evolve_test", "evolve_submit_pr", "task_complete"},
            ) or "",
        )

    def test_resolve_search_path_falls_back_from_stale_ghost_checkout(self):
        resolved = _resolve_search_path("/Users/ibrahimboona/Desktop/Ghost-0.5")
        self.assertEqual(resolved, CODE_TOOLS_PROJECT_DIR)

        resolved = _resolve_search_path("/Users/ibrahimboona/Ghost")
        self.assertEqual(resolved, CODE_TOOLS_PROJECT_DIR)

    def test_phase_wrote_expected_scratch_file(self):
        scratch_path = Path("/tmp/example-scratch.md")
        self.assertTrue(
            _phase_wrote_scratch_file(
                [
                    {
                        "tool": "file_write",
                        "args": {"path": str(scratch_path)},
                        "result": f"OK: wrote 42 chars to {scratch_path}",
                    }
                ],
                scratch_path,
            )
        )
        self.assertFalse(
            _phase_wrote_scratch_file(
                [
                    {
                        "tool": "file_write",
                        "args": {"path": str(scratch_path)},
                        "result": "Tool error (file_write): MALFORMED JSON",
                    }
                ],
                scratch_path,
            )
        )

    def test_mirrored_ghost_tool_paths_map_back_to_repo(self):
        mirrored = Path.home() / ".ghost" / "ghost_tools" / "regex_tool" / "tool.py"
        expected = CODE_TOOLS_PROJECT_DIR / "ghost_tools" / "regex_tool" / "tool.py"
        self.assertEqual(_normalize_ghost_repo_path(str(mirrored)), expected)
        self.assertEqual(_resolve_search_path(str(mirrored)), expected)

    def test_root_ghost_source_paths_map_back_to_repo(self):
        mirrored = Path.home() / ".ghost" / "ghost_evolve.py"
        expected = CODE_TOOLS_PROJECT_DIR / "ghost_evolve.py"
        self.assertEqual(_normalize_ghost_repo_path(str(mirrored)), expected)
        self.assertEqual(_resolve_search_path(str(mirrored)), expected)

    def test_stale_absolute_checkout_paths_map_back_to_repo(self):
        stale = "/Users/ibrahimboona/Ghost/ghost_tools/file_hasher/tool.py"
        expected = CODE_TOOLS_PROJECT_DIR / "ghost_tools" / "file_hasher" / "tool.py"
        self.assertEqual(_normalize_ghost_repo_path(stale), expected)

    def test_grep_accepts_path_to_search_alias(self):
        grep_tool = next(tool for tool in build_code_search_tools() if tool["name"] == "grep")
        result = grep_tool["execute"](
            pattern="def submit_pr",
            path_to_search=str(CODE_TOOLS_PROJECT_DIR / "ghost_evolve.py"),
        )
        self.assertIn("ghost_evolve.py", result)

    def test_verify_prefers_feature_specific_scratch_with_evolution_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            scratch_dir = Path(tmp_dir)
            auto = scratch_dir / "auto.md"
            feature = scratch_dir / "0492615b0b.md"
            auto.write_text("## Feature\n- feature_id: 0492615b0b\n", encoding="utf-8")
            feature.write_text("## Phase 2 Results\n**Evolution ID:** 6013245cc680\n", encoding="utf-8")

            with patch("ghost_autonomy.SCRATCH_DIR", scratch_dir):
                resolved_path, content = _resolve_verify_scratch_path("0492615b0b", auto)

            self.assertEqual(resolved_path, feature)
            self.assertIn("6013245cc680", content)


if __name__ == "__main__":
    unittest.main()
