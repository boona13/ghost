"""
GHOST Tool Loop Engine

Autonomous multi-turn LLM tool calling loop.
The agent keeps going until it decides the task is DONE — like while(true).
Loop detection mirrored from OpenClaw's tool-loop-detection architecture.
"""

import json
import logging
import os
import random
import time
import hashlib
import uuid
import requests
import traceback
from ghost_tool_intent_security import ToolIntentSecurity
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("ghost.loop")


def _build_date_context() -> str:
    """Dynamic date/time context injected into every LLM call.

    Most LLMs are trained on prior-year data and assume it's 2025.
    This corrects that by prepending the actual current date.
    """
    now = datetime.now()
    utc = datetime.now(timezone.utc)
    return (
        f"## CURRENT DATE & TIME\n"
        f"Today is **{now.strftime('%A, %B %d, %Y')}** "
        f"(ISO: {now.strftime('%Y-%m-%d')}, {now.strftime('%I:%M %p')} local, "
        f"{utc.strftime('%H:%M')} UTC). "
        f"The current year is **{now.year}**, NOT {now.year - 1}. "
        f"Use {now.year} in all searches, dates, and references.\n\n"
    )

MAX_RETRIES = 2
RETRY_DELAY = 1.5
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TOOL_RESULT_LIMIT = 6000
DEFAULT_TIMEOUT = 90
DEFAULT_MAX_STEPS = 200
FALLBACK_COOLDOWN_SEC = 300   # 5 min before probing failed model again
FALLBACK_PROBE_INTERVAL = 60  # seconds between probes of a cooled-down model
NETWORK_COOLDOWN_SEC = 15     # short cooldown for DNS/connection errors (transient)
JITTER_FACTOR = 0.3           # ±30% randomness on retry delays

GHOST_HOME = Path.home() / ".ghost"


# ═════════════════════════════════════════════════════════════════════
#  MODEL FALLBACK CHAIN  (inspired by OpenClaw's model-fallback.ts)
# ═════════════════════════════════════════════════════════════════════

class ModelFallbackChain:
    """Provider-aware model fallback with cooldown-aware probing.

    Each entry in the chain is a (provider_id, model) tuple.
    When a model fails, falls through to the next in the chain.
    Periodically probes failed models to detect recovery.
    """

    def __init__(self, primary: str, fallbacks: list[str] | None = None,
                 cooldown_sec: float = FALLBACK_COOLDOWN_SEC,
                 probe_interval: float = FALLBACK_PROBE_INTERVAL,
                 provider_chain: list[tuple[str, str]] | None = None):
        if provider_chain:
            self._chain: list[tuple[str, str]] = list(provider_chain)
        else:
            self._chain = [("openrouter", m) for m in [primary] + (fallbacks or [])]
        self._cooldown_sec = cooldown_sec
        self._probe_interval = probe_interval
        self._failures: dict[str, float] = {}
        self._last_probe: dict[str, float] = {}
        self._active: tuple[str, str] = self._chain[0] if self._chain else ("openrouter", primary)
        self._stats: dict[str, dict] = {self._key(e): {"ok": 0, "fail": 0} for e in self._chain}

    @staticmethod
    def _key(entry: tuple[str, str]) -> str:
        return f"{entry[0]}:{entry[1]}"

    @property
    def primary(self) -> str:
        return self._chain[0][1] if self._chain else ""

    @primary.setter
    def primary(self, model: str):
        new_entry = ("openrouter", model)
        for i, e in enumerate(self._chain):
            if e[0] == "openrouter" and e[1] == model:
                self._chain.pop(i)
                break
        self._chain.insert(0, new_entry)
        k = self._key(new_entry)
        if k not in self._stats:
            self._stats[k] = {"ok": 0, "fail": 0}
        self._active = new_entry
        self._failures.pop(k, None)

    @property
    def active_model(self) -> str:
        return self._active[1]

    @property
    def active_provider(self) -> str:
        return self._active[0]

    @property
    def chain(self) -> list[str]:
        return [e[1] for e in self._chain]

    @property
    def provider_chain(self) -> list[tuple[str, str]]:
        return list(self._chain)

    def set_provider_chain(self, chain: list[tuple[str, str]]):
        self._chain = list(chain)
        if chain:
            self._active = chain[0]
        for e in chain:
            k = self._key(e)
            if k not in self._stats:
                self._stats[k] = {"ok": 0, "fail": 0}

    @property
    def stats(self) -> dict:
        return {
            "active": f"{self._active[0]}:{self._active[1]}",
            "chain": [f"{e[0]}:{e[1]}" for e in self._chain],
            "failures": {k: round(time.time() - t) for k, t in self._failures.items()},
            "stats": dict(self._stats),
        }

    def _is_in_cooldown(self, key: str) -> bool:
        fail_time = self._failures.get(key)
        if fail_time is None:
            return False
        return (time.time() - fail_time) < self._cooldown_sec

    def _should_probe(self, key: str) -> bool:
        if not self._is_in_cooldown(key):
            return False
        last = self._last_probe.get(key, 0)
        return (time.time() - last) >= self._probe_interval

    def get_candidates(self) -> list[tuple[str, str]]:
        """Return ordered list of (provider, model) to attempt."""
        result = []
        probe_candidates = []

        for entry in self._chain:
            k = self._key(entry)
            if self._is_in_cooldown(k):
                if self._should_probe(k):
                    probe_candidates.append(entry)
            else:
                result.append(entry)

        if probe_candidates and result:
            result = result[:1] + probe_candidates + result[1:]
        elif probe_candidates:
            result = probe_candidates

        return result if result else list(self._chain)

    # Keep legacy method for backward compat
    def get_models_to_try(self) -> list[str]:
        return [e[1] for e in self.get_candidates()]

    def record_success(self, provider: str, model: str):
        k = f"{provider}:{model}"
        self._stats.setdefault(k, {"ok": 0, "fail": 0})
        self._stats[k]["ok"] += 1
        self._failures.pop(k, None)
        self._active = (provider, model)

    @staticmethod
    def _is_network_error(error: str) -> bool:
        """Detect transient DNS/connection failures vs real model errors."""
        network_markers = (
            "NameResolutionError", "Failed to resolve", "nodename nor servname",
            "ConnectionRefusedError", "ConnectionResetError", "ConnectionError",
            "Max retries exceeded", "NewConnectionError", "gaierror",
        )
        return any(m in error for m in network_markers)

    def record_failure(self, provider: str, model: str, error: str = ""):
        k = f"{provider}:{model}"
        self._stats.setdefault(k, {"ok": 0, "fail": 0})
        self._stats[k]["fail"] += 1
        if self._is_network_error(error):
            self._failures[k] = time.time() - (self._cooldown_sec - NETWORK_COOLDOWN_SEC)
            log.warning("%s:%s network error (%s), short cooldown %ds",
                        provider, model, error[:80], NETWORK_COOLDOWN_SEC)
        else:
            self._failures[k] = time.time()
            log.warning("%s:%s failed (%s), entering cooldown %ds",
                        provider, model, error[:80], int(self._cooldown_sec))
        self._last_probe[k] = time.time()

    def remove_from_chain(self, provider: str, model: str):
        """Permanently remove a model from the fallback chain (for 404 errors)."""
        entry = (provider, model)
        if entry in self._chain:
            self._chain.remove(entry)
            log.warning("Removed %s:%s from fallback chain (invalid model ID)", provider, model)
        # Also clean up failure tracking
        k = self._key(entry)
        self._failures.pop(k, None)
        self._last_probe.pop(k, None)


def _jittered_delay(base: float, attempt: int) -> float:
    """Exponential backoff with jitter: base * (attempt+1) * (1 ± JITTER_FACTOR)."""
    delay = base * (attempt + 1)
    jitter = delay * JITTER_FACTOR * (2 * random.random() - 1)
    return max(0.5, delay + jitter)
DEBUG_LOG_DIR = GHOST_HOME / "logs"
DEBUG_LOG_FILE = DEBUG_LOG_DIR / "tool_loop_debug.jsonl"
MAX_DEBUG_LOG_SIZE = 10 * 1024 * 1024  # 10MB before rotation


class ToolLoopDebugLogger:
    """Persistent JSONL logger for every tool loop session and step."""

    def __init__(self):
        self._session_id = None
        self._session_start = None
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _rotate_if_needed(self):
        """Rotate log files: keep current + up to 5 backups (.1 through .5)."""
        try:
            if DEBUG_LOG_FILE.exists() and DEBUG_LOG_FILE.stat().st_size > MAX_DEBUG_LOG_SIZE:
                # Rotate existing backups: .4 -> .5, .3 -> .4, .2 -> .3, .1 -> .2
                for i in range(4, 0, -1):
                    old = DEBUG_LOG_DIR / f"tool_loop_debug.jsonl.{i}"
                    new = DEBUG_LOG_DIR / f"tool_loop_debug.jsonl.{i+1}"
                    if old.exists():
                        old.rename(new)
                # Rotate current file to .1
                DEBUG_LOG_FILE.rename(DEBUG_LOG_DIR / "tool_loop_debug.jsonl.1")
        except Exception:
            pass

    def _write(self, record: dict):
        try:
            self._rotate_if_needed()
            with open(str(DEBUG_LOG_FILE), "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass

    def session_start(self, user_message: str, model: str, max_steps: int, caller: str = ""):
        self._session_id = uuid.uuid4().hex[:12]
        self._session_start = time.time()
        self._write({
            "event": "session_start",
            "session_id": self._session_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "user_message": user_message[:500],
            "model": model,
            "max_steps": max_steps,
            "caller": caller,
        })
        return self._session_id

    def step_tool_call(self, step: int, tool_name: str, args: dict, result: str,
                       duration_ms: float = 0, loop_detection: str = ""):
        self._write({
            "event": "tool_call",
            "session_id": self._session_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "step": step,
            "tool": tool_name,
            "args_summary": self._summarize_args(args),
            "result_preview": result[:300] if result else "",
            "result_length": len(result) if result else 0,
            "duration_ms": round(duration_ms),
            "loop_detection": loop_detection,
        })

    def step_text_response(self, step: int, text: str, action_taken: str):
        self._write({
            "event": "text_response",
            "session_id": self._session_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "step": step,
            "text_preview": text[:300] if text else "",
            "text_length": len(text) if text else 0,
            "action": action_taken,
        })

    def step_error(self, step: int, error: str):
        self._write({
            "event": "error",
            "session_id": self._session_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "step": step,
            "error": error[:500],
        })

    def session_end(self, steps_used: int, tools_used: list, total_tokens: int,
                    exit_reason: str, final_text: str = ""):
        elapsed = time.time() - self._session_start if self._session_start else 0
        self._write({
            "event": "session_end",
            "session_id": self._session_id,
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "steps_used": steps_used,
            "tools_used": tools_used,
            "total_tokens": total_tokens,
            "elapsed_seconds": round(elapsed, 1),
            "exit_reason": exit_reason,
            "final_text_preview": final_text[:300] if final_text else "",
        })

    @staticmethod
    def _summarize_args(args: dict) -> str:
        if not args:
            return "{}"
        summary = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 100:
                summary[k] = v[:80] + f"...({len(v)} chars)"
            elif isinstance(v, (list, dict)):
                s = json.dumps(v, default=str)
                summary[k] = s[:80] + "..." if len(s) > 80 else s
            else:
                summary[k] = v
        return json.dumps(summary, default=str)


_debug_logger = ToolLoopDebugLogger()

KNOWN_POLL_TOOLS = {"shell_exec", "browser"}
KNOWN_POLL_ACTIONS = {"snapshot", "content", "screenshot", "poll", "log", "status"}
WARNING_BUCKET_SIZE = 10

def _check_incomplete_workflows(tool_calls_log: list) -> str | None:
    """Check if any tool workflows are incomplete. Returns a message if so, None if OK."""
    tools_used = {tc["tool"] for tc in tool_calls_log}

    started_feature = "start_future_feature" in tools_used
    used_evolve_plan = "evolve_plan" in tools_used
    used_evolve_apply = "evolve_apply" in tools_used
    used_evolve_deploy = "evolve_deploy" in tools_used or "evolve_submit_pr" in tools_used
    used_fail = "fail_future_feature" in tools_used

    if used_evolve_plan and not used_evolve_deploy and not used_fail:
        if not used_evolve_apply:
            return (
                "You called evolve_plan but never called evolve_apply. "
                "You MUST apply changes. Call evolve_apply now for each file, "
                "then evolve_test, then evolve_submit_pr. Do NOT rollback or quit."
            )
        return (
            "You started an evolution (evolve_plan + evolve_apply) but never "
            "called evolve_submit_pr. Finish: evolve_test → evolve_submit_pr. "
            "Do NOT call task_complete until evolve_submit_pr succeeds."
        )

    if started_feature and not used_evolve_plan and not used_fail:
        return (
            "You called start_future_feature but never called evolve_plan. "
            "You MUST implement the feature NOW. Call evolve_plan, then "
            "evolve_apply, evolve_test, evolve_submit_pr. Do NOT defer to "
            "'the next run'. There is no next run — do it now."
        )

    return None


@dataclass
class LoopDetectionConfig:
    enabled: bool = True
    history_size: int = 30
    warning_threshold: int = 10
    critical_threshold: int = 20
    global_circuit_breaker: int = 30
    detectors: dict = field(default_factory=lambda: {
        "generic_repeat": True,
        "known_poll_no_progress": True,
        "ping_pong": True,
    })


@dataclass
class LoopDetectionResult:
    stuck: bool = False
    level: str = ""
    detector: str = ""
    count: int = 0
    message: str = ""


class LoopDetector:
    """Advanced loop detection mirrored from OpenClaw's detector priority chain.

    Detectors (checked in order, first match wins):
    1. global_circuit_breaker — any tool no-progress streak >= 30 -> block
    2. known_poll_no_progress (critical) — poll tools streak >= 20 -> block
    3. known_poll_no_progress (warning) — poll tools streak >= 10 -> warn
    4. ping_pong (critical) — A-B-A-B with no-progress evidence >= 20 -> block
    5. ping_pong (warning) — A-B-A-B >= 10 -> warn
    6. generic_repeat — non-poll tools repeated >= 10 -> warn only
    """

    def __init__(self, cfg: LoopDetectionConfig = None):
        self._cfg = cfg or LoopDetectionConfig()
        self._history: list[dict] = []
        self._warning_buckets: dict[str, int] = {}
        self._call_counter = 0

    @staticmethod
    def _hash_args(tool_name, args):
        raw = json.dumps(args, sort_keys=True, default=str)
        return f"{tool_name}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    @staticmethod
    def _hash_result(result):
        if not result:
            return "empty"
        return hashlib.sha256(result.encode()).hexdigest()[:16]

    @staticmethod
    def _is_poll_tool(tool_name, args):
        if tool_name in KNOWN_POLL_TOOLS:
            return True
        action = args.get("action", "") if isinstance(args, dict) else ""
        return action in KNOWN_POLL_ACTIONS

    def record_call(self, tool_name, args):
        """Phase 1: record the call BEFORE execution. Returns a call_id for patching result later."""
        call_id = f"lc_{self._call_counter}"
        self._call_counter += 1
        entry = {
            "id": call_id,
            "tool": tool_name,
            "call_hash": self._hash_args(tool_name, args),
            "result_hash": None,
            "ts": time.time(),
        }
        self._history.append(entry)
        if len(self._history) > self._cfg.history_size:
            self._history.pop(0)
        return call_id

    def record_result(self, call_id, result):
        """Phase 2: patch the result hash AFTER execution."""
        result_str = result if isinstance(result, str) else json.dumps(result, default=str)
        rh = self._hash_result(result_str)
        for entry in reversed(self._history):
            if entry["id"] == call_id:
                entry["result_hash"] = rh
                break

    def check(self, tool_name, args) -> LoopDetectionResult:
        """Run the full detector priority chain. Returns detection result."""
        if not self._cfg.enabled:
            return LoopDetectionResult()

        call_hash = self._hash_args(tool_name, args)
        is_poll = self._is_poll_tool(tool_name, args)
        detectors = self._cfg.detectors

        streak = self._get_no_progress_streak(call_hash)

        if streak >= self._cfg.global_circuit_breaker:
            return LoopDetectionResult(
                stuck=True, level="critical", detector="global_circuit_breaker",
                count=streak,
                message=(
                    f"BLOCKED: {tool_name} called {streak} times with identical arguments and no progress. "
                    "You are completely stuck. STOP calling this tool and try a fundamentally different approach, "
                    "or give up on this sub-task and move on."
                ),
            )

        if detectors.get("known_poll_no_progress") and is_poll:
            if streak >= self._cfg.critical_threshold:
                return LoopDetectionResult(
                    stuck=True, level="critical", detector="known_poll_no_progress",
                    count=streak,
                    message=(
                        f"BLOCKED: {tool_name} polled {streak} times with no change in output. "
                        "The operation is stuck or complete. Stop polling and try a different approach."
                    ),
                )
            if streak >= self._cfg.warning_threshold:
                return LoopDetectionResult(
                    stuck=True, level="warning", detector="known_poll_no_progress",
                    count=streak,
                    message=(
                        f"WARNING: {tool_name} polled {streak} times with identical results. "
                        "Consider stopping or trying a different approach."
                    ),
                )

        if detectors.get("ping_pong"):
            pp_count, pp_no_progress = self._get_ping_pong_streak(call_hash)
            if pp_count >= self._cfg.critical_threshold and pp_no_progress:
                return LoopDetectionResult(
                    stuck=True, level="critical", detector="ping_pong",
                    count=pp_count,
                    message=(
                        f"BLOCKED: You're alternating between two tool calls ({pp_count} times) "
                        "with no progress on either side. This ping-pong pattern is not productive. "
                        "Try a completely different approach."
                    ),
                )
            if pp_count >= self._cfg.warning_threshold:
                return LoopDetectionResult(
                    stuck=True, level="warning", detector="ping_pong",
                    count=pp_count,
                    message=(
                        f"WARNING: Ping-pong pattern detected — alternating between two calls "
                        f"({pp_count} times). Consider a different strategy."
                    ),
                )

        if detectors.get("generic_repeat") and not is_poll:
            repeat_count = sum(1 for h in self._history if h["call_hash"] == call_hash)
            if repeat_count >= self._cfg.critical_threshold:
                return LoopDetectionResult(
                    stuck=True, level="critical", detector="generic_repeat",
                    count=repeat_count,
                    message=(
                        f"BLOCKED: {tool_name} called {repeat_count} times with identical arguments. "
                        "You are stuck in a loop. STOP calling this tool and try a completely "
                        "different approach, or call task_complete to finish."
                    ),
                )
            if repeat_count >= self._cfg.warning_threshold:
                return LoopDetectionResult(
                    stuck=True, level="warning", detector="generic_repeat",
                    count=repeat_count,
                    message=(
                        f"WARNING: {tool_name} called {repeat_count} times with identical arguments. "
                        "The repeated calls may not be productive. Try a different approach."
                    ),
                )

        return LoopDetectionResult()

    def should_emit_warning(self, detector: str, count: int) -> bool:
        """Bucket-based deduplication: emit once per bucket of WARNING_BUCKET_SIZE."""
        bucket = count // WARNING_BUCKET_SIZE
        key = detector
        last_bucket = self._warning_buckets.get(key, -1)
        if bucket > last_bucket:
            self._warning_buckets[key] = bucket
            return True
        return False

    def _get_no_progress_streak(self, call_hash: str) -> int:
        """Walk backward counting consecutive entries with same call_hash AND same result_hash."""
        streak = 0
        last_result = None
        for entry in reversed(self._history):
            if entry["call_hash"] != call_hash:
                continue
            rh = entry.get("result_hash")
            if rh is None:
                continue
            if last_result is None:
                last_result = rh
                streak = 1
            elif rh == last_result:
                streak += 1
            else:
                break
        return streak

    def _get_ping_pong_streak(self, proposed_hash: str) -> tuple[int, bool]:
        """Detect A-B-A-B alternation. Returns (streak_count, no_progress_evidence)."""
        if len(self._history) < 2:
            return 0, False

        other_hash = None
        for entry in reversed(self._history):
            if entry["call_hash"] != proposed_hash:
                other_hash = entry["call_hash"]
                break
        if not other_hash:
            return 0, False

        pattern = [proposed_hash, other_hash]
        streak = 1
        side_a_results = set()
        side_b_results = set()

        for i, entry in enumerate(reversed(self._history)):
            expected = pattern[i % 2]
            if i == 0 and entry["call_hash"] == proposed_hash:
                if entry.get("result_hash"):
                    side_a_results.add(entry["result_hash"])
                streak = 1
                continue
            if entry["call_hash"] != expected:
                break
            streak += 1
            rh = entry.get("result_hash")
            if rh:
                if entry["call_hash"] == proposed_hash:
                    side_a_results.add(rh)
                else:
                    side_b_results.add(rh)

        no_progress = (len(side_a_results) <= 1 and len(side_b_results) <= 1
                       and len(side_a_results) + len(side_b_results) > 0)
        return streak, no_progress


class ToolLoopEngine:
    """Autonomous multi-turn LLM <-> tool execution loop."""

    def __init__(self, api_key, model, base_url="https://openrouter.ai/api/v1/chat/completions",
                 fallback_models=None, auth_store=None, provider_chain=None, usage_tracker=None):
        self._api_key = api_key
        self._model = model
        self.base_url = base_url
        self._auth_store = auth_store
        self._usage_tracker = usage_tracker
        self._fallback_chain = ModelFallbackChain(
            model, fallback_models or [],
            provider_chain=provider_chain,
        )

    @property
    def api_key(self):
        return self._api_key

    @api_key.setter
    def api_key(self, value):
        self._api_key = value

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value
        self._fallback_chain.primary = value

    @property
    def fallback_chain(self) -> ModelFallbackChain:
        return self._fallback_chain

    @property
    def _headers(self):
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ghost-ai",
            "X-Title": "Ghost AI Agent",
        }

    def _request_summary(self, messages, temperature, max_tokens):
        """When the loop ends without a text response, ask the LLM to summarize what it did."""
        summary_msgs = list(messages)
        summary_msgs.append({
            "role": "user",
            "content": (
                "You've completed your tool calls. Now provide a clear, concise final response "
                "summarizing what you found and what you did. Do NOT call any tools — "
                "just respond with your final answer in plain text."
            ),
        })
        payload = {
            "model": self.model,
            "messages": summary_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data, error = self._call_llm(payload)
        if error:
            return self._summarize_from_logs(messages)
        choices = data.get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "").strip()
            if text:
                return text
        return self._summarize_from_logs(messages)

    def _summarize_from_logs(self, messages):
        """Last-resort: extract the last meaningful tool result as the response."""
        for msg in reversed(messages):
            if msg.get("role") == "tool":
                content = msg.get("content", "").strip()
                if content and len(content) > 20 and not content.startswith("OK, continuing"):
                    return content
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return "(Task completed — results were delivered through tool actions above)"

    def _resolve_provider_call(self, provider_id: str, model: str, payload: dict):
        """Resolve base_url, headers, and adapted payload for a provider."""
        try:
            from ghost_providers import get_provider, build_headers, adapt_request
        except ImportError:
            return self.base_url, self._headers, dict(payload, model=model)

        provider = get_provider(provider_id)
        if not provider:
            return self.base_url, self._headers, dict(payload, model=model)

        api_key = ""
        account_id = ""
        if self._auth_store:
            if provider_id == "openai-codex":
                try:
                    from ghost_oauth import ensure_fresh_token
                    api_key = ensure_fresh_token(self._auth_store) or ""
                except Exception:
                    api_key = self._auth_store.get_api_key(provider_id)
                profile = self._auth_store.get_provider_profile(provider_id)
                if profile:
                    account_id = profile.get("account_id", "")
            else:
                api_key = self._auth_store.get_api_key(provider_id)

        if not api_key and provider_id == "openrouter":
            api_key = self._api_key

        headers = build_headers(provider, api_key)
        if provider_id == "openai-codex" and account_id:
            headers["ChatGPT-Account-Id"] = account_id

        adapted = adapt_request(provider, dict(payload, model=model))

        return provider.base_url, headers, adapted

    def _call_llm(self, payload, timeout=DEFAULT_TIMEOUT):
        """Make an LLM API call with provider-aware fallback chain and jittered retry.

        Flow:  for each (provider, model) in fallback chain →
                 resolve base_url, headers, adapted payload →
                 for each retry attempt →
                   call API, handle errors
               on success → adapt response, record_success, return
               on retriable failure → jittered backoff, next attempt
               on exhausted retries → record_failure, try next candidate
        """
        candidates = self._fallback_chain.get_candidates()
        all_errors = []

        for provider_id, model in candidates:
            url, headers, adapted_payload = self._resolve_provider_call(
                provider_id, model, payload
            )

            is_codex_stream = provider_id == "openai-codex"

            last_err = None
            # Notify usage tracker that call is starting
            if self._usage_tracker:
                self._usage_tracker.call_started(provider_id, model)

            for attempt in range(MAX_RETRIES + 1):
                try:
                    if is_codex_stream and attempt == 0:
                        log.debug("Codex request to %s | keys: %s", url, list(adapted_payload.keys()))

                    resp = requests.post(
                        url, json=adapted_payload,
                        headers=headers, timeout=timeout,
                        stream=is_codex_stream,
                    )
                    if resp.status_code == 429:
                        wait = _jittered_delay(RETRY_DELAY, attempt)
                        log.info("Rate-limited on %s:%s, waiting %.1fs (attempt %d)",
                                 provider_id, model, wait, attempt + 1)
                        time.sleep(wait)
                        last_err = f"HTTP 429 on {provider_id}:{model}"
                        continue

                    if is_codex_stream and resp.status_code != 200:
                        body = resp.text[:500]
                        log.error("Codex %s:%s returned HTTP %d: %s | Payload keys: %s",
                                  provider_id, model, resp.status_code, body,
                                  list(adapted_payload.keys()))
                        last_err = f"HTTP {resp.status_code} on {provider_id}:{model}: {body[:100]}"
                        break

                    resp.raise_for_status()

                    if is_codex_stream:
                        try:
                            from ghost_providers import parse_codex_sse_response, adapt_response, get_provider
                            raw = parse_codex_sse_response(resp)
                            provider = get_provider(provider_id)
                            data = adapt_response(provider, raw) if provider else raw
                        except RuntimeError as stream_err:
                            last_err = f"Codex stream error on {provider_id}:{model}: {stream_err}"
                            break
                    else:
                        data = resp.json()
                        try:
                            from ghost_providers import get_provider, adapt_response
                            provider = get_provider(provider_id)
                            if provider:
                                data = adapt_response(provider, data)
                        except ImportError:
                            pass

                    self._fallback_chain.record_success(provider_id, model)
                    primary = self._fallback_chain._chain[0] if self._fallback_chain._chain else None
                    if primary and (provider_id, model) != primary:
                        log.info("Served by fallback: %s:%s", provider_id, model)
                    
                    # Extract and report token usage
                    if self._usage_tracker:
                        usage = data.get("usage", {}) if isinstance(data, dict) else {}
                        total_tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
                        self._usage_tracker.call_completed(total_tokens, success=True)
                    
                    return data, None

                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code if e.response else 0
                    body = e.response.text[:300] if e.response else str(e)
                    # 404 = model not found (permanent error) - remove from chain
                    if status == 404:
                        log.warning("Model %s:%s returned 404 (invalid model ID), removing from chain", provider_id, model)
                        self._fallback_chain.remove_from_chain(provider_id, model)
                        last_err = f"HTTP 404 on {provider_id}:{model}: invalid model ID"
                        break
                    if status in (429, 500, 502, 503) and attempt < MAX_RETRIES:
                        wait = _jittered_delay(RETRY_DELAY, attempt)
                        time.sleep(wait)
                        last_err = f"HTTP {status} on {provider_id}:{model}: {body[:100]}"
                        continue
                    last_err = f"HTTP {status} on {provider_id}:{model}: {body[:100]}"
                    break
                except requests.exceptions.Timeout:
                    if attempt < MAX_RETRIES:
                        time.sleep(_jittered_delay(RETRY_DELAY, attempt))
                        last_err = f"Timeout on {provider_id}:{model}"
                        continue
                    last_err = f"Timeout on {provider_id}:{model} after retries"
                    break
                except requests.exceptions.ConnectionError as e:
                    if attempt < MAX_RETRIES:
                        time.sleep(_jittered_delay(RETRY_DELAY, attempt))
                        last_err = f"Connection error on {provider_id}:{model}: {str(e)[:80]}"
                        continue
                    last_err = f"Connection error on {provider_id}:{model} after retries: {str(e)[:80]}"
                    break
                except Exception as e:
                    last_err = f"Error on {provider_id}:{model}: {e}"
                    break

            # Report call failure to usage tracker
            if self._usage_tracker:
                self._usage_tracker.call_completed(0, success=False)

            self._fallback_chain.record_failure(provider_id, model, last_err or "unknown")
            all_errors.append(last_err or f"{provider_id}:{model} failed")

        error_summary = " → ".join(all_errors)
        return None, f"All models failed: {error_summary}"

    def run(self, system_prompt, user_message, tool_registry=None,
            max_steps=DEFAULT_MAX_STEPS, temperature=0.3, max_tokens=DEFAULT_MAX_TOKENS,
            image_b64=None, images=None, on_step=None, force_tool=False, history=None,
            cancel_check=None, hook_runner=None, tool_intent_security=None):
        """
        Run the autonomous tool loop.

        The agent keeps calling tools until it decides the task is complete
        and responds with a final text message. Like while(true) { work(); if done break; }

        Args:
            system_prompt: System message for the LLM.
            user_message: The user's input text.
            tool_registry: ToolRegistry instance (or None for single-shot).
            max_steps: Safety limit on max rounds (default 20).
            temperature: LLM temperature.
            max_tokens: Max tokens per LLM response.
            image_b64: Optional single base64-encoded image (legacy, use `images` instead).
            images: Optional list of image dicts: [{"data": "base64...", "mime": "image/png"}, ...]
            on_step: Optional callback(step_num, tool_name, tool_result).
            force_tool: If True, force tool use on step 0.
            history: Optional list of prior conversation turns
                     [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

        Returns:
            ToolLoopResult with final text, tool calls made, and token usage.
        """
        date_context = _build_date_context()
        messages = [{"role": "system", "content": date_context + system_prompt}]

        if history:
            messages.extend(history)

        all_images = list(images or [])
        if image_b64 and not all_images:
            all_images.append({"data": image_b64, "mime": "image/png"})

        if all_images:
            content_parts = [{"type": "text", "text": user_message}]
            for img in all_images:
                mime = img.get("mime", "image/png")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img['data']}"}
                })
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user_message})

        tools_schema = None
        if tool_registry and tool_registry.get_all():
            tools_schema = tool_registry.to_openai_schema()

        TASK_COMPLETE_TOOL = {
            "type": "function",
            "function": {
                "name": "task_complete",
                "description": (
                    "Call this when the task is FULLY complete and you want to send "
                    "your final response to the user. You MUST call this to end your turn — "
                    "do NOT respond with a plain text message. Put your full final response "
                    "in the 'summary' parameter. If you used evolve tools, you must have "
                    "called evolve_submit_pr (or evolve_deploy for self-repair) before calling this."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Your final response to the user summarizing what you did",
                        },
                    },
                    "required": ["summary"],
                },
            },
        }
        if tools_schema:
            tools_schema.append(TASK_COMPLETE_TOOL)

        tool_calls_log = []
        total_tokens = 0
        final_text = ""
        consecutive_errors = 0
        loop_detector = LoopDetector()
        critical_blocks = 0
        MAX_CRITICAL_BLOCKS = 3
        exit_reason = "max_steps"

        _debug_logger.session_start(
            user_message=user_message[:500] if isinstance(user_message, str) else str(user_message)[:500],
            model=self.model,
            max_steps=max_steps,
            caller=traceback.extract_stack()[-2].name if len(traceback.extract_stack()) >= 2 else "",
        )

        consecutive_task_completes = 0
        MAX_CONSECUTIVE_TASK_COMPLETES = 3

        tool_intent_security = tool_intent_security or ToolIntentSecurity({"enable_tool_intent_security": False})

        for step in range(max_steps):
            if cancel_check and cancel_check():
                final_text = "(Stopped by user)"
                exit_reason = "cancelled"
                break

            if consecutive_task_completes >= MAX_CONSECUTIVE_TASK_COMPLETES:
                _debug_logger.step_error(step,
                    f"Circuit breaker: task_complete accepted {consecutive_task_completes}x but loop continued")
                exit_reason = "task_complete"
                break

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            is_last_step = (step == max_steps - 1)

            if tools_schema and not is_last_step:
                payload["tools"] = tools_schema
                if step == 0 and force_tool:
                    payload["tool_choice"] = "required"
                else:
                    payload["tool_choice"] = "auto"

            data, error = self._call_llm(payload)

            if cancel_check and cancel_check():
                final_text = "(Stopped by user)"
                exit_reason = "cancelled"
                break

            if error:
                consecutive_errors += 1
                _debug_logger.step_error(step, f"LLM error ({consecutive_errors}/3): {error}")
                if consecutive_errors >= 3:
                    final_text = error
                    exit_reason = "llm_error"
                    break
                messages.append({"role": "assistant", "content": f"(Internal error: {error}. Retrying...)"})
                time.sleep(1)
                continue

            consecutive_errors = 0
            usage = data.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)

            choices = data.get("choices", [])
            if not choices:
                final_text = "LLM returned no choices"
                break

            choice = choices[0]
            msg = choice["message"]

            messages.append(msg)

            if msg.get("tool_calls") and tool_registry:
                for tc in msg["tool_calls"]:
                    fn_name = str(tc.get("function", {}).get("name", "")).strip()
                    raw_args = tc.get("function", {}).get("arguments", "{}")
                    try:
                        fn_args = json.loads(raw_args) if raw_args else {}
                    except (json.JSONDecodeError, TypeError) as parse_err:
                        fn_args = {"__parse_error": str(parse_err), "__raw_len": len(raw_args) if raw_args else 0}

                    tc_id = tc.get("id", f"tc_{step}_{fn_name}")

                    if fn_name == "task_complete":
                        summary = fn_args.get("summary", "")
                        workflow_issue = _check_incomplete_workflows(tool_calls_log)
                        if workflow_issue:
                            tool_result = (
                                f"REJECTED — you cannot complete yet. {workflow_issue} "
                                "Finish the workflow first, then call task_complete again."
                            )
                            _debug_logger.step_tool_call(step, "task_complete", fn_args,
                                                         f"REJECTED: {workflow_issue}")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": tool_result,
                            })
                            continue
                        final_text = summary
                        exit_reason = "task_complete"
                        consecutive_task_completes += 1
                        _debug_logger.step_tool_call(step, "task_complete", fn_args, "OK")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": "OK, task complete.",
                        })
                        if on_step:
                            try:
                                on_step(step, "task_complete", summary[:200])
                            except Exception:
                                pass
                        break

                    consecutive_task_completes = 0

                    if cancel_check and cancel_check():
                        final_text = "(Stopped by user)"
                        exit_reason = "cancelled"
                        break

                    detection = loop_detector.check(fn_name, fn_args)
                    call_id = loop_detector.record_call(fn_name, fn_args)
                    loop_hint = ""
                    tool_duration_ms = 0

                    if detection.stuck and detection.level == "critical":
                        critical_blocks += 1
                        tool_result = detection.message
                        loop_detector.record_result(call_id, tool_result)
                        loop_hint = f"BLOCKED:{detection.detector}"
                        if critical_blocks >= MAX_CRITICAL_BLOCKS:
                            final_text = (
                                f"(Loop terminated: {critical_blocks} critical blocks hit. "
                                "The model was stuck repeating the same tool calls.)"
                            )
                            exit_reason = "critical_loop_break"
                            _debug_logger.step_error(step,
                                f"Force-exit: {critical_blocks} critical blocks reached")
                            break
                    else:
                        warning_text = ""
                        if detection.stuck and detection.level == "warning":
                            if loop_detector.should_emit_warning(detection.detector, detection.count):
                                warning_text = detection.message + "\n\n"
                                loop_hint = f"WARN:{detection.detector}"

                        exec_args = fn_args
                        if hook_runner:
                            modified_args = hook_runner.run("before_tool_call", fn_name, fn_args)
                            if modified_args is not None and isinstance(modified_args, dict):
                                exec_args = modified_args

                        envelope = tool_intent_security.create_envelope(
                            tool_name=fn_name,
                            args=exec_args,
                            session_id=getattr(_debug_logger, "_session_id", ""),
                            policy_level="standard",
                        )
                        ok_intent, reason_intent = tool_intent_security.verify_envelope(
                            envelope=envelope,
                            tool_name=fn_name,
                            args=exec_args,
                            session_id=getattr(_debug_logger, "_session_id", ""),
                        )

                        t0 = time.time()
                        try:
                            if not ok_intent:
                                tool_result = f"BLOCKED by tool-intent security: {reason_intent}"
                            else:
                                tool_result = tool_registry.execute(fn_name, exec_args)
                        except Exception as e:
                            tool_result = f"Tool execution failed: {e}"

                        tool_duration_ms = (time.time() - t0) * 1000

                        if hook_runner:
                            modified_result = hook_runner.run(
                                "after_tool_call", fn_name, exec_args, tool_result
                            )
                            if modified_result is not None and isinstance(modified_result, str):
                                tool_result = modified_result

                        loop_detector.record_result(call_id, tool_result)

                        if warning_text:
                            tool_result = warning_text + tool_result

                    _debug_logger.step_tool_call(
                        step, fn_name, fn_args, tool_result,
                        duration_ms=tool_duration_ms,
                        loop_detection=loop_hint,
                    )

                    tool_calls_log.append({
                        "step": step,
                        "tool": fn_name,
                        "args": fn_args,
                        "result": tool_result[:3000],
                    })

                    if on_step:
                        try:
                            on_step(step, fn_name, tool_result)
                        except Exception:
                            pass

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": tool_result[:DEFAULT_TOOL_RESULT_LIMIT],
                    })

                if exit_reason in ("task_complete", "cancelled"):
                    break

                if cancel_check and cancel_check():
                    if not final_text:
                        final_text = "(Stopped by user)"
                    exit_reason = "cancelled"
                    break

                if len(messages) > 30:
                    system_msg = messages[0]
                    user_msg = messages[1]
                    keep = messages[2:-20]
                    for i, m in enumerate(keep):
                        if m.get("role") == "tool" and len(m.get("content", "")) > 500:
                            keep[i] = {**m, "content": m["content"][:300] + "\n...(trimmed)"}
                    recent = messages[-20:]
                    messages = [system_msg, user_msg] + keep + recent
            else:
                text_content = msg.get("content", "").strip()
                if not tool_calls_log:
                    if tools_schema and step == 0 and step < max_steps - 2:
                        pushback = (
                            "You answered with a plain text message instead of using your tools. "
                            "You MUST use tools to complete tasks — do NOT answer from memory or assumptions. "
                            "Use the available tools (file_read, shell_exec, web_fetch, etc.) to gather real information, "
                            "then call task_complete(summary='...') with your findings. "
                            "Do NOT respond with plain text again — call a tool NOW."
                        )
                        _debug_logger.step_text_response(step, text_content, "pushback_first_turn_no_tools")
                        messages.append({
                            "role": "user",
                            "content": pushback,
                        })
                        continue
                    final_text = text_content
                    exit_reason = "first_text_response"
                    _debug_logger.step_text_response(step, text_content, "accepted_first_turn")
                    break

                if tools_schema and step < max_steps - 2:
                    workflow_issue = _check_incomplete_workflows(tool_calls_log)
                    pushback = (
                        "You responded with a plain text message, but you should call "
                        "task_complete(summary='...') when done. A text response without "
                        "task_complete means you're still working. "
                        "If the task IS done, call task_complete now with your summary. "
                        "If the task is NOT done, call the next tool to make progress."
                    )
                    if workflow_issue:
                        pushback += f"\n\nBLOCKER: {workflow_issue}"
                    _debug_logger.step_text_response(step, text_content,
                        f"pushback_sent{'_with_blocker' if workflow_issue else ''}")
                    messages.append({
                        "role": "user",
                        "content": pushback,
                    })
                    continue
                final_text = text_content
                exit_reason = "text_at_end"
                _debug_logger.step_text_response(step, text_content, "accepted_at_end")
                break

        if not final_text and messages:
            last = messages[-1]
            if isinstance(last, dict) and last.get("role") == "assistant":
                content = last.get("content", "")
                if isinstance(content, str):
                    final_text = content.strip()

            if not final_text and tool_calls_log:
                final_text = self._request_summary(messages, temperature, max_tokens)

        used_evolve = any(
            tc["tool"].startswith("evolve_") for tc in tool_calls_log
        )
        if used_evolve:
            try:
                from ghost_evolve import get_engine
                run_evo_ids = set()
                for tc in tool_calls_log:
                    if tc["tool"] == "evolve_plan":
                        result = tc.get("result", "")
                        if "Evolution planned:" in result:
                            evo_id = result.split("Evolution planned:")[1].strip().split()[0]
                            run_evo_ids.add(evo_id)
                cleanup_results = get_engine().cleanup_incomplete(
                    only_ids=run_evo_ids if run_evo_ids else None
                )
                if cleanup_results:
                    rollback_msgs = []
                    for evo_id, ok, msg in cleanup_results:
                        rollback_msgs.append(msg)
                    rollback_notice = "\n".join(rollback_msgs)
                    final_text = (
                        (final_text or "") +
                        f"\n\n⚠️ **Incomplete evolution rolled back**\n{rollback_notice}\n"
                        "Evolutions must complete the full cycle: "
                        "evolve_plan → evolve_apply → evolve_test → evolve_submit_pr."
                    )
            except Exception:
                pass

        unique_tools = list(set(tc["tool"] for tc in tool_calls_log)) if tool_calls_log else []
        _debug_logger.session_end(
            steps_used=len(set(tc["step"] for tc in tool_calls_log)) if tool_calls_log else 0,
            tools_used=unique_tools,
            total_tokens=total_tokens,
            exit_reason=exit_reason,
            final_text=final_text,
        )

        return ToolLoopResult(
            text=final_text,
            tool_calls=tool_calls_log,
            total_tokens=total_tokens,
            steps=len(set(tc["step"] for tc in tool_calls_log)) if tool_calls_log else 0,
        )

    def single_shot(self, system_prompt, user_message, temperature=0.2,
                    max_tokens=1024, image_b64=None, images=None):
        """Backwards-compatible single-shot call with no tools."""
        result = self.run(
            system_prompt=system_prompt,
            user_message=user_message,
            tool_registry=None,
            max_steps=1,
            temperature=temperature,
            max_tokens=max_tokens,
            image_b64=image_b64,
            images=images,
        )
        return result.text


class ToolLoopResult:
    """Result from a tool loop run."""
    __slots__ = ("text", "tool_calls", "total_tokens", "steps")

    def __init__(self, text, tool_calls, total_tokens, steps):
        self.text = text
        self.tool_calls = tool_calls
        self.total_tokens = total_tokens
        self.steps = steps

    def summary(self):
        if not self.tool_calls:
            return self.text
        tools_used = ", ".join(set(tc["tool"] for tc in self.tool_calls))
        return f"[Used: {tools_used}]\n{self.text}"


class ToolRegistry:
    """Registry of callable tools with OpenAI function-calling schema.
    
    Security: Prevents tool shadowing attacks (CVE-2025-59536/21852 mitigation).
    Malicious tools cannot override system tools or silently replace legitimate ones.
    """

    # System tools that cannot be shadowed/overwritten
    RESERVED_TOOL_NAMES = {"evolve_plan", "evolve_apply", "evolve_test", 
                           "evolve_deploy", "evolve_rollback", "evolve_delete",
                           "evolve_submit_pr",
                           "shell_exec", "file_read", "file_write", "credential_get",
                           "credential_save", "cron_add", "cron_remove"}

    def __init__(self, strict_mode=False):
        self._tools = {}
        self._strict_mode = strict_mode  # If True, reject overwrites instead of warning
        self._register_log = []  # Audit trail of registration attempts

    def register(self, tool_def):
        """Register a tool. Warns on overwrite, rejects if strict_mode and reserved."""
        name = tool_def.get("name")
        if not name:
            raise ValueError("Tool definition missing 'name' field")
        
        # Security: Check for reserved tool names
        if name in self.RESERVED_TOOL_NAMES and name in self._tools:
            msg = f"SECURITY: Attempt to overwrite reserved tool '{name}' blocked"
            self._register_log.append({"action": "blocked", "tool": name, "reason": "reserved"})
            if self._strict_mode:
                raise PermissionError(msg)
            print(f"[ToolRegistry] {msg}")
            return  # Silently ignore in non-strict mode to prevent shadowing
        
        # Security: Warn on any overwrite (tool shadowing detection)
        if name in self._tools:
            old_desc = self._tools[name].get("description", "")[:50]
            new_desc = tool_def.get("description", "")[:50]
            self._register_log.append({
                "action": "overwrite", 
                "tool": name, 
                "old_desc": old_desc,
                "new_desc": new_desc
            })
            print(f"[ToolRegistry] WARNING: Tool '{name}' is being overwritten!")
            print(f"  Old: {old_desc}... -> New: {new_desc}...")
        else:
            self._register_log.append({"action": "register", "tool": name})
        
        self._tools[name] = tool_def

    def unregister(self, name):
        self._tools.pop(name, None)

    def get(self, name):
        return self._tools.get(name)

    def get_all(self):
        return dict(self._tools)

    def names(self):
        return list(self._tools.keys())

    def execute(self, name, args):
        """Execute a tool by name with given args. Returns result string."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"
        try:
            if "__parse_error" in args:
                raw_len = args.get("__raw_len", 0)
                return (
                    f"Tool error ({name}): Your tool call arguments were malformed JSON "
                    f"(parse error: {args['__parse_error']}, raw length: {raw_len} chars). "
                    f"This usually happens when the content is too large for a single tool call. "
                    f"SOLUTION: For large files, use shell_exec with a heredoc or echo command instead. "
                    f"Example: shell_exec(command=\"mkdir -p ~/Desktop/project && cat > ~/Desktop/project/index.html << 'HTMLEOF'\\n<html>...</html>\\nHTMLEOF\")"
                )

            params = tool.get("parameters", {})
            required = params.get("required", [])
            missing = [r for r in required if r not in args]
            if missing:
                return (
                    f"Tool error ({name}): Missing required argument(s): {', '.join(missing)}. "
                    f"Required params: {required}. Provided: {list(args.keys())}. "
                    f"Please call {name} again with all required arguments."
                )
            
            result = tool["execute"](**args)
            if not isinstance(result, str):
                result = json.dumps(result, indent=2, default=str)
            return result
        except Exception as e:
            return f"Tool error ({name}): {e}\n{traceback.format_exc()[-500:]}"

    def to_openai_schema(self):
        """Convert all tools to OpenAI function-calling format."""
        schema = []
        for name, tool in self._tools.items():
            schema.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return schema

    def subset(self, names):
        """Return a new registry with only the named tools."""
        reg = ToolRegistry(strict_mode=self._strict_mode)
        for n in names:
            if n in self._tools:
                reg.register(self._tools[n])
        return reg
    
    def get_audit_log(self):
        """Return the registration audit log for security review."""
        return list(self._register_log)
    
    def is_reserved(self, name):
        """Check if a tool name is reserved."""
        return name in self.RESERVED_TOOL_NAMES
