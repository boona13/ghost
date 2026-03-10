"""Concurrency tests for per-thread state isolation.

Proves that simultaneous invocations on the same MiddlewareChain,
ToolLoopDebugLogger, and EvolveContextLogger do not cross-contaminate.
"""

from __future__ import annotations

import threading
import time
import types
from unittest.mock import MagicMock

import pytest

from ghost_middleware import InvocationContext, Middleware, MiddlewareChain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(source="test", **kw) -> InvocationContext:
    return InvocationContext(source=source, **kw)


def _fake_engine(text="done", delay=0):
    """Mock engine whose run() can sleep to simulate real work."""
    result = types.SimpleNamespace(text=text, tool_calls=[], total_tokens=50)
    engine = MagicMock()

    def _run(**kwargs):
        if delay:
            time.sleep(delay)
        return result

    engine.run.side_effect = _run
    return engine


def _fake_daemon(identity="Ghost"):
    d = MagicMock()
    d._build_identity_context.return_value = identity
    d._resolve_skill_model.return_value = None
    d.hooks = MagicMock()
    d.tool_intent_security = MagicMock()
    d.tool_event_bus = MagicMock()
    d.skill_loader = MagicMock()
    d.skill_loader.match.return_value = []
    d.skill_loader.build_skills_prompt.return_value = ""
    d.skill_loader.get_tools_for_skills.return_value = []
    d.skill_loader.check_reload.return_value = None
    d._cleanup_browser_after_task = MagicMock()
    return d


# ---------------------------------------------------------------------------
# MiddlewareChain._active_ctx thread isolation
# ---------------------------------------------------------------------------


class TestMiddlewareChainThreadIsolation:
    """Verify _active_ctx is per-thread, not shared."""

    def test_active_ctx_isolated_between_threads(self):
        """Two threads setting _active_ctx on the same chain don't interfere."""
        chain = MiddlewareChain()
        results = {}
        barrier = threading.Barrier(2)

        def worker(name):
            ctx = _make_ctx(source=name)
            chain._active_ctx = ctx
            barrier.wait()  # both threads set at the same time
            time.sleep(0.05)
            results[name] = chain._active_ctx

        t1 = threading.Thread(target=worker, args=("thread-A",))
        t2 = threading.Thread(target=worker, args=("thread-B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["thread-A"].source == "thread-A"
        assert results["thread-B"].source == "thread-B"

    def test_active_ctx_none_in_unset_thread(self):
        """A thread that never set _active_ctx sees None."""
        chain = MiddlewareChain()
        chain._active_ctx = _make_ctx(source="main")
        result = {}

        def worker():
            result["ctx"] = chain._active_ctx

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert result["ctx"] is None
        assert chain._active_ctx.source == "main"

    def test_per_step_hooks_see_correct_ctx(self):
        """before_model/after_model use the calling thread's ctx."""
        chain = MiddlewareChain()
        seen = {}

        class SpyMiddleware(Middleware):
            def before_model(self, ctx, messages, step):
                seen[threading.current_thread().name] = (
                    ctx.source if ctx else "NO_CTX"
                )
                return messages

        chain.add(SpyMiddleware())

        barrier = threading.Barrier(2)

        def worker(name):
            ctx = _make_ctx(source=name)
            chain._active_ctx = ctx
            barrier.wait()
            chain.before_model([], 0)

        t1 = threading.Thread(target=worker, args=("worker-1",), name="w1")
        t2 = threading.Thread(target=worker, args=("worker-2",), name="w2")
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert seen["w1"] == "worker-1"
        assert seen["w2"] == "worker-2"

    def test_concurrent_invoke_isolation(self):
        """Two concurrent invoke() calls don't clobber each other's ctx."""
        seen_sources = []

        class RecordingMiddleware(Middleware):
            def before_invoke(self, ctx):
                time.sleep(0.02)
                seen_sources.append(ctx.source)

            def after_invoke(self, ctx):
                seen_sources.append(ctx.source)

        chain = MiddlewareChain([RecordingMiddleware()])

        def run_invoke(source, delay):
            engine = _fake_engine(text=f"result-{source}", delay=delay)
            daemon = _fake_daemon()
            ctx = _make_ctx(
                source=source,
                engine=engine,
                daemon=daemon,
                config={},
                user_message="test",
            )
            chain.invoke(ctx)

        t1 = threading.Thread(target=run_invoke, args=("alpha", 0.05))
        t2 = threading.Thread(target=run_invoke, args=("beta", 0.05))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        alpha_count = seen_sources.count("alpha")
        beta_count = seen_sources.count("beta")
        assert alpha_count == 2  # before + after
        assert beta_count == 2


# ---------------------------------------------------------------------------
# ToolLoopDebugLogger thread isolation
# ---------------------------------------------------------------------------


class TestDebugLoggerThreadIsolation:

    def test_session_id_isolated_between_threads(self):
        """Two threads calling session_start get independent session_ids."""
        from ghost_loop import ToolLoopDebugLogger

        logger = ToolLoopDebugLogger()
        results = {}
        barrier = threading.Barrier(2)

        def worker(name):
            logger.session_start(name, "model", 10, name)
            sid = logger._session_id
            barrier.wait()
            time.sleep(0.02)
            results[name] = logger._session_id

        t1 = threading.Thread(target=worker, args=("thread-A",))
        t2 = threading.Thread(target=worker, args=("thread-B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["thread-A"] != results["thread-B"]
        assert results["thread-A"] is not None
        assert results["thread-B"] is not None

    def test_session_start_not_visible_from_other_thread(self):
        """A thread that never called session_start sees None."""
        from ghost_loop import ToolLoopDebugLogger

        logger = ToolLoopDebugLogger()
        logger.session_start("main", "model", 10)
        result = {}

        def worker():
            result["sid"] = logger._session_id

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert result["sid"] is None
        assert logger._session_id is not None


# ---------------------------------------------------------------------------
# EvolveContextLogger thread isolation
# ---------------------------------------------------------------------------


class TestCtxLoggerThreadIsolation:

    def test_feature_id_isolated_between_threads(self):
        """Two threads calling set_feature get independent values."""
        from ghost_loop import EvolveContextLogger

        logger = EvolveContextLogger()
        results = {}
        barrier = threading.Barrier(2)

        def worker(name, fid):
            logger.set_feature(fid, f"title-{name}")
            logger.set_session(f"session-{name}", name)
            barrier.wait()
            time.sleep(0.02)
            results[name] = {
                "feature_id": logger._feature_id,
                "session_id": logger._session_id,
                "caller": logger._caller,
            }

        t1 = threading.Thread(target=worker, args=("A", "feat-aaa"))
        t2 = threading.Thread(target=worker, args=("B", "feat-bbb"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["A"]["feature_id"] == "feat-aaa"
        assert results["B"]["feature_id"] == "feat-bbb"
        assert results["A"]["session_id"] == "session-A"
        assert results["B"]["session_id"] == "session-B"

    def test_clear_only_affects_calling_thread(self):
        """clear() on one thread doesn't affect another."""
        from ghost_loop import EvolveContextLogger

        logger = EvolveContextLogger()
        logger.set_feature("feat-main", "Main Feature")
        result = {}
        barrier = threading.Barrier(2)

        def worker_clear():
            logger.set_feature("feat-worker", "Worker")
            barrier.wait()
            logger.clear()
            result["worker_after_clear"] = logger._feature_id

        def worker_keep():
            logger.set_feature("feat-keeper", "Keeper")
            barrier.wait()
            time.sleep(0.05)
            result["keeper_after_other_clear"] = logger._feature_id

        t1 = threading.Thread(target=worker_clear)
        t2 = threading.Thread(target=worker_keep)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert result["worker_after_clear"] == ""
        assert result["keeper_after_other_clear"] == "feat-keeper"

    def test_base_dict_uses_thread_local_values(self):
        """_base() returns values from the calling thread."""
        from ghost_loop import EvolveContextLogger

        logger = EvolveContextLogger()
        results = {}
        barrier = threading.Barrier(2)

        def worker(name):
            logger.set_feature(f"feat-{name}", f"title-{name}")
            logger.set_session(f"sess-{name}", name)
            barrier.wait()
            results[name] = logger._base()

        t1 = threading.Thread(target=worker, args=("X",))
        t2 = threading.Thread(target=worker, args=("Y",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["X"]["feature_id"] == "feat-X"
        assert results["Y"]["feature_id"] == "feat-Y"
        assert results["X"]["session_id"] == "sess-X"
        assert results["Y"]["session_id"] == "sess-Y"


# ---------------------------------------------------------------------------
# RunContext isolation (each run() gets its own)
# ---------------------------------------------------------------------------


class TestRunContextIsolation:

    def test_run_context_fields_independent(self):
        """Two RunContext instances don't share state."""
        from ghost_loop import RunContext

        a = RunContext(session_id="a")
        b = RunContext(session_id="b")

        a.compaction_count = 5
        a.consecutive_empty = 3
        a.malformed_json_count = 2

        assert b.compaction_count == 0
        assert b.consecutive_empty == 0
        assert b.malformed_json_count == 0

    def test_run_context_defaults(self):
        from ghost_loop import RunContext

        rc = RunContext()
        assert rc.session_id == ""
        assert rc.compaction_count == 0
        assert rc.consecutive_text_only == 0
        assert rc.consecutive_empty == 0
        assert rc.malformed_json_count == 0
        assert rc.critical_blocks == 0


# ---------------------------------------------------------------------------
# Stress test: many threads hitting the same chain
# ---------------------------------------------------------------------------


class TestStressConcurrency:

    def test_many_threads_no_ctx_leakage(self):
        """8 threads concurrently invoking before_model see their own ctx."""
        chain = MiddlewareChain()
        seen = {}
        num_threads = 8
        barrier = threading.Barrier(num_threads)

        class RecordCtxMiddleware(Middleware):
            def before_model(self, ctx, messages, step):
                tid = threading.current_thread().name
                seen[tid] = ctx.source if ctx else "NONE"
                return messages

        chain.add(RecordCtxMiddleware())

        def worker(idx):
            name = f"t-{idx}"
            ctx = _make_ctx(source=name)
            chain._active_ctx = ctx
            barrier.wait()
            chain.before_model([], 0)

        threads = [
            threading.Thread(target=worker, args=(i,), name=f"t-{i}")
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(num_threads):
            assert seen[f"t-{i}"] == f"t-{i}", f"Thread t-{i} saw wrong ctx"

    def test_many_threads_debug_logger(self):
        """8 threads concurrently using the debug logger get unique sessions."""
        from ghost_loop import ToolLoopDebugLogger

        logger = ToolLoopDebugLogger()
        session_ids = {}
        num_threads = 8
        barrier = threading.Barrier(num_threads)

        def worker(idx):
            name = f"worker-{idx}"
            logger.session_start(name, "model", 10, name)
            barrier.wait()
            time.sleep(0.01)
            session_ids[name] = logger._session_id

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        unique_ids = set(session_ids.values())
        assert len(unique_ids) == num_threads, (
            f"Expected {num_threads} unique session IDs, got {len(unique_ids)}"
        )
