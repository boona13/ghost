"""Middleware pipeline for Ghost agent invocations.

DeerFlow-grade architecture with 6 hook points:
  before_invoke / after_invoke   — wrap the entire engine.run() call
  before_model  / after_model    — wrap EACH LLM call inside the loop
  wrap_tool_call                 — intercept individual tool executions
  after_tool_call                — modify tool results after execution

The engine calls back into the chain at each LLM call and tool call,
giving middlewares full control over every stage of the agent loop.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("ghost.middleware")

# ---------------------------------------------------------------------------
# InvocationContext — carries ALL state for a single agent invocation
# ---------------------------------------------------------------------------


@dataclass
class InvocationContext:
    """All state for a single agent invocation.

    Every field that differs between entry points is a separate, explicit
    field — never hidden inside generic middleware logic.
    """

    # -- Source identification --
    source: str  # "chat" | "cron" | "channel" | "monitor" | "action"

    # -- Input (set by entry point BEFORE chain runs) --
    user_message: str = ""
    system_prompt_parts: list[str] = field(default_factory=list)
    tool_registry: Any = None
    history: list | None = None
    images: list | None = None      # list of {data, mime} dicts  (chat)
    image_b64: str | None = None    # single base64 string        (inbound)
    max_steps: int = 200
    max_tokens: int = 4096
    temperature: float = 0.3
    force_tool: bool = True
    enable_reasoning: bool = False
    model_override: str | None = None
    cancel_check: Any = None
    on_step: Any = None
    on_token: Any = None

    # -- Daemon references --
    daemon: Any = None
    engine: Any = None              # caller sets this: chat_engine or engine
    config: dict = field(default_factory=dict)

    # -- Enrichment (set by middleware) --
    matched_skills: list = field(default_factory=list)
    active_project: Any = None      # set by entry point, used by SkillMatch
    caller_context: str = "autonomous"

    # -- Output (set after engine.run) --
    result: Any = None              # ToolLoopResult
    result_text: str = ""
    tools_used: list = field(default_factory=list)
    tokens_used: int = 0
    escalation_count: int = 0

    # -- Source-specific metadata --
    meta: dict = field(default_factory=dict)

    @property
    def system_prompt(self) -> str:
        return "\n\n".join(p for p in self.system_prompt_parts if p)


# ---------------------------------------------------------------------------
# Middleware base class — 6 hook points
# ---------------------------------------------------------------------------


class Middleware:
    """Base class for all middleware.

    Subclasses override any combination of hook methods.  Returning None
    from a hook means "no modification" — the chain continues with the
    original value.
    """

    # -- Invocation-level hooks (wrap the entire engine.run) --

    def before_invoke(self, ctx: InvocationContext) -> None:
        """Called once before engine.run().  May mutate *ctx* in-place."""

    def after_invoke(self, ctx: InvocationContext) -> None:
        """Called once after engine.run().  May mutate *ctx* in-place."""

    # -- Per-LLM-call hooks (called every step inside the engine loop) --

    def before_model(self, ctx: InvocationContext, messages: list, step: int) -> list | None:
        """Called before each LLM API call inside the loop.

        May inspect or modify the messages list.  Return a new list to
        replace messages, or None to keep them unchanged.
        """

    def after_model(self, ctx: InvocationContext, messages: list, response_msg: dict, step: int) -> dict | None:
        """Called after each LLM response, before tool call processing.

        *response_msg* is the assistant message dict that was just appended
        to *messages*.  Return a replacement dict or None to keep it.
        """

    # -- Per-tool-call hooks (called for every individual tool execution) --

    def wrap_tool_call(self, ctx: InvocationContext, tool_name: str, args: dict, step: int) -> str | None:
        """Called before a tool is executed.

        Return a string to INTERCEPT the call (the string becomes the tool
        result and normal execution is skipped).  Return None to let the
        tool execute normally.
        """

    def after_tool_call(self, ctx: InvocationContext, tool_name: str, args: dict, result: str, step: int) -> str | None:
        """Called after a tool has executed.

        Return a modified result string, or None to keep the original.
        """


# ---------------------------------------------------------------------------
# MiddlewareChain — ordered execution with engine call in the middle
# ---------------------------------------------------------------------------


class MiddlewareChain:
    """Runs before-hooks → engine.run → after-hooks in order.

    The chain is also passed INTO the engine so it can call per-step
    hooks (before_model, after_model, wrap_tool_call, after_tool_call).
    """

    def __init__(self, middlewares: list[Middleware] | None = None):
        self._middlewares: list[Middleware] = list(middlewares or [])
        self._active_ctx: InvocationContext | None = None

    def add(self, mw: Middleware) -> "MiddlewareChain":
        self._middlewares.append(mw)
        return self

    # -- Full invocation lifecycle --

    def invoke(self, ctx: InvocationContext) -> InvocationContext:
        """Execute the full pipeline: before → engine → after."""
        self._active_ctx = ctx
        log.debug("[MW] invoke source=%s user=%s",
                  ctx.source, (ctx.user_message or "")[:80])

        for mw in self._middlewares:
            try:
                mw.before_invoke(ctx)
            except Exception as exc:
                log.error("%s.before_invoke failed: %s",
                          type(mw).__name__, exc, exc_info=True)

        self._run_engine(ctx)

        for mw in self._middlewares:
            try:
                mw.after_invoke(ctx)
            except Exception as exc:
                log.error("%s.after_invoke failed: %s",
                          type(mw).__name__, exc, exc_info=True)

        self._active_ctx = None
        return ctx

    # -- Per-step hooks called by the engine --

    def before_model(self, messages: list, step: int) -> list:
        """Engine calls this before each LLM API call."""
        ctx = self._active_ctx
        for mw in self._middlewares:
            try:
                result = mw.before_model(ctx, messages, step)
                if result is not None:
                    messages = result
            except Exception as exc:
                log.error("%s.before_model failed: %s",
                          type(mw).__name__, exc, exc_info=True)
        return messages

    def after_model(self, messages: list, response_msg: dict, step: int) -> dict | None:
        """Engine calls this after each LLM response."""
        ctx = self._active_ctx
        override = None
        for mw in self._middlewares:
            try:
                result = mw.after_model(ctx, messages, response_msg, step)
                if result is not None:
                    response_msg = result
                    override = result
            except Exception as exc:
                log.error("%s.after_model failed: %s",
                          type(mw).__name__, exc, exc_info=True)
        return override

    def wrap_tool_call(self, tool_name: str, args: dict, step: int) -> str | None:
        """Engine calls this before executing a tool.  First non-None wins."""
        ctx = self._active_ctx
        for mw in self._middlewares:
            try:
                result = mw.wrap_tool_call(ctx, tool_name, args, step)
                if result is not None:
                    log.info("wrap_tool_call: %s intercepted %s at step %d",
                             type(mw).__name__, tool_name, step)
                    return result
            except Exception as exc:
                log.error("%s.wrap_tool_call failed: %s",
                          type(mw).__name__, exc, exc_info=True)
        return None

    def after_tool_call(self, tool_name: str, args: dict, result: str, step: int) -> str:
        """Engine calls this after a tool has executed."""
        ctx = self._active_ctx
        for mw in self._middlewares:
            try:
                modified = mw.after_tool_call(ctx, tool_name, args, result, step)
                if modified is not None:
                    result = modified
            except Exception as exc:
                log.error("%s.after_tool_call failed: %s",
                          type(mw).__name__, exc, exc_info=True)
        return result

    # -- private: faithful pass-through of ALL engine.run params -----------

    def _run_engine(self, ctx: InvocationContext) -> None:
        if ctx.engine is None:
            log.error("No engine on InvocationContext — skipping engine.run()")
            return

        from ghost_tools import set_shell_caller_context
        set_shell_caller_context(ctx.caller_context)

        try:
            ctx.result = ctx.engine.run(
                system_prompt=ctx.system_prompt,
                user_message=ctx.user_message,
                tool_registry=ctx.tool_registry,
                max_steps=ctx.max_steps,
                max_tokens=ctx.max_tokens,
                temperature=ctx.temperature,
                force_tool=ctx.force_tool,
                on_step=ctx.on_step,
                history=ctx.history,
                cancel_check=ctx.cancel_check,
                images=ctx.images,
                image_b64=ctx.image_b64,
                enable_reasoning=ctx.enable_reasoning,
                model_override=ctx.model_override,
                hook_runner=ctx.daemon.hooks if ctx.daemon else None,
                tool_intent_security=getattr(
                    ctx.daemon, "tool_intent_security", None),
                tool_event_bus=getattr(
                    ctx.daemon, "tool_event_bus", None),
                on_token=ctx.on_token,
                middleware_chain=self,
            )
            if ctx.result:
                ctx.result_text = ctx.result.text or ""
                ctx.tools_used = [
                    tc["tool"] for tc in (ctx.result.tool_calls or [])
                ]
                ctx.tokens_used = ctx.result.total_tokens or 0
        except Exception as exc:
            log.error("Engine.run failed: %s", exc, exc_info=True)
            ctx.result_text = f"Error: {exc}"
            ctx.meta["engine_error"] = exc
        finally:
            set_shell_caller_context("autonomous")


# ===========================================================================
# INVOCATION-LEVEL MIDDLEWARES (before_invoke / after_invoke)
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. IdentityMiddleware
# ---------------------------------------------------------------------------


class IdentityMiddleware(Middleware):
    """Prepend SOUL.md + USER.md + platform info to the system prompt."""

    def before_invoke(self, ctx: InvocationContext) -> None:
        if ctx.daemon is None:
            return
        try:
            identity = ctx.daemon._build_identity_context()
            if identity:
                ctx.system_prompt_parts.insert(0, identity)
        except Exception as exc:
            log.warning("IdentityMiddleware: %s", exc)


# ---------------------------------------------------------------------------
# 2. SkillMatchMiddleware
# ---------------------------------------------------------------------------


class SkillMatchMiddleware(Middleware):
    """Match skills, inject prompt section, resolve model override."""

    def before_invoke(self, ctx: InvocationContext) -> None:
        daemon = ctx.daemon
        if not daemon or not getattr(daemon, "skill_loader", None):
            return
        try:
            daemon.skill_loader.check_reload()
            disabled = set(ctx.config.get("disabled_skills", []))

            if ctx.active_project:
                disabled |= set(
                    ctx.active_project.config.get("disabled_skills", [])
                )

            content_type = ctx.meta.get("content_type")

            ctx.matched_skills = daemon.skill_loader.match(
                ctx.user_message, content_type, disabled=disabled
            )

            if ctx.active_project:
                project_enabled = ctx.active_project.config.get("skills", [])
                if project_enabled:
                    allowed = set(project_enabled)
                    ctx.matched_skills = [
                        s for s in ctx.matched_skills if s.name in allowed
                    ]

            if ctx.matched_skills:
                skills_prompt = daemon.skill_loader.build_skills_prompt(
                    ctx.matched_skills
                )
                ctx.system_prompt_parts.append(skills_prompt)

            if ctx.matched_skills and not ctx.model_override:
                skill_model = daemon._resolve_skill_model(ctx.matched_skills)
                if skill_model:
                    ctx.model_override = skill_model

        except Exception as exc:
            log.warning("SkillMatchMiddleware: %s", exc)
            ctx.matched_skills = []


# ---------------------------------------------------------------------------
# 3. ToolScopeMiddleware
# ---------------------------------------------------------------------------


class ToolScopeMiddleware(Middleware):
    """Restrict tool_registry based on source and context."""

    _EVOLVE_TOOLS = frozenset({
        "evolve_plan", "evolve_apply", "evolve_apply_config",
        "evolve_delete", "evolve_test", "evolve_deploy", "evolve_rollback",
        "evolve_submit_pr",
    })
    _FEATURE_MUTATE_TOOLS = frozenset({
        "start_future_feature", "complete_future_feature",
        "fail_future_feature", "evolve_resume",
    })

    _IMPLEMENTER_ALLOWLIST = [
        "evolve_plan", "evolve_apply", "evolve_apply_config",
        "evolve_test", "evolve_deploy", "evolve_rollback",
        "evolve_delete", "evolve_submit_pr",
        "list_future_features", "get_future_feature",
        "start_future_feature", "complete_future_feature",
        "fail_future_feature", "get_feature_stats",
        "add_future_feature",
        "file_read", "file_search", "file_write",
        "grep", "glob", "find_code_patterns",
        "shell_exec", "shell_session", "shell_bg_start",
        "shell_bg_status", "shell_bg_kill",
        "delegate_task",
        "web_fetch", "web_search",
        "browser_navigate", "browser_snapshot",
        "browser_click", "browser_type",
        "memory_save", "memory_search",
        "config_get", "config_set",
        "tools_list", "tools_create", "tools_install_github",
        "tools_uninstall", "tools_validate",
        "tools_enable", "tools_disable",
        "task_complete",
    ]

    def before_invoke(self, ctx: InvocationContext) -> None:
        if ctx.tool_registry is None:
            return

        is_evo_runner = ctx.meta.get("is_evolution_runner", False)

        if is_evo_runner:
            available = set(ctx.tool_registry.names())
            allowed = [t for t in self._IMPLEMENTER_ALLOWLIST
                       if t in available]
            ctx.tool_registry = ctx.tool_registry.subset(allowed)
            return

        exclude = self._EVOLVE_TOOLS
        if ctx.source == "cron":
            exclude = self._EVOLVE_TOOLS | self._FEATURE_MUTATE_TOOLS
        safe_names = [
            n for n in ctx.tool_registry.names() if n not in exclude
        ]
        ctx.tool_registry = ctx.tool_registry.subset(safe_names)

        if not ctx.matched_skills:
            return
        if not ctx.daemon or not getattr(ctx.daemon, "skill_loader", None):
            return
        needed = ctx.daemon.skill_loader.get_tools_for_skills(
            ctx.matched_skills
        )
        if not needed:
            return

        if ctx.source == "chat" and ctx.active_project:
            _ALWAYS = {
                "memory_search", "memory_save", "task_complete",
                "project_list", "project_get", "project_resolve",
                "file_read", "file_write", "file_search",
                "shell_exec", "grep", "glob",
                "notify", "uptime", "app_control",
                "add_future_feature", "list_future_features",
                "get_future_feature", "get_feature_stats",
            }
        else:
            _ALWAYS = {"memory_search", "memory_save", "notify"}

        all_names = list(set(needed) | _ALWAYS)
        available = set(ctx.tool_registry.names())
        valid = [n for n in all_names if n in available]
        if valid:
            ctx.tool_registry = ctx.tool_registry.subset(valid)


# ---------------------------------------------------------------------------
# 4. CallerContextMiddleware
# ---------------------------------------------------------------------------


class CallerContextMiddleware(Middleware):
    """Map invocation source to shell caller context."""

    _MAP = {
        "chat": "interactive",
        "channel": "interactive",
        "action": "interactive",
        "monitor": "interactive",
        "cron": "autonomous",
    }

    def before_invoke(self, ctx: InvocationContext) -> None:
        ctx.caller_context = self._MAP.get(ctx.source, "autonomous")


# ---------------------------------------------------------------------------
# 5. GiveUpDetectionMiddleware
# ---------------------------------------------------------------------------


class GiveUpDetectionMiddleware(Middleware):
    """Detect give-up responses and retry with escalation coaching."""

    MAX_RETRIES = 2

    def after_invoke(self, ctx: InvocationContext) -> None:
        if ctx.source in ("cron", "monitor"):
            return
        if not ctx.result_text or len(ctx.result_text.strip()) < 20:
            return

        try:
            from ghost import _detected_give_up, _ESCALATION_COACHING
        except ImportError:
            return

        for attempt in range(self.MAX_RETRIES):
            cancelled = ctx.cancel_check() if ctx.cancel_check else False
            if cancelled:
                break
            if not _detected_give_up(ctx.result_text, engine=ctx.engine):
                break

            ctx.escalation_count = attempt + 1
            log.info("Give-up detected (attempt %d/%d), escalating",
                     attempt + 1, self.MAX_RETRIES)

            esc_history = list(ctx.history or [])
            esc_history.append({"role": "user", "content": ctx.user_message})
            esc_history.append({
                "role": "assistant", "content": ctx.result_text
            })

            if ctx.source == "chat" and "session" in ctx.meta:
                session = ctx.meta["session"]
                if hasattr(session, "token_chunks"):
                    session.token_chunks.clear()

            from ghost_tools import set_shell_caller_context
            set_shell_caller_context(ctx.caller_context)
            try:
                retry_result = ctx.engine.run(
                    system_prompt=ctx.system_prompt,
                    user_message=_ESCALATION_COACHING,
                    tool_registry=ctx.tool_registry,
                    max_steps=ctx.max_steps,
                    max_tokens=ctx.max_tokens,
                    temperature=ctx.temperature,
                    force_tool=ctx.force_tool,
                    on_step=ctx.on_step,
                    history=esc_history,
                    cancel_check=ctx.cancel_check,
                    images=ctx.images,
                    image_b64=ctx.image_b64,
                    enable_reasoning=ctx.enable_reasoning,
                    model_override=ctx.model_override,
                    hook_runner=(ctx.daemon.hooks
                                if ctx.daemon else None),
                    tool_intent_security=getattr(
                        ctx.daemon, "tool_intent_security", None),
                    tool_event_bus=getattr(
                        ctx.daemon, "tool_event_bus", None),
                    on_token=ctx.on_token,
                )
                if retry_result:
                    ctx.result = retry_result
                    ctx.result_text = retry_result.text or ""
                    new_tools = [
                        tc["tool"]
                        for tc in (retry_result.tool_calls or [])
                    ]
                    ctx.tools_used = ctx.tools_used + new_tools
                    ctx.tokens_used += retry_result.total_tokens or 0
            except Exception as exc:
                log.warning("Escalation attempt %d failed: %s",
                            attempt + 1, exc)
                break
            finally:
                set_shell_caller_context("autonomous")


# ---------------------------------------------------------------------------
# 6. BrowserCleanupMiddleware
# ---------------------------------------------------------------------------


class BrowserCleanupMiddleware(Middleware):
    """Stop browser if any browser tools were used.

    Skips chat — users may have multi-turn browser sessions where the
    browser must stay open between messages.
    """

    def after_invoke(self, ctx: InvocationContext) -> None:
        if ctx.source == "chat":
            return
        if not ctx.tools_used:
            return
        if ctx.daemon and hasattr(ctx.daemon, "_cleanup_browser_after_task"):
            try:
                ctx.daemon._cleanup_browser_after_task(ctx.tools_used)
            except Exception as exc:
                log.warning("BrowserCleanupMiddleware: %s", exc)


# ===========================================================================
# PER-STEP MIDDLEWARES (before_model / after_model / wrap_tool_call)
# ===========================================================================


# ---------------------------------------------------------------------------
# 7. DanglingToolCallRepairMiddleware  (before_model)
#    Inspired by DeerFlow's DanglingToolCallMiddleware.
#    Runs EVERY step to catch dangling tool calls that appear mid-loop
#    (e.g. if a prior tool execution crashed and left an orphan).
# ---------------------------------------------------------------------------


class DanglingToolCallRepairMiddleware(Middleware):
    """Fix broken tool message sequences before each LLM call.

    Scans the message list for assistant messages whose tool_calls have no
    matching tool-result message and injects synthetic placeholders in the
    correct position (immediately after the offending assistant message).

    Unlike the one-shot repair at history load time, this runs every step
    so it catches breaks that happen mid-loop (crash in tool execution,
    timeout, etc.).
    """

    _stats_lock = threading.Lock()
    _stats = {"repairs": 0, "patched_calls": 0}

    @classmethod
    def get_stats(cls) -> dict:
        with cls._stats_lock:
            return dict(cls._stats)

    def before_model(self, ctx: InvocationContext, messages: list, step: int) -> list | None:
        existing_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                if tc_id:
                    existing_ids.add(tc_id)

        needs_patch = False
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_ids:
                    needs_patch = True
                    break
            if needs_patch:
                break

        if not needs_patch:
            return None

        patched: list[dict] = []
        patched_ids: set[str] = set()
        patch_count = 0

        for msg in messages:
            patched.append(msg)
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls") or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_ids and tc_id not in patched_ids:
                    patched.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": tc.get("function", {}).get("name", "unknown"),
                        "content": "[Tool call was interrupted and did not return a result.]",
                    })
                    patched_ids.add(tc_id)
                    patch_count += 1

        if patch_count:
            log.warning("DanglingToolCallRepair: patched %d orphan(s) at step %d",
                        patch_count, step)
            with self._stats_lock:
                self._stats["repairs"] += 1
                self._stats["patched_calls"] += patch_count

        return patched


# ---------------------------------------------------------------------------
# 8. SubagentLimitMiddleware  (after_model)
#    Inspired by DeerFlow's SubagentLimitMiddleware.
#    Truncates excess parallel delegate_task calls from a single LLM response
#    to prevent resource exhaustion.
# ---------------------------------------------------------------------------


class SubagentLimitMiddleware(Middleware):
    """Truncate excess parallel subagent (delegate_task) calls.

    When the LLM generates more delegate_task tool calls than allowed in
    a single response, this middleware keeps only the first N and removes
    the rest.  Enforced at the model-response level, more reliable than
    prompt-based limits.
    """

    MIN_LIMIT = 2
    MAX_LIMIT = 5

    def __init__(self, max_concurrent: int = 3):
        self._max = max(self.MIN_LIMIT, min(self.MAX_LIMIT, max_concurrent))

    def after_model(self, ctx: InvocationContext, messages: list, response_msg: dict, step: int) -> dict | None:
        tool_calls = response_msg.get("tool_calls")
        if not tool_calls:
            return None

        delegate_indices = [
            i for i, tc in enumerate(tool_calls)
            if tc.get("function", {}).get("name") == "delegate_task"
        ]
        if len(delegate_indices) <= self._max:
            return None

        drop = set(delegate_indices[self._max:])
        truncated = [tc for i, tc in enumerate(tool_calls) if i not in drop]
        dropped = len(drop)
        log.warning("SubagentLimit: truncated %d excess delegate_task call(s) at step %d",
                    dropped, step)

        updated = dict(response_msg)
        updated["tool_calls"] = truncated
        return updated


# ---------------------------------------------------------------------------
# 9. ContextSummarizationMiddleware  (before_model)
#    Proactively summarize long conversations BEFORE the LLM call, so the
#    engine's emergency compaction is a last resort instead of the norm.
# ---------------------------------------------------------------------------


_SUMMARIZATION_TOKEN_THRESHOLD = 60_000  # trigger proactive summarization
_MIN_MESSAGES_FOR_SUMMARIZATION = 25


class ContextSummarizationMiddleware(Middleware):
    """Proactively summarize conversation when context grows too large.

    Runs before each LLM call.  When estimated tokens exceed the threshold
    and there are enough messages, builds a deterministic summary of older
    messages and replaces them with a compact context summary.

    This is complementary to the engine's built-in compaction (which kicks
    in at 80k tokens or 30 messages).  By acting earlier and at a lower
    threshold, we avoid hitting the engine's emergency path.
    """

    def __init__(self, token_threshold: int = _SUMMARIZATION_TOKEN_THRESHOLD,
                 min_messages: int = _MIN_MESSAGES_FOR_SUMMARIZATION):
        self._threshold = token_threshold
        self._min_msgs = min_messages

    def before_model(self, ctx: InvocationContext, messages: list, step: int) -> list | None:
        if len(messages) < self._min_msgs:
            return None

        est_tokens = self._estimate_tokens(messages)
        if est_tokens < self._threshold:
            return None

        return self._summarize(messages, step)

    @staticmethod
    def _estimate_tokens(messages: list) -> int:
        total = 0
        for m in messages:
            content = m.get("content") or ""
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += len(str(part.get("text", "")))
        return total // 4

    def _summarize(self, messages: list, step: int) -> list:
        system_msg = messages[0]
        recent_count = min(15, len(messages) // 2)
        recent = messages[-recent_count:]
        old = messages[1:-recent_count]
        if not old:
            return messages

        user_msg = None
        user_idx = None
        for i, m in enumerate(old):
            if m.get("role") == "user" and "[Context Summary" not in (m.get("content") or ""):
                user_msg = m
                user_idx = i

        summary_parts = []
        tool_names_seen: set[str] = set()
        assistant_count = 0
        user_count = 0

        for m in old:
            role = m.get("role", "")
            if role == "assistant":
                assistant_count += 1
                for tc in m.get("tool_calls") or []:
                    name = tc.get("function", {}).get("name", "")
                    if name:
                        tool_names_seen.add(name)
            elif role == "user":
                user_count += 1
            elif role == "tool":
                content = m.get("content") or ""
                if len(content) > 200:
                    name = m.get("name", "tool")
                    first_line = content.split("\n")[0][:150]
                    summary_parts.append(f"  {name}: {first_line}...")

        summary_lines = [
            f"[Context Summary — {len(old)} older messages compacted at step {step}]",
            f"  Turns: {user_count} user, {assistant_count} assistant",
        ]
        if tool_names_seen:
            summary_lines.append(f"  Tools used: {', '.join(sorted(tool_names_seen))}")
        if summary_parts:
            summary_lines.append("  Key results:")
            summary_lines.extend(summary_parts[:10])

        summary_text = "\n".join(summary_lines)

        result = [system_msg]
        if user_msg:
            result.append(user_msg)
        result.append({"role": "user", "content": summary_text})
        result.extend(recent)

        log.info("ContextSummarization: compacted %d→%d messages at step %d",
                 len(messages), len(result), step)
        return result


# ---------------------------------------------------------------------------
# 10. ToolCallInterceptMiddleware  (wrap_tool_call)
#     Inspired by DeerFlow's ClarificationMiddleware.
#     Generic interceptor that can redirect specific tool calls.
# ---------------------------------------------------------------------------


class ToolCallInterceptMiddleware(Middleware):
    """Intercept specific tool calls and return custom results.

    Supports two modes:
    1. Static intercept: tool_name → fixed result string
    2. Dynamic intercept: tool_name → callable(ctx, tool_name, args) → str

    When a tool call is intercepted, the tool is NOT executed — the
    intercept result is returned directly to the LLM.

    Primary use cases:
    - Clarification: intercept "ask_clarification" to pause the loop
    - Safety: block dangerous tools at a finer grain than ToolScopeMiddleware
    - Mocking: replace real tools with test results during testing
    """

    def __init__(self, intercepts: dict[str, str | callable] | None = None):
        self._intercepts: dict[str, str | callable] = dict(intercepts or {})

    def register(self, tool_name: str, handler: str | callable) -> None:
        """Register an intercept for a tool name."""
        self._intercepts[tool_name] = handler

    def unregister(self, tool_name: str) -> None:
        """Remove an intercept."""
        self._intercepts.pop(tool_name, None)

    def wrap_tool_call(self, ctx: InvocationContext, tool_name: str, args: dict, step: int) -> str | None:
        handler = self._intercepts.get(tool_name)
        if handler is None:
            return None

        log.info("ToolCallIntercept: intercepting %s at step %d", tool_name, step)
        if callable(handler):
            try:
                return handler(ctx, tool_name, args)
            except Exception as exc:
                log.error("ToolCallIntercept handler for %s failed: %s",
                          tool_name, exc, exc_info=True)
                return f"Intercept error: {exc}"
        return str(handler)


# ===========================================================================
# FACTORY — builds the default chain with all middlewares
# ===========================================================================


def build_default_chain() -> MiddlewareChain:
    """Construct the standard middleware pipeline.

    Order matters:
    1. IdentityMiddleware       — prepend identity to system prompt
    2. SkillMatchMiddleware     — match skills, inject prompts
    3. ToolScopeMiddleware      — restrict available tools
    4. CallerContextMiddleware  — set caller context for shell
    5. DanglingToolCallRepairMiddleware  — fix broken history each step
    6. ContextSummarizationMiddleware    — proactive context compaction
    7. SubagentLimitMiddleware  — cap parallel delegate_task calls
    8. GiveUpDetectionMiddleware         — retry on give-up responses
    9. BrowserCleanupMiddleware — cleanup browser after task
    """
    return MiddlewareChain([
        IdentityMiddleware(),
        SkillMatchMiddleware(),
        ToolScopeMiddleware(),
        CallerContextMiddleware(),
        DanglingToolCallRepairMiddleware(),
        ContextSummarizationMiddleware(),
        SubagentLimitMiddleware(),
        GiveUpDetectionMiddleware(),
        BrowserCleanupMiddleware(),
    ])
