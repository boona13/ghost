"""
Ghost Goal Executor Engine — Deterministic step-by-step goal execution.

Replaces the LLM-prompt-only approach with a Python-controlled execution loop:
  1. For each actionable goal, Python decides which step to run next
  2. A focused single-step LLM session executes ONLY that step
  3. Python verifies the step was actually marked done (reads GoalStore)
  4. If verification fails, retries once with a stricter prompt
  5. After all steps done, a quality-check session validates the output
  6. Only then is goal_complete() called

This eliminates narration, skipping, and the "one step per 30 min" bottleneck.
All steps of a goal run back-to-back in one cron fire.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from ghost_goals import GoalStore, STEP_PENDING, STEP_COMPLETED, STEP_FAILED

log = logging.getLogger("ghost.goal_executor")

MAX_STEP_TOOL_STEPS = 30   # tool-loop steps per individual step session
MAX_QA_TOOL_STEPS   = 15   # tool-loop steps for the quality-check session
MAX_RETRIES         = 2    # retries if a step isn't marked done after execution
MAX_GOALS_PER_RUN   = 5    # max goals to process in one cron fire
MAX_STEPS_PER_GOAL  = 20   # hard cap on steps per goal to prevent infinite loops


# ═══════════════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════════════

_STEP_SYSTEM = """You are Ghost executing ONE specific step of a user goal.
You have a single job: execute the step described below using the available tools,
then call goal_step_done() to record the result.

RULES (non-negotiable):
1. Execute the step using real tools — web_search, web_fetch, memory_save, shell_exec, etc.
2. After the step is done, call goal_step_done(goal_id=..., step_id=..., result=<one-line summary>).
3. If the step is to save or compile output, call goal_set_output(goal_id=..., output=<full content>)
   BEFORE calling goal_step_done.
4. Do NOT attempt other steps. Do NOT call goal_complete. Do exactly one step.
5. NEVER narrate. If you would say "I searched..." without having called web_search, go back and call it.
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
If NO: identify the single most important missing piece, add an observation explaining it,
       then call goal_complete anyway (the next cycle will do better).

Do NOT re-execute any steps. Do NOT call goal_set_output again. Just evaluate and complete.
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
        """Process all actionable goals. Called by the cron job."""
        goals = self.store.list_actionable()
        if not goals:
            return {"message": "No actionable goals.", "processed": 0}

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
                results.append({"goal_id": goal["id"], "error": str(exc)})

        return {
            "processed": len(results),
            "results": results,
        }

    # ------------------------------------------------------------------
    # Goal lifecycle
    # ------------------------------------------------------------------

    def _process_goal(self, goal: Dict) -> Dict:
        goal_id = goal["id"]

        # Phase 1 — plan if needed
        if goal["status"] == "pending_plan":
            log.info("[goal_executor] Planning goal [%s]", goal_id)
            ok = self._plan_goal(goal)
            if not ok:
                return {"goal_id": goal_id, "phase": "plan", "ok": False}
            goal = self.store.get(goal_id)  # reload after plan

        if not goal or goal["status"] != "active":
            return {"goal_id": goal_id, "skipped": True, "status": goal.get("status")}

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
            goal = self.store.get(goal_id)  # reload after each step
            if not goal:
                break
        else:
            log.error("[goal_executor] Goal [%s] hit step limit (%d). Stopping.",
                      goal_id, MAX_STEPS_PER_GOAL)

        # Phase 3 — quality check + complete
        if goal and self.store.all_steps_done(goal) and goal.get("last_output"):
            log.info("[goal_executor] Quality check for goal [%s]", goal_id)
            self._quality_check(goal)

        return {"goal_id": goal_id, "steps_run": steps_run}

    # ------------------------------------------------------------------
    # Phase 1 — Planning
    # ------------------------------------------------------------------

    def _plan_goal(self, goal: Dict) -> bool:
        """Run a focused LLM session to create the plan."""
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

        # Verify plan was set
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
        """Run a focused LLM session for exactly one step, with retry on failure."""
        goal_id = goal["id"]
        step_id = step["id"]

        observations = goal.get("observations", [])
        obs_text = "\n".join(
            f"  - {o['text']}" for o in observations[-8:]
            if isinstance(o, dict)
        ) or "  (none yet)"

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
            f"Prior observations (working memory from previous steps/runs):\n{obs_text}\n\n"
            f"Instructions:\n"
            f"1. Execute this step using the appropriate tools.\n"
            f"2. If this step involves compiling or delivering the final output, "
            f"   call goal_set_output(goal_id='{goal_id}', output=<full markdown content>).\n"
            f"3. Then call goal_step_done(goal_id='{goal_id}', step_id='{step_id}', "
            f"   result=<one-line summary of what you did>).\n"
            f"4. Do NOT execute other steps. Stop after this one."
        )

        # Tools available for step execution
        step_tools = [
            "goal_step_done", "goal_step_fail", "goal_add_observation",
            "goal_set_output",
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

            # Verify step was actually marked done
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

        # After all retries, force-fail the step so we don't loop forever
        log.error("[goal_executor] Step [%s/%s] failed after %d attempts. Force-failing.",
                  goal_id, step_id, MAX_RETRIES)
        self.store.mark_step_failed(goal_id, step_id,
                                    error=f"Executor: step not completed after {MAX_RETRIES} attempts")
        return False

    # ------------------------------------------------------------------
    # Phase 3 — Quality check
    # ------------------------------------------------------------------

    def _quality_check(self, goal: Dict) -> None:
        """Validate output against goal, then call goal_complete."""
        goal_id = goal["id"]
        output = goal.get("last_output", "")

        prompt = (
            f"Quality check for goal {goal_id}.\n\n"
            f"Original goal: {goal['goal_text']}\n\n"
            f"Output produced:\n{output[:3000]}\n"
            + ("...[truncated]" if len(output) > 3000 else "") +
            f"\n\nDoes this output satisfy the goal? "
            f"Call goal_complete(goal_id='{goal_id}', summary=...) to finish."
        )

        qa_tools = [
            "goal_complete", "goal_add_observation", "goal_step_fail",
        ]

        self._run_session(
            system=_QA_SYSTEM,
            message=prompt,
            tools=qa_tools,
            max_steps=MAX_QA_TOOL_STEPS,
            label=f"qa:{goal_id}",
        )

        # If QA session didn't call goal_complete, force it
        refreshed = self.store.get(goal_id)
        if refreshed and self.store.all_steps_done(refreshed):
            if refreshed["status"] == "active" and refreshed.get("completion_count", 0) == goal.get("completion_count", 0):
                log.warning("[goal_executor] QA didn't call goal_complete for [%s]. Forcing.", goal_id)
                self.store.complete_goal(goal_id, summary="Auto-completed by executor after quality check.")

    # ------------------------------------------------------------------
    # LLM session runner
    # ------------------------------------------------------------------

    def _run_session(self, system: str, message: str, tools: List[str],
                     max_steps: int, label: str) -> Optional[str]:
        """Spin up a fresh ToolLoopEngine and run a focused session."""
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

        # Build a focused registry containing only the tools this session needs
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
#  LLM-CALLABLE TOOL
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
                "steps of all active goals in one shot. Verifies each step was "
                "actually completed. Runs a quality check on the output. "
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
