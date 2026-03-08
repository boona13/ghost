"""
Ghost Focused Delegation — Fresh-context task execution for verification and research.

Provides a single `delegate_task` tool that runs a focused sub-task with a clean
context window. This solves the context degradation problem where long tool-loop
sessions (50+ steps) lose early file_read details due to message truncation.

Use cases:
  - Verify interface compatibility after evolve_apply (fresh read of dependencies)
  - Research a module's API before writing code that depends on it
  - Summarize large files without polluting the parent's context
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DELEGATE_SYSTEM_PROMPT = (
    "You are a focused research assistant working inside the Ghost codebase. "
    "Your job: complete the task below and return a clear, concise summary.\n\n"
    "RULES:\n"
    "- ONLY read and analyze. Do NOT modify files, run commands, or take actions.\n"
    "- Be precise about method names, signatures, and line numbers.\n"
    "- If you find issues (missing methods, wrong signatures), list them explicitly.\n"
    "- Keep your final response under 2000 characters — the parent agent needs a concise result.\n"
    "- Do NOT explain your process. Just return the findings."
)

READONLY_TOOLS = frozenset({
    "file_read", "grep", "glob", "memory_search",
    "analyze_code_file", "find_code_patterns",
})

MAX_DELEGATE_STEPS = 15
MAX_RESULT_CHARS = 3000


def build_subagent_tools(cfg: Dict[str, Any], tool_registry, skill_loader=None,
                         auth_store=None, provider_chain=None):
    """Build the delegate_task tool for focused, fresh-context sub-tasks."""

    def delegate_task(task: str, max_steps: int = MAX_DELEGATE_STEPS, **kwargs):
        """
        Run a focused research task with a fresh context window.

        Spawns a short-lived LLM session with read-only tools (file_read, grep,
        glob, memory_search) and returns the result. Use this when you need
        accurate information that may have been lost to context truncation.

        Args:
            task: Clear description of what to research or verify.
            max_steps: Max tool-loop steps (default 15, max 25).

        Returns:
            Dict with success status and the delegate's findings.
        """
        from ghost_loop import ToolLoopEngine

        if not task or not task.strip():
            return {"error": "Task description is required."}

        max_steps = min(max(1, max_steps), 25)

        readonly_registry = tool_registry.subset(
            [name for name in tool_registry.names() if name in READONLY_TOOLS]
        )

        if not readonly_registry.names():
            return {"error": "No read-only tools available for delegation."}

        api_key = None
        if auth_store:
            try:
                api_key = auth_store.get_api_key("openrouter")
            except (AttributeError, TypeError):
                pass
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return {"error": "No API key available for delegate task."}

        model = cfg.get("model", "anthropic/claude-sonnet-4")

        engine = ToolLoopEngine(
            api_key=api_key,
            model=model,
            fallback_models=cfg.get("fallback_models", []),
            auth_store=auth_store,
            provider_chain=provider_chain,
        )

        start = time.time()
        try:
            result = engine.run(
                system_prompt=DELEGATE_SYSTEM_PROMPT,
                user_message=task.strip(),
                tool_registry=readonly_registry,
                max_steps=max_steps,
                temperature=0.2,
                max_tokens=2048,
            )

            duration_ms = int((time.time() - start) * 1000)
            text = (result.text or "").strip()
            if len(text) > MAX_RESULT_CHARS:
                text = text[:MAX_RESULT_CHARS] + "\n... [truncated]"

            log.info("delegate_task completed in %dms (%d steps, %d tokens): %s...",
                     duration_ms, result.steps, result.total_tokens, task[:60])

            return {
                "success": True,
                "result": text,
                "steps_used": result.steps,
                "duration_ms": duration_ms,
            }

        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            log.warning("delegate_task failed after %dms: %s", duration_ms, exc)
            return {"error": f"Delegation failed: {type(exc).__name__}: {str(exc)}"}

    return [{
        "name": "delegate_task",
        "description": (
            "Run a focused research or verification task with a fresh context window. "
            "Use this when you need accurate information from files that may have been "
            "lost to context truncation (e.g., verifying method signatures on imported "
            "classes after a long evolve session). The delegate has read-only access to "
            "file_read, grep, glob, and memory_search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Clear description of what to research or verify. "
                        "Be specific: include file paths, class names, and what to check."
                    ),
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Max tool-loop steps (default 15, max 25).",
                    "default": 15,
                },
            },
            "required": ["task"],
        },
        "execute": delegate_task,
    }]
