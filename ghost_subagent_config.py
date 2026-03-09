"""
Ghost Subagent Config + Registry + Executor — Multi-type delegation with timeouts.

Mirrored from DeerFlow's subagents/ architecture:
  - SubagentConfig dataclass (config.py)
  - Registry dict with built-in types (builtins/)
  - Two-pool executor with timeout enforcement (executor.py)
  - Config-driven tool filtering (allowlist + denylist)

Replaces the single-type delegate_task with a registry of typed subagents:
  - researcher: Read-only research with web + file tools
  - coder: Full write access for code tasks
  - bash: Shell execution specialist
  - reviewer: Readonly code review
"""

import logging
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

log = logging.getLogger("ghost.subagent")


# ═══════════════════════════════════════════════════════════════════
#  CONFIG  (mirrors DeerFlow's subagents/config.py)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SubagentConfig:
    """Configuration for a subagent type.

    Attributes:
        name: Unique identifier for this subagent type.
        description: When to use this subagent (shown to LLM).
        system_prompt: The system prompt that guides the subagent.
        tools: Allowlist of tool names. None = inherit all parent tools.
        disallowed_tools: Denylist of tool names. Always excluded.
        model: Model to use. "inherit" = use parent's model.
        max_steps: Maximum tool-loop steps before stopping.
        timeout_seconds: Maximum wall-clock time (default: 900 = 15 minutes).
        max_result_chars: Truncate result to this length.
    """
    name: str
    description: str
    system_prompt: str
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = field(default_factory=lambda: ["delegate_task", "task"])
    model: str = "inherit"
    max_steps: int = 25
    timeout_seconds: int = 900
    max_result_chars: int = 3000


# ═══════════════════════════════════════════════════════════════════
#  BUILT-IN SUBAGENT TYPES  (mirrors DeerFlow's builtins/)
# ═══════════════════════════════════════════════════════════════════

RESEARCHER_CONFIG = SubagentConfig(
    name="researcher",
    description=(
        "A focused research agent with read-only access. Use for:\n"
        "- Verifying interface compatibility after code changes\n"
        "- Researching a module's API before writing code\n"
        "- Summarizing large files without polluting parent context\n"
        "- Web research requiring multiple search + fetch steps\n"
        "Do NOT use for simple single-step operations."
    ),
    system_prompt=(
        "You are a focused research assistant working inside the Ghost codebase. "
        "Your job: complete the task below and return a clear, concise summary.\n\n"
        "RULES:\n"
        "- ONLY read and analyze. Do NOT modify files, run commands, or take actions.\n"
        "- Be precise about method names, signatures, and line numbers.\n"
        "- If you find issues (missing methods, wrong signatures), list them explicitly.\n"
        "- Keep your final response under 2000 characters.\n"
        "- Do NOT explain your process. Just return the findings."
    ),
    tools=["file_read", "grep", "glob", "memory_search", "web_search", "web_fetch",
           "analyze_code_file", "find_code_patterns", "hybrid_memory_search",
           "semantic_memory_search"],
    disallowed_tools=["delegate_task", "task", "shell_exec", "file_write", "apply_diff"],
    max_steps=20,
    timeout_seconds=300,
    max_result_chars=3000,
)

CODER_CONFIG = SubagentConfig(
    name="coder",
    description=(
        "A code-writing agent with full tool access. Use for:\n"
        "- Implementing features that require reading + writing files\n"
        "- Complex multi-file code changes\n"
        "- Tasks requiring shell commands (install deps, run tests)\n"
        "Do NOT use for simple read-only research."
    ),
    system_prompt=(
        "You are a skilled coding agent working inside the Ghost codebase. "
        "Complete the task below autonomously and return a summary of changes.\n\n"
        "RULES:\n"
        "- Read files before modifying them.\n"
        "- Make targeted, minimal changes.\n"
        "- Verify your changes compile/pass basic checks.\n"
        "- Return a concise summary of what you changed and why."
    ),
    tools=None,
    disallowed_tools=["delegate_task", "task"],
    max_steps=30,
    timeout_seconds=600,
    max_result_chars=3000,
)

BASH_CONFIG = SubagentConfig(
    name="bash",
    description=(
        "Command execution specialist for bash operations. Use for:\n"
        "- Running a series of related shell commands\n"
        "- Git, npm, pip, docker operations\n"
        "- Build, test, or deployment pipelines\n"
        "- Verbose command output that would clutter main context\n"
        "Do NOT use for simple single commands."
    ),
    system_prompt=(
        "You are a bash command execution specialist. Execute commands carefully "
        "and report results clearly.\n\n"
        "RULES:\n"
        "- Execute commands one at a time when they depend on each other.\n"
        "- Report both stdout and stderr when relevant.\n"
        "- Handle errors gracefully and explain what went wrong.\n"
        "- Use absolute paths for file operations.\n"
        "- Be cautious with destructive operations."
    ),
    tools=["shell_exec", "file_read", "file_write", "grep", "glob"],
    disallowed_tools=["delegate_task", "task"],
    model="inherit",
    max_steps=20,
    timeout_seconds=600,
    max_result_chars=5000,
)

REVIEWER_CONFIG = SubagentConfig(
    name="reviewer",
    description=(
        "A code review agent that examines changes for quality. Use for:\n"
        "- Reviewing code changes before deployment\n"
        "- Checking for bugs, security issues, or style violations\n"
        "- Verifying test coverage and documentation\n"
        "Do NOT use for making changes."
    ),
    system_prompt=(
        "You are a code reviewer. Examine the code and provide a structured review.\n\n"
        "RULES:\n"
        "- Check for bugs, security issues, and correctness.\n"
        "- Verify error handling and edge cases.\n"
        "- Comment on code clarity and maintainability.\n"
        "- Be specific: reference line numbers and function names.\n"
        "- Return a structured review with severity ratings."
    ),
    tools=["file_read", "grep", "glob", "analyze_code_file", "find_code_patterns"],
    disallowed_tools=["delegate_task", "task", "shell_exec", "file_write", "apply_diff"],
    max_steps=15,
    timeout_seconds=300,
    max_result_chars=3000,
)

BUILTIN_SUBAGENTS: dict[str, SubagentConfig] = {
    "researcher": RESEARCHER_CONFIG,
    "coder": CODER_CONFIG,
    "bash": BASH_CONFIG,
    "reviewer": REVIEWER_CONFIG,
}


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get a subagent configuration by name."""
    return BUILTIN_SUBAGENTS.get(name)


def list_subagent_types() -> list[str]:
    """List available subagent type names."""
    return list(BUILTIN_SUBAGENTS.keys())


# ═══════════════════════════════════════════════════════════════════
#  STATUS TRACKING  (mirrors DeerFlow's SubagentStatus + SubagentResult)
# ═══════════════════════════════════════════════════════════════════

class SubagentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentResult:
    task_id: str
    trace_id: str
    subagent_type: str
    status: SubagentStatus
    result: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps_used: int = 0
    tokens_used: int = 0

    @property
    def duration_ms(self) -> int:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return 0


# ═══════════════════════════════════════════════════════════════════
#  TOOL FILTERING  (mirrors DeerFlow's _filter_tools)
# ═══════════════════════════════════════════════════════════════════

def filter_tool_names(
    all_tool_names: list[str],
    allowed: list[str] | None,
    disallowed: list[str] | None,
) -> list[str]:
    """Filter tool names using allowlist + denylist."""
    filtered = all_tool_names
    if allowed is not None:
        allowed_set = set(allowed)
        filtered = [n for n in filtered if n in allowed_set]
    if disallowed is not None:
        disallowed_set = set(disallowed)
        filtered = [n for n in filtered if n not in disallowed_set]
    return filtered


# ═══════════════════════════════════════════════════════════════════
#  TWO-POOL EXECUTOR  (mirrors DeerFlow's executor.py)
# ═══════════════════════════════════════════════════════════════════

_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()

_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ghost-subagent-sched-")
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ghost-subagent-exec-")

MAX_CONCURRENT_SUBAGENTS = 3


def _run_subagent_sync(
    config: SubagentConfig,
    task: str,
    tool_registry,
    cfg: dict,
    auth_store=None,
    provider_chain=None,
) -> SubagentResult:
    """Execute a subagent synchronously using Ghost's ToolLoopEngine."""
    from ghost_loop import ToolLoopEngine

    trace_id = uuid.uuid4().hex[:8]
    task_id = uuid.uuid4().hex[:8]
    result = SubagentResult(
        task_id=task_id,
        trace_id=trace_id,
        subagent_type=config.name,
        status=SubagentStatus.RUNNING,
        started_at=datetime.now(),
    )

    available_names = tool_registry.names() if hasattr(tool_registry, 'names') else []
    filtered_names = filter_tool_names(available_names, config.tools, config.disallowed_tools)
    filtered_registry = tool_registry.subset(
        [n for n in filtered_names if n in available_names]
    ) if hasattr(tool_registry, 'subset') else tool_registry

    api_key = None
    if auth_store:
        try:
            api_key = auth_store.get_api_key("openrouter")
        except (AttributeError, TypeError):
            pass
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

    if not api_key:
        result.status = SubagentStatus.FAILED
        result.error = "No API key available"
        result.completed_at = datetime.now()
        return result

    model = cfg.get("model", "anthropic/claude-sonnet-4") if config.model == "inherit" else config.model

    engine = ToolLoopEngine(
        api_key=api_key,
        model=model,
        fallback_models=cfg.get("fallback_models", []),
        auth_store=auth_store,
        provider_chain=provider_chain,
    )

    log.info("[trace=%s] Subagent %s starting: %s...", trace_id, config.name, task[:80])

    try:
        loop_result = engine.run(
            system_prompt=config.system_prompt,
            user_message=task.strip(),
            tool_registry=filtered_registry,
            max_steps=config.max_steps,
            temperature=0.2,
            max_tokens=2048,
        )

        text = (loop_result.text or "").strip()
        if len(text) > config.max_result_chars:
            text = text[:config.max_result_chars] + "\n... [truncated]"

        result.result = text
        result.steps_used = loop_result.steps
        result.tokens_used = loop_result.total_tokens
        result.status = SubagentStatus.COMPLETED
        result.completed_at = datetime.now()

        log.info("[trace=%s] Subagent %s completed in %dms (%d steps)",
                 trace_id, config.name, result.duration_ms, result.steps_used)

    except Exception as exc:
        result.status = SubagentStatus.FAILED
        result.error = f"{type(exc).__name__}: {exc}"
        result.completed_at = datetime.now()
        log.warning("[trace=%s] Subagent %s failed: %s", trace_id, config.name, exc)

    return result


def execute_subagent_async(
    config: SubagentConfig,
    task: str,
    tool_registry,
    cfg: dict,
    auth_store=None,
    provider_chain=None,
) -> str:
    """Start a subagent in the background with timeout enforcement.

    Uses the two-pool architecture from DeerFlow:
    - Scheduler pool submits work to execution pool
    - Scheduler enforces timeout via future.result(timeout=N)

    Returns task_id for status polling.
    """
    task_id = uuid.uuid4().hex[:8]
    trace_id = uuid.uuid4().hex[:8]

    result = SubagentResult(
        task_id=task_id,
        trace_id=trace_id,
        subagent_type=config.name,
        status=SubagentStatus.PENDING,
    )

    with _background_tasks_lock:
        _background_tasks[task_id] = result
        _cleanup_background_tasks()

    def run_task():
        with _background_tasks_lock:
            _background_tasks[task_id].status = SubagentStatus.RUNNING
            _background_tasks[task_id].started_at = datetime.now()

        try:
            execution_future: Future = _execution_pool.submit(
                _run_subagent_sync, config, task, tool_registry, cfg,
                auth_store, provider_chain
            )
            try:
                exec_result = execution_future.result(timeout=config.timeout_seconds)
                with _background_tasks_lock:
                    _background_tasks[task_id].status = exec_result.status
                    _background_tasks[task_id].result = exec_result.result
                    _background_tasks[task_id].error = exec_result.error
                    _background_tasks[task_id].completed_at = datetime.now()
                    _background_tasks[task_id].steps_used = exec_result.steps_used
                    _background_tasks[task_id].tokens_used = exec_result.tokens_used
            except FuturesTimeoutError:
                log.error("[trace=%s] Subagent %s timed out after %ds",
                         trace_id, config.name, config.timeout_seconds)
                with _background_tasks_lock:
                    _background_tasks[task_id].status = SubagentStatus.TIMED_OUT
                    _background_tasks[task_id].error = (
                        f"Execution timed out after {config.timeout_seconds} seconds"
                    )
                    _background_tasks[task_id].completed_at = datetime.now()
                execution_future.cancel()
        except Exception as e:
            log.error("[trace=%s] Subagent %s scheduler error: %s", trace_id, config.name, e)
            with _background_tasks_lock:
                _background_tasks[task_id].status = SubagentStatus.FAILED
                _background_tasks[task_id].error = str(e)
                _background_tasks[task_id].completed_at = datetime.now()

    _scheduler_pool.submit(run_task)
    return task_id


_MAX_BACKGROUND_TASKS = 50


def _cleanup_background_tasks() -> None:
    """Remove oldest completed/failed/timed_out tasks when dict exceeds max size."""
    if len(_background_tasks) <= _MAX_BACKGROUND_TASKS:
        return
    terminal = {SubagentStatus.COMPLETED, SubagentStatus.FAILED, SubagentStatus.TIMED_OUT}
    removable = sorted(
        (tid for tid, r in _background_tasks.items() if r.status in terminal),
        key=lambda tid: _background_tasks[tid].completed_at or datetime.min,
    )
    to_remove = len(_background_tasks) - _MAX_BACKGROUND_TASKS
    for tid in removable[:to_remove]:
        del _background_tasks[tid]


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    with _background_tasks_lock:
        return list(_background_tasks.values())


# ═══════════════════════════════════════════════════════════════════
#  TOOL BUILDER  (for Ghost's tool registry)
# ═══════════════════════════════════════════════════════════════════

def build_typed_subagent_tools(
    cfg: dict,
    tool_registry,
    auth_store=None,
    provider_chain=None,
) -> list[dict]:
    """Build the task tool that supports typed subagent delegation.

    The LLM picks a subagent_type from the available types, and the
    tool dispatches to the correct config + executor with timeout.
    """
    available_types = list_subagent_types()
    type_descriptions = "\n".join(
        f"- {name}: {BUILTIN_SUBAGENTS[name].description.split(chr(10))[0]}"
        for name in available_types
    )

    def task(prompt: str, subagent_type: str = "researcher", max_steps: int = None):
        """
        Delegate a task to a specialized subagent for parallel or isolated execution.

        Args:
            prompt: Clear description of the task to complete.
            subagent_type: Type of subagent (researcher, coder, bash, reviewer).
            max_steps: Override max tool-loop steps (optional).

        Returns:
            Result from the subagent.
        """
        config = get_subagent_config(subagent_type)
        if config is None:
            return {"error": f"Unknown subagent type: {subagent_type}. Available: {available_types}"}

        if not prompt or not prompt.strip():
            return {"error": "Task prompt is required."}

        if max_steps is not None:
            from dataclasses import replace
            try:
                max_steps = int(max_steps)
            except (TypeError, ValueError):
                max_steps = config.max_steps
            config = replace(config, max_steps=min(max(1, max_steps), config.max_steps))

        result = _run_subagent_sync(
            config=config,
            task=prompt,
            tool_registry=tool_registry,
            cfg=cfg,
            auth_store=auth_store,
            provider_chain=provider_chain,
        )

        if result.status == SubagentStatus.COMPLETED:
            return {
                "success": True,
                "result": result.result,
                "subagent_type": result.subagent_type,
                "steps_used": result.steps_used,
                "duration_ms": result.duration_ms,
            }
        elif result.status == SubagentStatus.TIMED_OUT:
            return {
                "error": f"Subagent timed out after {config.timeout_seconds}s",
                "subagent_type": result.subagent_type,
            }
        else:
            return {
                "error": result.error or "Unknown error",
                "subagent_type": result.subagent_type,
            }

    return [{
        "name": "task",
        "description": (
            "Delegate a task to a specialized subagent for isolated execution with "
            "a fresh context window. Choose the right subagent type:\n"
            f"{type_descriptions}\n\n"
            "Use this when you need accurate information from files that may have "
            "been lost to context truncation, or for parallel sub-tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Clear description of the task. Be specific: include file paths, "
                        "class names, and what to accomplish."
                    ),
                },
                "subagent_type": {
                    "type": "string",
                    "enum": available_types,
                    "description": f"Type of subagent: {', '.join(available_types)}",
                    "default": "researcher",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Override max tool-loop steps (optional).",
                },
            },
            "required": ["prompt"],
        },
        "execute": task,
    }]
