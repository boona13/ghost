import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

import ghost_code_index
from ghost_code_index import CodeIndex
from ghost_memory import MemoryDB, STALE_MEMORY_PURGE_THRESHOLD


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


if __name__ == "__main__":
    unittest.main()
