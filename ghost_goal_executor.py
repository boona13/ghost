"""
Ghost Goal Executor Engine — Deterministic step-by-step goal execution
with delivery, feed integration, and failed-step recovery.

Execution flow per goal:
  1. Recover any failed steps that are under the retry cap
  2. Plan the goal if it has no plan yet (focused LLM session)
  3. Execute ALL pending steps back-to-back (each in its own LLM session)
  4. Verify each step was actually marked done; retry if not
  5. Quality-check the output — reject once if insufficient, then accept
  6. Call goal_complete and return completion info for delivery

The caller (daemon cron handler) is responsible for delivery dispatch,
feed posting, and console output — the engine returns structured results.
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ghost_goals import GoalStore, STEP_PENDING, STEP_COMPLETED, STEP_FAILED

log = logging.getLogger("ghost.goal_executor")

MAX_STEP_TOOL_STEPS = 30
MAX_QA_TOOL_STEPS   = 15
MAX_RETRIES         = 2
MAX_GOALS_PER_RUN   = 5
MAX_STEPS_PER_GOAL  = 20
MAX_STEP_RETRIES    = 3   # max times a failed step can be retried across cycles


# ═══════════════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════

_STEP_SYSTEM = """You are Ghost executing ONE specific step of a user goal.
You have a single job: execute the step described below using the available tools,
then call goal_step_done() to record the result.

RULES (non-negotiable):
1. Execute the step using real tools — web_search, web_fetch, memory_save, shell_exec, etc.
2. After the step is done, call goal_step_done(goal_id=..., step_id=..., result=<one-line summary>).
3. If the step produces data that later steps need (URLs, findings, lists, etc.),
   call goal_set_scratch(goal_id=..., key=<descriptive_key>, value=<data>) BEFORE goal_step_done.
4. If the step is to save or compile output, call goal_set_output(goal_id=..., output=<full content>)
   BEFORE calling goal_step_done.
5. Do NOT attempt other steps. Do NOT call goal_complete. Do exactly one step.
6. NEVER narrate. If you would say "I searched..." without having called web_search, go back and call it.
"""

_PLAN_SYSTEM = """You are Ghost creating an execution plan for a user goal.
Your ONLY job: call goal_plan(goal_id=..., steps=[...]) with 3-6 concrete steps.
Each step must be completable by Ghost with 1-2 tool calls (web_search, web_fetch,
memory_save, file_write, notify, etc.).
The FINAL step must always be: "Compile full output and call goal_set_output, then mark cycle complete."
Do not do any research now. Just create the plan.
"""

_QA_SYSTEM = """You are Ghost doing a quality check on a completed goal execution.
Read the goal description and the output that was produced.
Decide: does the output fully satisfy what the user asked for?

If YES: call goal_complete(goal_id=..., summary=<one sentence>) to close the cycle.
If NO: call goal_add_observation with a specific note about what's missing.
       Do NOT call goal_complete — the executor will handle retries.

Do NOT re-execute any steps. Do NOT call goal_set_output again. Just evaluate.
"""


# ═══════════════════════════════════════════════════════════════════
#  ENGINE
# ═══════════════════════════════════════════════════════════════════

class GoalExecutorEngine:
    """Deterministic Python-controlled goal executor."""

    def __init__(self, cfg: Dict[str, Any], tool_registry, auth_store=None,
                 provider_chain=None):
        self.cfg = cfg
        self.tool_registry = tool_registry
        self.auth_store = auth_store
        self.provider_chain = provider_chain
        self.store = GoalStore()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_all(self) -> Dict:
        """Process all actionable goals. Returns structured results for delivery."""
        goals = self.store.list_actionable()
        if not goals:
            return {"message": "No actionable goals.", "processed": 0, "results": []}

        goals = goals[:MAX_GOALS_PER_RUN]
        results = []

        for goal in goals:
            log.info("[goal_executor] Processing goal [%s] %s (status=%s)",
                     goal["id"], goal["title"], goal["status"])
            try:
                result = self._process_goal(goal)
                results.append(result)
            except Exception as exc:
                log.error("[goal_executor] Goal [%s] failed with exception: %s",
                          goal["id"], exc, exc_info=True)
                results.append({"goal_id": goal["id"], "title": goal.get("title", ""),
                                "error": str(exc), "completed": False})

        return {
            "processed": len(results),
            "results": results,
        }

    # ------------------------------------------------------------------
    # Goal lifecycle
    # ------------------------------------------------------------------

    def _process_goal(self, goal: Dict) -> Dict:
        goal_id = goal["id"]
        result_info = {
            "goal_id": goal_id,
            "title": goal.get("title", ""),
            "completed": False,
            "output": None,
            "summary": None,
            "delivery": goal.get("delivery", ""),
            "recurrence": goal.get("recurrence"),
        }

        # Phase 0 — Recover failed steps that are under the retry cap
        recovered = self.store.retry_failed_steps(goal_id, max_retries=MAX_STEP_RETRIES)
        if recovered > 0:
            log.info("[goal_executor] Recovered %d failed step(s) for [%s]", recovered, goal_id)
            goal = self.store.get(goal_id)

        # Phase 1 — plan if needed
        if goal["status"] == "pending_plan":
            log.info("[goal_executor] Planning goal [%s]", goal_id)
            ok = self._plan_goal(goal)
            if not ok:
                return {**result_info, "phase": "plan", "ok": False}
            goal = self.store.get(goal_id)

        if not goal or goal["status"] != "active":
            return {**result_info, "skipped": True, "status": goal.get("status") if goal else "deleted"}

        # Phase 2 — execute ALL pending steps back-to-back
        steps_run = []
        for _ in range(MAX_STEPS_PER_GOAL):
            step = self.store.next_pending_step(goal)
            if not step:
                break
            log.info("[goal_executor] Executing step [%s/%s] %s",
                     goal_id, step["id"], step["description"][:60])
            ok = self._execute_step(goal, step)
            steps_run.append({"step_id": step["id"], "ok": ok})
            goal = self.store.get(goal_id)
            if not goal:
                break
        else:
            log.error("[goal_executor] Goal [%s] hit step limit (%d). Stopping.",
                      goal_id, MAX_STEPS_PER_GOAL)

        result_info["steps_run"] = steps_run

        if not goal:
            return result_info

        # Reload goal to pick up any changes from step execution
        goal = self.store.get(goal_id)
        if not goal:
            return result_info

        all_done = self.store.all_steps_done(goal)
        has_pending = self.store.next_pending_step(goal) is not None
        has_failed = any(s["status"] == STEP_FAILED for s in goal.get("plan", []))

        # Phase 3 — quality check + complete
        if all_done:
            output = goal.get("last_output", "")
            if output:
                log.info("[goal_executor] Quality check for goal [%s]", goal_id)
                qa_passed = self._quality_check(goal)

                refreshed = self.store.get(goal_id)
                if refreshed:
                    cc_before = goal.get("completion_count", 0)
                    cc_after = refreshed.get("completion_count", 0)

                    if cc_after > cc_before:
                        result_info["completed"] = True
                        result_info["output"] = refreshed.get("last_output", "")
                        result_info["summary"] = refreshed.get("last_summary", "")
                    elif not qa_passed:
                        log.warning("[goal_executor] QA rejected [%s] — force-completing.", goal_id)
                        self.store.complete_goal(goal_id, summary="Completed (QA flagged possible gaps — see observations)")
                        refreshed = self.store.get(goal_id)
                        if refreshed:
                            result_info["completed"] = True
                            result_info["output"] = refreshed.get("last_output", "")
                            result_info["summary"] = refreshed.get("last_summary", "")
            else:
                log.warning("[goal_executor] Goal [%s] all steps done but no output. Completing.", goal_id)
                self.store.complete_goal(goal_id, summary="Completed — no output was produced by the steps.")
                result_info["completed"] = True

        elif not has_pending and has_failed:
            # All steps either completed or permanently failed (exceeded retry cap).
            # No pending steps remain — this goal is stuck. Complete it with a note
            # about which steps failed so it doesn't zombie forever.
            failed_ids = [s["id"] for s in goal.get("plan", []) if s["status"] == STEP_FAILED]
            log.warning("[goal_executor] Goal [%s] stuck: steps %s permanently failed. Force-completing.",
                        goal_id, failed_ids)
            summary = f"Completed with {len(failed_ids)} failed step(s): {', '.join(failed_ids)}"
            self.store.complete_goal(goal_id, summary=summary)
            refreshed = self.store.get(goal_id)
            if refreshed:
                result_info["completed"] = True
                result_info["output"] = refreshed.get("last_output", "")
                result_info["summary"] = summary

        return result_info

    # ------------------------------------------------------------------
    # Phase 1 — Planning
    # ------------------------------------------------------------------

    def _plan_goal(self, goal: Dict) -> bool:
        goal_id = goal["id"]
        prompt = (
            f"Create an execution plan for this goal.\n\n"
            f"Goal ID: {goal_id}\n"
            f"Title: {goal['title']}\n"
            f"Description: {goal['goal_text']}\n"
            f"Recurrence: {goal.get('recurrence') or 'one-shot'}\n\n"
            f"Call goal_plan(goal_id='{goal_id}', steps=[...]) now."
        )

        plan_tools = ["goal_plan", "goal_get"]
        result = self._run_session(
            system=_PLAN_SYSTEM,
            message=prompt,
            tools=plan_tools,
            max_steps=10,
            label=f"plan:{goal_id}",
        )

        updated = self.store.get(goal_id)
        if updated and updated.get("plan"):
            log.info("[goal_executor] Plan set for [%s]: %d steps",
                     goal_id, len(updated["plan"]))
            return True

        log.warning("[goal_executor] Plan not set for [%s]. Session text: %s",
                    goal_id, (result or "")[:200])
        return False

    # ------------------------------------------------------------------
    # Phase 2 — Step execution
    # ------------------------------------------------------------------

    def _execute_step(self, goal: Dict, step: Dict) -> bool:
        goal_id = goal["id"]
        step_id = step["id"]

        observations = goal.get("observations", [])
        obs_text = "\n".join(
            f"  - {o['text']}" for o in observations[-8:]
            if isinstance(o, dict)
        ) or "  (none yet)"

        # Include scratch data so the step has access to prior steps' structured output
        scratch = goal.get("scratch", {})
        scratch_text = ""
        if scratch:
            scratch_lines = []
            for k, v in scratch.items():
                val_preview = str(v)[:500]
                scratch_lines.append(f"  {k}: {val_preview}")
            scratch_text = (
                "\nScratch space (structured data from previous steps):\n"
                + "\n".join(scratch_lines) + "\n"
            )

        last_output_note = ""
        if goal.get("last_output"):
            last_output_note = (
                "\nNOTE: A previous cycle already produced output for this goal. "
                "This is a NEW cycle — produce FRESH content, do not reuse prior output."
            )

        prompt = (
            f"Execute step {step_id} of goal {goal_id}.{last_output_note}\n\n"
            f"Goal: {goal['title']}\n"
            f"Goal description: {goal['goal_text']}\n\n"
            f"Step to execute:\n"
            f"  ID: {step_id}\n"
            f"  Description: {step['description']}\n\n"
            f"Prior observations (working memory from previous steps/runs):\n{obs_text}\n"
            f"{scratch_text}\n"
            f"Instructions:\n"
            f"1. Execute this step using the appropriate tools.\n"
            f"2. If this step produces data that later steps need, call "
            f"   goal_set_scratch(goal_id='{goal_id}', key=<name>, value=<data>).\n"
            f"3. If this step involves compiling or delivering the final output, "
            f"   call goal_set_output(goal_id='{goal_id}', output=<full markdown content>).\n"
            f"4. Then call goal_step_done(goal_id='{goal_id}', step_id='{step_id}', "
            f"   result=<one-line summary of what you did>).\n"
            f"5. Do NOT execute other steps. Stop after this one."
        )

        step_tools = [
            "goal_step_done", "goal_step_fail", "goal_add_observation",
            "goal_set_output", "goal_set_scratch",
            "web_search", "web_fetch", "memory_save", "memory_search",
            "file_write", "file_read", "shell_exec",
            "notify", "channel_send",
        ]

        for attempt in range(MAX_RETRIES):
            retry_note = f"\n\nATTEMPT {attempt + 1}/{MAX_RETRIES}. You MUST call goal_step_done at the end." if attempt > 0 else ""
            self._run_session(
                system=_STEP_SYSTEM,
                message=prompt + retry_note,
                tools=step_tools,
                max_steps=MAX_STEP_TOOL_STEPS,
                label=f"step:{goal_id}/{step_id}",
            )

            refreshed = self.store.get(goal_id)
            if not refreshed:
                return False
            for s in refreshed.get("plan", []):
                if s["id"] == step_id and s["status"] in (STEP_COMPLETED, STEP_FAILED):
                    log.info("[goal_executor] Step [%s/%s] confirmed %s (attempt %d)",
                             goal_id, step_id, s["status"], attempt + 1)
                    return True

            log.warning("[goal_executor] Step [%s/%s] not marked done after attempt %d",
                        goal_id, step_id, attempt + 1)

        log.error("[goal_executor] Step [%s/%s] failed after %d attempts. Force-failing.",
                  goal_id, step_id, MAX_RETRIES)
        self.store.mark_step_failed(goal_id, step_id,
                                    error=f"Executor: step not completed after {MAX_RETRIES} attempts")
        return False

    # ------------------------------------------------------------------
    # Phase 3 — Quality check
    # ------------------------------------------------------------------

    def _quality_check(self, goal: Dict) -> bool:
        """Validate output against goal. Returns True if QA approved."""
        goal_id = goal["id"]
        output = goal.get("last_output", "")

        prompt = (
            f"Quality check for goal {goal_id}.\n\n"
            f"Original goal: {goal['goal_text']}\n\n"
            f"Output produced:\n{output[:3000]}\n"
            + ("...[truncated]" if len(output) > 3000 else "") +
            f"\n\nDoes this output satisfy the goal? "
            f"If YES: call goal_complete(goal_id='{goal_id}', summary=...) to finish.\n"
            f"If NO: call goal_add_observation with what's missing. Do NOT call goal_complete."
        )

        qa_tools = [
            "goal_complete", "goal_add_observation",
        ]

        self._run_session(
            system=_QA_SYSTEM,
            message=prompt,
            tools=qa_tools,
            max_steps=MAX_QA_TOOL_STEPS,
            label=f"qa:{goal_id}",
        )

        refreshed = self.store.get(goal_id)
        if not refreshed:
            return False

        cc_before = goal.get("completion_count", 0)
        cc_after = refreshed.get("completion_count", 0)
        return cc_after > cc_before

    # ------------------------------------------------------------------
    # LLM session runner
    # ------------------------------------------------------------------

    def _run_session(self, system: str, message: str, tools: List[str],
                     max_steps: int, label: str) -> Optional[str]:
        from ghost_loop import ToolLoopEngine

        api_key = None
        if self.auth_store:
            try:
                api_key = self.auth_store.get_api_key("openrouter")
            except Exception:
                pass
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            log.error("[goal_executor] No API key for session %s", label)
            return None

        available = set(self.tool_registry.names())
        valid_tools = [t for t in tools if t in available]
        if not valid_tools:
            log.error("[goal_executor] No valid tools for session %s", label)
            return None

        focused_registry = self.tool_registry.subset(valid_tools)
        model = self.cfg.get("model", "anthropic/claude-sonnet-4")

        engine = ToolLoopEngine(
            api_key=api_key,
            model=model,
            fallback_models=self.cfg.get("fallback_models", []),
            auth_store=self.auth_store,
            provider_chain=self.provider_chain,
        )

        start = time.time()
        try:
            result = engine.run(
                system_prompt=system,
                user_message=message,
                tool_registry=focused_registry,
                max_steps=max_steps,
                temperature=0.2,
                max_tokens=4096,
            )
            elapsed = int((time.time() - start) * 1000)
            log.info("[goal_executor] Session %s done in %dms (%d steps)",
                     label, elapsed, result.steps)
            return result.text or ""
        except Exception as exc:
            log.error("[goal_executor] Session %s failed: %s", label, exc, exc_info=True)
            return None


# ═══════════════════════════════════════════════════════════════════
#  DELIVERY DISPATCH — called by daemon after executor completes
# ═══════════════════════════════════════════════════════════════════

def deliver_goal_results(results: List[Dict], daemon) -> None:
    """Post-process executor results: deliver output, post to feed, emit events.

    Called by the daemon's cron handler after the goal executor runs.
    This is the "last mile" that closes the loop back to the user.
    """
    from ghost_console import console_bus

    for r in results:
        goal_id = r.get("goal_id", "?")
        title = r.get("title", "Untitled goal")

        if r.get("error"):
            console_bus.emit("error", "cron", "goal_executor",
                             f"Goal [{goal_id}] error: {r['error'][:200]}")
            continue

        if r.get("skipped"):
            continue

        steps = r.get("steps_run", [])
        done_count = sum(1 for s in steps if s.get("ok"))
        console_bus.emit("info", "cron", "goal_executor",
                         f"Goal [{goal_id}] {title}: {done_count}/{len(steps)} steps completed")

        if not r.get("completed"):
            continue

        # ── Goal completed — deliver output ──

        output = r.get("output", "")
        summary = r.get("summary", "Goal completed")
        delivery = r.get("delivery", "")
        recurrence = r.get("recurrence")

        recurrence_label = f" (recurring: {recurrence})" if recurrence else ""
        console_bus.emit("success", "cron", "goal_executor",
                         f"Goal completed: {title}{recurrence_label}")

        # 1. Post to activity feed
        try:
            from ghost import append_feed
            feed_entry = {
                "time": datetime.now().isoformat(),
                "type": "goal",
                "source": f"[Goal] {title}",
                "result": (summary or output[:300]) if output else summary,
                "goal_id": goal_id,
            }
            append_feed(feed_entry, daemon.cfg.get("max_feed_items", 50))
        except Exception as exc:
            log.warning("[goal_executor] Failed to post goal to feed: %s", exc)

        # 2. Dispatch delivery based on the delivery method
        if delivery:
            _dispatch_delivery(delivery, title, output, summary, goal_id, daemon)


def _dispatch_delivery(delivery: str, title: str, output: str,
                       summary: str, goal_id: str, daemon) -> None:
    """Route goal output to the configured delivery channel."""
    log.info("[goal_executor] Delivering goal [%s] via: %s", goal_id, delivery)

    try:
        if delivery == "notify":
            _deliver_notify(title, summary or output[:500], daemon)

        elif delivery == "chat":
            _deliver_chat_feed(title, output, summary, goal_id, daemon)

        elif delivery.startswith("file:"):
            _deliver_file(delivery[5:].strip(), title, output, goal_id)

        elif delivery in ("telegram", "discord", "slack", "whatsapp"):
            _deliver_channel(delivery, title, output, summary, daemon)

        elif delivery == "memory":
            _deliver_memory(title, output, summary, goal_id, daemon)

        else:
            log.warning("[goal_executor] Unknown delivery method '%s' for goal [%s]",
                        delivery, goal_id)

    except Exception as exc:
        log.error("[goal_executor] Delivery failed for goal [%s] via %s: %s",
                  goal_id, delivery, exc, exc_info=True)


def _deliver_notify(title: str, message: str, daemon) -> None:
    """Send via the notify tool (OS notification + configured channels)."""
    notify_tool = daemon.tool_registry.get("notify") if daemon.tool_registry else None
    if notify_tool and callable(notify_tool.get("execute")):
        notify_tool["execute"](
            title=f"Goal Complete: {title}",
            message=message[:1000],
            priority="normal",
        )
    else:
        import ghost_platform
        ghost_platform.send_notification(f"Goal: {title}", message[:500])


def _deliver_channel(channel: str, title: str, output: str,
                     summary: str, daemon) -> None:
    """Send output via a messaging channel (telegram, discord, etc.)."""
    if not getattr(daemon, "channel_router", None):
        log.warning("[goal_executor] No channel router — cannot deliver via %s", channel)
        return

    text = f"**Goal Complete: {title}**\n\n"
    if summary:
        text += f"*{summary}*\n\n"
    text += output[:3000]
    if len(output) > 3000:
        text += "\n\n...[truncated — full output in Goals dashboard]"

    daemon.channel_router.send(text, channel=channel, priority="normal",
                               title=f"Goal: {title}")


def _deliver_chat_feed(title: str, output: str, summary: str,
                       goal_id: str, daemon) -> None:
    """Post the full output as a chat feed entry."""
    try:
        from ghost import append_feed
        entry = {
            "time": datetime.now().isoformat(),
            "type": "goal_delivery",
            "source": f"[Goal Delivery] {title}",
            "result": output[:5000] if output else summary,
            "goal_id": goal_id,
        }
        append_feed(entry, daemon.cfg.get("max_feed_items", 50))
    except Exception as exc:
        log.warning("[goal_executor] Chat feed delivery failed: %s", exc)


def _deliver_file(path_str: str, title: str, output: str, goal_id: str) -> None:
    """Write the output to a file."""
    path = Path(path_str).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {title}\n"
        f"<!-- Goal: {goal_id} | Generated: {datetime.now().isoformat()} -->\n\n"
        f"{output}",
        encoding="utf-8",
    )
    log.info("[goal_executor] Output written to %s", path)


def _deliver_memory(title: str, output: str, summary: str,
                    goal_id: str, daemon) -> None:
    """Save the output to Ghost's searchable memory."""
    mem_tool = daemon.tool_registry.get("memory_save") if daemon.tool_registry else None
    if mem_tool and callable(mem_tool.get("execute")):
        mem_tool["execute"](
            content=f"Goal output: {title}\n\n{output[:2000]}",
            tags=f"goal,{goal_id}",
        )


# ═══════════════════════════════════════════════════════════════════
#  LLM-CALLABLE TOOL (for manual / chat invocation)
# ═══════════════════════════════════════════════════════════════════

def build_goal_executor_tool(cfg: Dict, tool_registry, auth_store=None,
                              provider_chain=None) -> List[Dict]:
    """Build the run_goal_engine tool for cron/chat invocation."""

    executor = GoalExecutorEngine(
        cfg=cfg,
        tool_registry=tool_registry,
        auth_store=auth_store,
        provider_chain=provider_chain,
    )

    def run_goal_engine(goal_id: str = "", **kwargs):
        """
        Run the deterministic Goal Executor Engine.

        Processes all actionable goals (or a specific goal if goal_id is given):
          - Recovers failed steps that are under the retry cap
          - Plans goals that have no plan yet
          - Executes ALL pending steps back-to-back in one session
          - Verifies each step was actually marked done (retries if not)
          - Runs a quality check on the output before completing

        Use this instead of manually managing goal steps. It finishes the entire
        goal in one invocation rather than one step per cron fire.

        Args:
            goal_id: Optional — run only this goal. Leave empty to run all.
        """
        if goal_id:
            goal = executor.store.get(goal_id)
            if not goal:
                return {"error": f"Goal not found: {goal_id}"}
            result = executor._process_goal(goal)
            return result
        return executor.run_all()

    return [
        {
            "name": "run_goal_engine",
            "description": (
                "Run the deterministic Goal Executor — plans and executes ALL pending "
                "steps of all active goals in one shot. Recovers failed steps, verifies "
                "each step was completed, runs a quality check on output. "
                "Use this to trigger goal execution immediately without waiting for the cron."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {
                        "type": "string",
                        "description": "Run only this specific goal (leave empty for all goals).",
                    },
                },
            },
            "execute": run_goal_engine,
        }
    ]
