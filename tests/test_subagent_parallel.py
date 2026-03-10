"""Tests for the parallel subagent executor, auto-collect, and related tools.

Covers:
  - _run_subagent_sync with explicit IDs
  - execute_subagent_async: background execution, task registration
  - wait_for_tasks: success, timeout, unknown IDs
  - check_task / wait_tasks_tool: tool wrappers
  - task() tool: async submission, correct return format
  - Parallel execution: multiple tasks run concurrently
  - SubagentLimitMiddleware: enforces cap on task + delegate_task
  - Engine auto-collect: parses task_ids from tool_calls_log
  - SSE event emission
"""

import json
import re
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghost_subagent_config import (
    SubagentConfig,
    SubagentResult,
    SubagentStatus,
    _run_subagent_sync,
    execute_subagent_async,
    wait_for_tasks,
    get_background_task_result,
    list_background_tasks,
    _background_tasks,
    _background_tasks_lock,
    _format_subagent_result,
    build_typed_subagent_tools,
    BUILTIN_SUBAGENTS,
)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> SubagentConfig:
    defaults = dict(
        name="test_agent",
        description="Test subagent",
        system_prompt="You are a test agent.",
        tools=None,
        disallowed_tools=[],
        model="test-model",
        max_steps=5,
        timeout_seconds=30,
        max_result_chars=500,
    )
    defaults.update(overrides)
    return SubagentConfig(**defaults)


class FakeToolRegistry:
    """Minimal tool registry stub."""
    def names(self):
        return ["read_file", "shell_exec"]
    def subset(self, names):
        return self
    def execute(self, name, args):
        return f"executed {name}"
    def to_openai_schema(self):
        return []


class FakeLoopResult:
    def __init__(self, text="done", steps=3, total_tokens=100):
        self.text = text
        self.steps = steps
        self.total_tokens = total_tokens


def _clear_background_tasks():
    with _background_tasks_lock:
        _background_tasks.clear()


# ---------------------------------------------------------------------------
#  1. _run_subagent_sync
# ---------------------------------------------------------------------------

class TestRunSubagentSync:
    def setup_method(self):
        _clear_background_tasks()

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("ghost_loop.ToolLoopEngine")
    def test_uses_explicit_ids(self, MockEngine):
        mock_engine = MagicMock()
        mock_engine.run.return_value = FakeLoopResult("result text")
        MockEngine.return_value = mock_engine

        config = _make_config()
        result = _run_subagent_sync(
            config=config,
            task_text="do stuff",
            tool_registry=FakeToolRegistry(),
            cfg={"model": "test"},
            task_id="MY_ID",
            trace_id="MY_TRACE",
        )
        assert result.task_id == "MY_ID"
        assert result.trace_id == "MY_TRACE"
        assert result.status == SubagentStatus.COMPLETED
        assert result.result == "result text"

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("ghost_loop.ToolLoopEngine")
    def test_generates_ids_when_not_provided(self, MockEngine):
        mock_engine = MagicMock()
        mock_engine.run.return_value = FakeLoopResult()
        MockEngine.return_value = mock_engine

        result = _run_subagent_sync(
            config=_make_config(),
            task_text="do stuff",
            tool_registry=FakeToolRegistry(),
            cfg={},
        )
        assert len(result.task_id) == 8
        assert len(result.trace_id) == 8

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("ghost_loop.ToolLoopEngine")
    def test_failure_populates_error(self, MockEngine):
        mock_engine = MagicMock()
        mock_engine.run.side_effect = RuntimeError("boom")
        MockEngine.return_value = mock_engine

        result = _run_subagent_sync(
            config=_make_config(),
            task_text="fail",
            tool_registry=FakeToolRegistry(),
            cfg={},
        )
        assert result.status == SubagentStatus.FAILED
        assert "boom" in result.error

    def test_no_api_key_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _run_subagent_sync(
                config=_make_config(),
                task_text="no key",
                tool_registry=FakeToolRegistry(),
                cfg={},
                auth_store=None,
            )
            assert result.status == SubagentStatus.FAILED
            assert "API key" in result.error

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("ghost_loop.ToolLoopEngine")
    def test_emits_sse_events(self, MockEngine):
        mock_engine = MagicMock()
        mock_engine.run.return_value = FakeLoopResult()
        MockEngine.return_value = mock_engine

        bus = MagicMock()
        result = _run_subagent_sync(
            config=_make_config(),
            task_text="work",
            tool_registry=FakeToolRegistry(),
            cfg={"model": "test"},
            event_bus=bus,
            task_id="EV_ID",
        )
        assert result.status == SubagentStatus.COMPLETED
        calls = [c[0][0] for c in bus.emit.call_args_list]
        assert "on_subagent_started" in calls
        assert "on_subagent_completed" in calls

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("ghost_loop.ToolLoopEngine")
    def test_emits_failed_event_on_error(self, MockEngine):
        mock_engine = MagicMock()
        mock_engine.run.side_effect = ValueError("oops")
        MockEngine.return_value = mock_engine

        bus = MagicMock()
        result = _run_subagent_sync(
            config=_make_config(),
            task_text="crash",
            tool_registry=FakeToolRegistry(),
            cfg={"model": "test"},
            event_bus=bus,
        )
        assert result.status == SubagentStatus.FAILED
        calls = [c[0][0] for c in bus.emit.call_args_list]
        assert "on_subagent_started" in calls
        assert "on_subagent_failed" in calls


# ---------------------------------------------------------------------------
#  2. execute_subagent_async
# ---------------------------------------------------------------------------

class TestExecuteSubagentAsync:
    def setup_method(self):
        _clear_background_tasks()

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_returns_task_id_and_future(self, mock_sync):
        fake_sr = SubagentResult(
            task_id="overwritten",
            trace_id="overwritten",
            subagent_type="test_agent",
            status=SubagentStatus.COMPLETED,
            result="done",
        )
        mock_sync.return_value = fake_sr

        task_id, future = execute_subagent_async(
            config=_make_config(),
            task_text="async work",
            tool_registry=FakeToolRegistry(),
            cfg={},
        )
        assert isinstance(task_id, str) and len(task_id) == 8
        assert isinstance(future, Future)

        result = future.result(timeout=10)
        assert result.status == SubagentStatus.COMPLETED

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_registers_in_background_tasks(self, mock_sync):
        fake_sr = SubagentResult(
            task_id="x", trace_id="x",
            subagent_type="test_agent",
            status=SubagentStatus.COMPLETED,
            result="ok",
        )
        mock_sync.return_value = fake_sr

        task_id, future = execute_subagent_async(
            config=_make_config(),
            task_text="track me",
            tool_registry=FakeToolRegistry(),
            cfg={},
        )
        # Should be registered immediately as RUNNING
        sr = get_background_task_result(task_id)
        assert sr is not None
        assert sr.status == SubagentStatus.RUNNING

        # After completion
        future.result(timeout=10)
        time.sleep(0.1)  # give _run_and_track a moment to update
        sr = get_background_task_result(task_id)
        assert sr.status == SubagentStatus.COMPLETED

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_passes_task_id_and_trace_id_to_sync(self, mock_sync):
        """Verify the external IDs are passed through, not generated internally."""
        fake_sr = SubagentResult(
            task_id="x", trace_id="x",
            subagent_type="test_agent",
            status=SubagentStatus.COMPLETED,
            result="ok",
        )
        mock_sync.return_value = fake_sr

        task_id, future = execute_subagent_async(
            config=_make_config(),
            task_text="track IDs",
            tool_registry=FakeToolRegistry(),
            cfg={},
        )
        future.result(timeout=10)

        call_kwargs = mock_sync.call_args
        assert call_kwargs[1]["task_id"] == task_id


# ---------------------------------------------------------------------------
#  3. wait_for_tasks
# ---------------------------------------------------------------------------

class TestWaitForTasks:
    def setup_method(self):
        _clear_background_tasks()

    def test_success(self):
        with _background_tasks_lock:
            _background_tasks["t1"] = SubagentResult(
                task_id="t1", trace_id="tr1",
                subagent_type="test",
                status=SubagentStatus.COMPLETED,
                result="answer",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
        results = wait_for_tasks(["t1"], timeout=5)
        assert results["t1"]["success"] is True
        assert results["t1"]["result"] == "answer"

    def test_unknown_task_id(self):
        results = wait_for_tasks(["nonexistent"], timeout=1)
        assert "error" in results["nonexistent"]
        assert "Unknown" in results["nonexistent"]["error"]

    def test_timeout(self):
        with _background_tasks_lock:
            _background_tasks["slow"] = SubagentResult(
                task_id="slow", trace_id="tr",
                subagent_type="test",
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )
        results = wait_for_tasks(["slow"], timeout=0.5)
        assert "error" in results["slow"]
        assert "Timed out" in results["slow"]["error"]

    def test_multiple_tasks(self):
        with _background_tasks_lock:
            for i in range(3):
                _background_tasks[f"m{i}"] = SubagentResult(
                    task_id=f"m{i}", trace_id=f"tr{i}",
                    subagent_type="test",
                    status=SubagentStatus.COMPLETED,
                    result=f"result_{i}",
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                )
        results = wait_for_tasks(["m0", "m1", "m2"], timeout=5)
        assert all(results[f"m{i}"]["success"] for i in range(3))

    def test_mixed_success_and_failure(self):
        with _background_tasks_lock:
            _background_tasks["ok"] = SubagentResult(
                task_id="ok", trace_id="tr",
                subagent_type="test",
                status=SubagentStatus.COMPLETED,
                result="good",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
            _background_tasks["bad"] = SubagentResult(
                task_id="bad", trace_id="tr",
                subagent_type="test",
                status=SubagentStatus.FAILED,
                error="crash",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
        results = wait_for_tasks(["ok", "bad"], timeout=5)
        assert results["ok"]["success"] is True
        assert "error" in results["bad"]


# ---------------------------------------------------------------------------
#  4. _format_subagent_result
# ---------------------------------------------------------------------------

class TestFormatResult:
    def test_completed(self):
        sr = SubagentResult(
            task_id="t", trace_id="tr", subagent_type="coder",
            status=SubagentStatus.COMPLETED, result="done",
            steps_used=5, started_at=datetime.now(), completed_at=datetime.now(),
        )
        f = _format_subagent_result(sr)
        assert f["success"] is True
        assert f["result"] == "done"
        assert f["subagent_type"] == "coder"

    def test_failed(self):
        sr = SubagentResult(
            task_id="t", trace_id="tr", subagent_type="coder",
            status=SubagentStatus.FAILED, error="broken",
        )
        f = _format_subagent_result(sr)
        assert "error" in f
        assert f["error"] == "broken"

    def test_timed_out(self):
        sr = SubagentResult(
            task_id="t", trace_id="tr", subagent_type="coder",
            status=SubagentStatus.TIMED_OUT,
        )
        f = _format_subagent_result(sr)
        assert "error" in f
        assert "timed out" in f["error"].lower()


# ---------------------------------------------------------------------------
#  5. build_typed_subagent_tools — tool definitions
# ---------------------------------------------------------------------------

class TestBuildTools:
    def setup_method(self):
        _clear_background_tasks()

    def test_returns_three_tools(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        names = [t["name"] for t in tools]
        assert "task" in names
        assert "check_task" in names
        assert "wait_tasks" in names

    def test_task_tool_has_required_prompt(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        task_tool = next(t for t in tools if t["name"] == "task")
        assert "prompt" in task_tool["parameters"]["required"]

    def test_check_task_has_required_task_id(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        ct = next(t for t in tools if t["name"] == "check_task")
        assert "task_id" in ct["parameters"]["required"]

    def test_wait_tasks_has_required_task_ids(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        wt = next(t for t in tools if t["name"] == "wait_tasks")
        assert "task_ids" in wt["parameters"]["required"]


# ---------------------------------------------------------------------------
#  6. task() tool — async submission
# ---------------------------------------------------------------------------

class TestTaskTool:
    def setup_method(self):
        _clear_background_tasks()

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_returns_submitted_with_task_id(self, mock_sync):
        mock_sync.return_value = SubagentResult(
            task_id="x", trace_id="x",
            subagent_type="researcher",
            status=SubagentStatus.COMPLETED,
            result="found it",
        )
        tools = build_typed_subagent_tools(
            cfg={"model": "test"}, tool_registry=FakeToolRegistry(),
        )
        task_fn = next(t for t in tools if t["name"] == "task")["execute"]
        result = task_fn(prompt="find stuff", subagent_type="researcher")
        assert result["submitted"] is True
        assert "task_id" in result
        assert len(result["task_id"]) == 8

    def test_invalid_type_returns_error(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        task_fn = next(t for t in tools if t["name"] == "task")["execute"]
        result = task_fn(prompt="x", subagent_type="nonexistent")
        assert "error" in result

    def test_empty_prompt_returns_error(self):
        tools = build_typed_subagent_tools(
            cfg={}, tool_registry=FakeToolRegistry(),
        )
        task_fn = next(t for t in tools if t["name"] == "task")["execute"]
        result = task_fn(prompt="", subagent_type="researcher")
        assert "error" in result


# ---------------------------------------------------------------------------
#  7. check_task tool
# ---------------------------------------------------------------------------

class TestCheckTaskTool:
    def setup_method(self):
        _clear_background_tasks()

    def test_returns_status_for_known_task(self):
        with _background_tasks_lock:
            _background_tasks["ct1"] = SubagentResult(
                task_id="ct1", trace_id="tr",
                subagent_type="coder",
                status=SubagentStatus.COMPLETED,
                result="code written",
                started_at=datetime.now(),
                completed_at=datetime.now(),
                steps_used=3,
            )
        tools = build_typed_subagent_tools(cfg={}, tool_registry=FakeToolRegistry())
        check_fn = next(t for t in tools if t["name"] == "check_task")["execute"]
        result = check_fn(task_id="ct1")
        assert result["status"] == "completed"
        assert result["result"] == "code written"

    def test_unknown_task_id(self):
        tools = build_typed_subagent_tools(cfg={}, tool_registry=FakeToolRegistry())
        check_fn = next(t for t in tools if t["name"] == "check_task")["execute"]
        result = check_fn(task_id="nope")
        assert "error" in result

    def test_running_task_shows_elapsed(self):
        with _background_tasks_lock:
            _background_tasks["run1"] = SubagentResult(
                task_id="run1", trace_id="tr",
                subagent_type="researcher",
                status=SubagentStatus.RUNNING,
                started_at=datetime.now(),
            )
        tools = build_typed_subagent_tools(cfg={}, tool_registry=FakeToolRegistry())
        check_fn = next(t for t in tools if t["name"] == "check_task")["execute"]
        result = check_fn(task_id="run1")
        assert result["status"] == "running"
        assert "running_for_ms" in result


# ---------------------------------------------------------------------------
#  8. Parallel execution — multiple tasks concurrent
# ---------------------------------------------------------------------------

class TestParallelExecution:
    def setup_method(self):
        _clear_background_tasks()

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_multiple_tasks_run_concurrently(self, mock_sync):
        """Fire 3 tasks, verify they all start before any finishes."""
        start_barrier = threading.Barrier(3, timeout=10)
        call_times = []

        def slow_sync(*args, **kwargs):
            t0 = time.time()
            start_barrier.wait()
            call_times.append(t0)
            return SubagentResult(
                task_id=kwargs.get("task_id", "x"),
                trace_id=kwargs.get("trace_id", "x"),
                subagent_type="test",
                status=SubagentStatus.COMPLETED,
                result="done",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )

        mock_sync.side_effect = slow_sync

        futures = []
        for _ in range(3):
            task_id, future = execute_subagent_async(
                config=_make_config(),
                task_text="parallel work",
                tool_registry=FakeToolRegistry(),
                cfg={},
            )
            futures.append(future)

        for f in futures:
            f.result(timeout=15)

        assert len(call_times) == 3
        # All started within 1 second of each other (concurrency)
        assert max(call_times) - min(call_times) < 1.0


# ---------------------------------------------------------------------------
#  9. SubagentLimitMiddleware
# ---------------------------------------------------------------------------

class TestSubagentLimitMiddleware:
    def test_truncates_excess_task_calls(self):
        from ghost_middleware import SubagentLimitMiddleware, InvocationContext

        mw = SubagentLimitMiddleware(max_concurrent=2)
        ctx = InvocationContext(source="chat")
        msg = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "task", "arguments": '{"prompt": "a"}'}},
                {"function": {"name": "task", "arguments": '{"prompt": "b"}'}},
                {"function": {"name": "task", "arguments": '{"prompt": "c"}'}},
                {"function": {"name": "task", "arguments": '{"prompt": "d"}'}},
            ],
        }
        result = mw.after_model(ctx, [], msg, step=0)
        assert result is not None
        assert len(result["tool_calls"]) == 2

    def test_truncates_delegate_task_too(self):
        from ghost_middleware import SubagentLimitMiddleware, InvocationContext

        mw = SubagentLimitMiddleware(max_concurrent=2)
        ctx = InvocationContext(source="chat")
        msg = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "delegate_task", "arguments": '{}'}},
                {"function": {"name": "delegate_task", "arguments": '{}'}},
                {"function": {"name": "delegate_task", "arguments": '{}'}},
            ],
        }
        result = mw.after_model(ctx, [], msg, step=0)
        assert result is not None
        assert len(result["tool_calls"]) == 2

    def test_mixed_task_and_delegate(self):
        from ghost_middleware import SubagentLimitMiddleware, InvocationContext

        mw = SubagentLimitMiddleware(max_concurrent=2)
        ctx = InvocationContext(source="chat")
        msg = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "task", "arguments": '{}'}},
                {"function": {"name": "delegate_task", "arguments": '{}'}},
                {"function": {"name": "task", "arguments": '{}'}},
            ],
        }
        result = mw.after_model(ctx, [], msg, step=0)
        assert result is not None
        assert len(result["tool_calls"]) == 2

    def test_within_limit_returns_none(self):
        from ghost_middleware import SubagentLimitMiddleware, InvocationContext

        mw = SubagentLimitMiddleware(max_concurrent=3)
        ctx = InvocationContext(source="chat")
        msg = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "task", "arguments": '{}'}},
                {"function": {"name": "task", "arguments": '{}'}},
            ],
        }
        assert mw.after_model(ctx, [], msg, step=0) is None

    def test_preserves_non_subagent_tools(self):
        from ghost_middleware import SubagentLimitMiddleware, InvocationContext

        mw = SubagentLimitMiddleware(max_concurrent=2)
        ctx = InvocationContext(source="chat")
        msg = {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "file_read", "arguments": '{}'}},
                {"function": {"name": "task", "arguments": '{}'}},
                {"function": {"name": "shell_exec", "arguments": '{}'}},
                {"function": {"name": "task", "arguments": '{}'}},
                {"function": {"name": "task", "arguments": '{}'}},
            ],
        }
        result = mw.after_model(ctx, [], msg, step=0)
        assert result is not None
        names = [tc["function"]["name"] for tc in result["tool_calls"]]
        assert names.count("task") == 2
        assert "file_read" in names
        assert "shell_exec" in names


# ---------------------------------------------------------------------------
#  10. Engine auto-collect: parse task_ids from tool_calls_log
# ---------------------------------------------------------------------------

class TestAutoCollectParsing:
    """Test the regex extraction logic used by the engine's auto-collect block."""

    def test_extracts_task_id_from_json(self):
        raw = json.dumps({
            "submitted": True,
            "task_id": "ab12cd34",
            "subagent_type": "researcher",
        }, indent=2)
        m = re.search(r'"task_id":\s*"([a-f0-9]+)"', raw)
        assert m is not None
        assert m.group(1) == "ab12cd34"

    def test_no_match_for_error_response(self):
        raw = json.dumps({"error": "Unknown subagent type"})
        m = re.search(r'"task_id":\s*"([a-f0-9]+)"', raw)
        assert m is None

    def test_extracts_from_truncated_result(self):
        raw = json.dumps({
            "submitted": True,
            "task_id": "deadbeef",
            "message": "x" * 5000,
        }, indent=2)[:3000]
        m = re.search(r'"task_id":\s*"([a-f0-9]+)"', raw)
        assert m is not None
        assert m.group(1) == "deadbeef"

    def test_tool_calls_log_simulation(self):
        """Simulate what the engine does: scan tool_calls_log for task results."""
        tool_calls_log = [
            {"step": 5, "tool": "file_read", "result": '{"content": "hello"}'},
            {"step": 5, "tool": "task", "result": json.dumps({
                "submitted": True,
                "task_id": "aaa11111",
                "subagent_type": "researcher",
            }, indent=2)},
            {"step": 5, "tool": "task", "result": json.dumps({
                "submitted": True,
                "task_id": "bbb22222",
                "subagent_type": "coder",
            }, indent=2)},
            {"step": 4, "tool": "task", "result": json.dumps({
                "submitted": True,
                "task_id": "old33333",
                "subagent_type": "researcher",
            }, indent=2)},
        ]

        step = 5
        task_ids = []
        for entry in tool_calls_log:
            if entry.get("step") == step and entry.get("tool") == "task":
                raw = entry.get("result", "")
                if "task_id" in raw:
                    m = re.search(r'"task_id":\s*"([a-f0-9]+)"', raw)
                    if m:
                        task_ids.append(m.group(1))

        assert task_ids == ["aaa11111", "bbb22222"]
        assert "old33333" not in task_ids  # from step 4, not step 5


# ---------------------------------------------------------------------------
#  11. SSE event bus integration
# ---------------------------------------------------------------------------

class TestSSEEventBus:
    def setup_method(self):
        _clear_background_tasks()

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_task_tool_passes_event_bus(self, mock_sync):
        mock_sync.return_value = SubagentResult(
            task_id="x", trace_id="x",
            subagent_type="researcher",
            status=SubagentStatus.COMPLETED,
            result="done",
        )
        bus = MagicMock()
        tools = build_typed_subagent_tools(
            cfg={"model": "test"},
            tool_registry=FakeToolRegistry(),
            event_bus=bus,
        )
        task_fn = next(t for t in tools if t["name"] == "task")["execute"]
        result = task_fn(prompt="work", subagent_type="researcher")
        assert result["submitted"] is True

        # Wait for async execution to complete
        tid = result["task_id"]
        for _ in range(50):
            sr = get_background_task_result(tid)
            if sr and sr.status == SubagentStatus.COMPLETED:
                break
            time.sleep(0.1)

        # _run_subagent_sync was called with event_bus
        call_kwargs = mock_sync.call_args
        assert call_kwargs[1].get("event_bus") is bus or call_kwargs[0][6] is bus


# ---------------------------------------------------------------------------
#  12. Stress test: many concurrent tasks
# ---------------------------------------------------------------------------

class TestStressConcurrent:
    def setup_method(self):
        _clear_background_tasks()

    @patch("ghost_subagent_config._run_subagent_sync")
    def test_ten_tasks_all_complete(self, mock_sync):
        def fast_sync(*args, **kwargs):
            time.sleep(0.05)
            return SubagentResult(
                task_id=kwargs.get("task_id", "x"),
                trace_id=kwargs.get("trace_id", "x"),
                subagent_type="test",
                status=SubagentStatus.COMPLETED,
                result=f"result-{kwargs.get('task_id', '?')}",
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
        mock_sync.side_effect = fast_sync

        ids = []
        futures = []
        for _ in range(10):
            tid, fut = execute_subagent_async(
                config=_make_config(),
                task_text="stress",
                tool_registry=FakeToolRegistry(),
                cfg={},
            )
            ids.append(tid)
            futures.append(fut)

        # Wait for all (thread pool has 3 workers, so batches of 3)
        for f in futures:
            f.result(timeout=30)

        results = wait_for_tasks(ids, timeout=5)
        assert len(results) == 10
        assert all(r.get("success") for r in results.values())
