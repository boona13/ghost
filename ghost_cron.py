"""
GHOST Cron Service

Persistent cron job scheduler with three schedule types:
  - "at":    one-shot at a specific datetime
  - "every": repeating interval (e.g. every 5 minutes)
  - "cron":  standard cron expression (requires croniter)

Inspired by OpenClaw's cron service.
Jobs stored in ~/.ghost/cron/jobs.json with atomic writes.
"""

import json
import time
import uuid
import hashlib
import threading
from copy import deepcopy
from pathlib import Path
from datetime import datetime

GHOST_HOME = Path.home() / ".ghost"
CRON_DIR = GHOST_HOME / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"

MAX_TIMER_DELAY_S = 60
MAX_CONCURRENT_RUNS = 3
STUCK_THRESHOLD_S = 7200        # 2 hours
MIN_REFIRE_GAP_S = 2
MAX_SCHEDULE_ERRORS = 3

BACKOFF_DELAYS_S = [30, 60, 300, 900, 3600]

RST = "\033[0m"
DIM = "\033[2m"
YEL = "\033[33m"
GRN = "\033[32m"
RED = "\033[31m"
CYN = "\033[36m"

try:
    from croniter import croniter
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


def _now_ms():
    return int(time.time() * 1000)


def _generate_id():
    return uuid.uuid4().hex[:12]


def _format_duration(ms):
    if ms < 1000:
        return f"{ms}ms"
    s = ms / 1000
    if s < 60:
        return f"{s:.1f}s"
    m = s / 60
    if m < 60:
        return f"{m:.1f}m"
    h = m / 60
    return f"{h:.1f}h"


def _format_interval(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


# ═════════════════════════════════════════════════════════════════════
#  SCHEDULE COMPUTATION
# ═════════════════════════════════════════════════════════════════════

def compute_next_run(schedule, job_id=None, created_at_ms=None, after_ms=None):
    """Compute the next run time in ms for a given schedule.

    Returns int (epoch ms) or None if the schedule has no future runs.
    """
    now_ms = after_ms or _now_ms()
    kind = schedule.get("kind")

    if kind == "at":
        at_val = schedule.get("at")
        if isinstance(at_val, (int, float)):
            target_ms = int(at_val)
        else:
            try:
                dt = datetime.fromisoformat(str(at_val))
                target_ms = int(dt.timestamp() * 1000)
            except Exception:
                return None
        return target_ms if target_ms > now_ms else None

    elif kind == "every":
        every_ms = schedule.get("everyMs", 60000)
        anchor_ms = schedule.get("anchorMs") or created_at_ms or now_ms
        if every_ms <= 0:
            return None
        elapsed = now_ms - anchor_ms
        if elapsed < 0:
            return anchor_ms
        steps = (elapsed // every_ms) + 1
        next_ms = anchor_ms + steps * every_ms
        while next_ms <= now_ms:
            next_ms += every_ms
        return next_ms

    elif kind == "cron":
        if not HAS_CRONITER:
            return None
        expr = schedule.get("expr", "")
        try:
            base_dt = datetime.fromtimestamp(now_ms / 1000)
            cron = croniter(expr, base_dt)
            next_dt = cron.get_next(datetime)
            next_ms = int(next_dt.timestamp() * 1000)
            stagger_ms = schedule.get("staggerMs", 0)
            if stagger_ms and job_id:
                offset = int(hashlib.sha256(job_id.encode()).hexdigest()[:8], 16) % stagger_ms
                next_ms += offset
            return next_ms
        except Exception:
            return None

    return None


def describe_schedule(schedule):
    """Human-readable description of a schedule."""
    kind = schedule.get("kind")
    if kind == "at":
        at_val = schedule.get("at")
        if isinstance(at_val, (int, float)):
            return f"once at {datetime.fromtimestamp(at_val / 1000).strftime('%Y-%m-%d %H:%M')}"
        return f"once at {at_val}"
    elif kind == "every":
        every_ms = schedule.get("everyMs", 60000)
        return f"every {_format_interval(every_ms // 1000)}"
    elif kind == "cron":
        expr = schedule.get("expr", "?")
        tz = schedule.get("tz")
        desc = f"cron: {expr}"
        if tz:
            desc += f" ({tz})"
        return desc
    elif kind == "manual":
        return "event-driven (manual trigger only)"
    return "unknown"


# ═════════════════════════════════════════════════════════════════════
#  JOB MODEL
# ═════════════════════════════════════════════════════════════════════

def make_job(name, schedule, payload, description="", enabled=True,
             delete_after_run=False):
    """Create a new cron job dict."""
    now = _now_ms()
    job_id = _generate_id()
    job = {
        "id": job_id,
        "name": name,
        "description": description,
        "enabled": enabled,
        "deleteAfterRun": delete_after_run,
        "createdAtMs": now,
        "updatedAtMs": now,
        "schedule": schedule,
        "payload": payload,
        "state": {},
    }
    job["state"]["nextRunAtMs"] = compute_next_run(
        schedule, job_id=job_id, created_at_ms=now
    )
    return job


# ═════════════════════════════════════════════════════════════════════
#  PERSISTENCE (atomic JSON file store)
# ═════════════════════════════════════════════════════════════════════

class CronStore:
    """JSON file-based persistence for cron jobs with atomic writes."""

    def __init__(self, path=None):
        self._path = Path(path) if path else JOBS_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._mtime = 0
        self._jobs = []
        self._load()

    def _load(self):
        if not self._path.exists():
            self._jobs = []
            self._mtime = 0
            return
        try:
            mtime = self._path.stat().st_mtime
            if mtime == self._mtime:
                return
            data = json.loads(self._path.read_text())
            self._jobs = data.get("jobs", [])
            self._mtime = mtime
        except Exception:
            self._jobs = []

    def _save(self):
        try:
            tmp = self._path.with_suffix(".tmp")
            data = {"version": 1, "jobs": self._jobs}
            tmp.write_text(json.dumps(data, indent=2, default=str))
            tmp.rename(self._path)
            self._mtime = self._path.stat().st_mtime
        except Exception as e:
            print(f"  {RED}[cron] Save error: {e}{RST}")

    def reload(self):
        with self._lock:
            self._mtime = 0
            self._load()

    def get_all(self):
        with self._lock:
            self._load()
            return deepcopy(self._jobs)

    def get(self, job_id):
        with self._lock:
            self._load()
            for j in self._jobs:
                if j["id"] == job_id:
                    return deepcopy(j)
            return None

    def add(self, job):
        with self._lock:
            self._load()
            self._jobs.append(job)
            self._save()

    def update(self, job_id, updates):
        with self._lock:
            self._load()
            for i, j in enumerate(self._jobs):
                if j["id"] == job_id:
                    self._jobs[i].update(updates)
                    self._jobs[i]["updatedAtMs"] = _now_ms()
                    self._save()
                    return True
            return False

    def update_state(self, job_id, state_updates):
        with self._lock:
            self._load()
            for j in self._jobs:
                if j["id"] == job_id:
                    j.setdefault("state", {}).update(state_updates)
                    self._save()
                    return True
            return False

    def remove(self, job_id):
        with self._lock:
            self._load()
            before = len(self._jobs)
            self._jobs = [j for j in self._jobs if j["id"] != job_id]
            if len(self._jobs) < before:
                self._save()
                return True
            return False

    def save_all(self, jobs):
        with self._lock:
            self._jobs = jobs
            self._save()


# ═════════════════════════════════════════════════════════════════════
#  CRON SERVICE (background scheduler)
# ═════════════════════════════════════════════════════════════════════

class CronService:
    """Background cron job scheduler.

    Runs a timer loop that checks for due jobs and executes them.
    When a job fires, the on_fire callback receives the full job dict.

    Payload types:
      - {"type": "task",   "prompt": "..."}  -> run through tool loop
      - {"type": "notify", "title": "...", "message": "..."}  -> system notification
      - {"type": "shell",  "command": "..."}  -> run shell command
    """

    def __init__(self, on_fire=None, store_path=None):
        self.store = CronStore(store_path)
        self._on_fire = on_fire
        self._running = False
        self._timer = None
        self._timer_lock = threading.Lock()
        self._exec_lock = threading.Lock()
        self._executing = set()

    def start(self):
        if self._running:
            return
        self._running = True
        CRON_DIR.mkdir(parents=True, exist_ok=True)
        self._clear_stale_running()
        self._run_missed_jobs()
        self._recompute_all()
        self._arm_timer()
        jobs = self.store.get_all()
        enabled = sum(1 for j in jobs if j.get("enabled"))
        print(f"  {DIM}⏰ Cron started: {len(jobs)} jobs ({enabled} enabled){RST}")

    def stop(self):
        self._running = False
        with self._timer_lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    # ── Timer loop ────────────────────────────────────────────────

    def _arm_timer(self):
        if not self._running:
            return
        with self._timer_lock:
            if self._timer:
                self._timer.cancel()

            jobs = self.store.get_all()
            enabled = [j for j in jobs if j.get("enabled")]

            if not enabled:
                self._timer = threading.Timer(MAX_TIMER_DELAY_S, self._on_timer)
                self._timer.daemon = True
                self._timer.start()
                return

            now_ms = _now_ms()
            next_runs = [
                j["state"].get("nextRunAtMs")
                for j in enabled
                if j.get("state", {}).get("nextRunAtMs")
            ]

            if not next_runs:
                delay = MAX_TIMER_DELAY_S
            else:
                earliest = min(next_runs)
                delay_ms = max(0, earliest - now_ms)
                delay = min(delay_ms / 1000, MAX_TIMER_DELAY_S)
                delay = max(delay, 0.1)

            self._timer = threading.Timer(delay, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self):
        if not self._running:
            return
        try:
            self._tick()
        except Exception as e:
            print(f"  {RED}[cron] Timer error: {e}{RST}")
        finally:
            self._arm_timer()

    def _tick(self):
        now_ms = _now_ms()
        jobs = self.store.get_all()

        due = []
        for job in jobs:
            if not job.get("enabled"):
                continue
            if job["id"] in self._executing:
                continue
            next_run = job.get("state", {}).get("nextRunAtMs")
            if not next_run or next_run > now_ms:
                continue
            last_run = job.get("state", {}).get("lastRunAtMs")
            if last_run and (now_ms - last_run) < MIN_REFIRE_GAP_S * 1000:
                continue
            due.append(job)

        if not due:
            return

        with self._exec_lock:
            slots = MAX_CONCURRENT_RUNS - len(self._executing)
            due = [j for j in due if j["id"] not in self._executing][:max(0, slots)]
            for job in due:
                self._executing.add(job["id"])

        for job in due:
            self.store.update_state(job["id"], {"runningAtMs": now_ms})
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"  {DIM}{now_str}{RST}  {YEL}⏰ Cron firing:{RST} {GRN}{job['name']}{RST}")
            threading.Thread(
                target=self._execute_job,
                args=(job,),
                daemon=True,
            ).start()

    def _execute_job(self, job):
        job_id = job["id"]
        start_ms = _now_ms()
        status = "ok"
        error = None

        try:
            if self._on_fire:
                self._on_fire(job)
        except Exception as e:
            status = "error"
            error = str(e)
        finally:
            with self._exec_lock:
                self._executing.discard(job_id)

        duration_ms = _now_ms() - start_ms
        state_updates = {
            "runningAtMs": None,
            "lastRunAtMs": start_ms,
            "lastRunStatus": status,
            "lastDurationMs": duration_ms,
        }

        if status == "error":
            state_updates["lastError"] = error
            consec = (job.get("state", {}).get("consecutiveErrors") or 0) + 1
            state_updates["consecutiveErrors"] = consec
            backoff_idx = min(consec - 1, len(BACKOFF_DELAYS_S) - 1)
            backoff_ms = BACKOFF_DELAYS_S[backoff_idx] * 1000
            next_run = compute_next_run(
                job["schedule"], job_id=job_id,
                created_at_ms=job.get("createdAtMs"),
                after_ms=_now_ms(),
            )
            if next_run:
                next_run = max(next_run, _now_ms() + backoff_ms)
            state_updates["nextRunAtMs"] = next_run
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"  {DIM}{now_str}{RST}  {RED}⏰ Cron error:{RST} {job['name']}: {error}")
        else:
            state_updates["consecutiveErrors"] = 0
            state_updates["lastError"] = None

            if job["schedule"].get("kind") == "at":
                state_updates["nextRunAtMs"] = None
                if job.get("deleteAfterRun"):
                    self.store.remove(job_id)
                    return
                self.store.update(job_id, {"enabled": False})

            next_run = compute_next_run(
                job["schedule"], job_id=job_id,
                created_at_ms=job.get("createdAtMs"),
                after_ms=_now_ms(),
            )
            state_updates["nextRunAtMs"] = next_run
            now_str = datetime.now().strftime("%H:%M:%S")
            dur = _format_duration(duration_ms)
            print(f"  {DIM}{now_str}{RST}  {GRN}⏰ Cron done:{RST} {job['name']} ({dur})")

        self.store.update_state(job_id, state_updates)

    # ── On-demand trigger ──────────────────────────────────────────

    def fire_now(self, job_name):
        """Immediately fire a job by name (if not already running).

        Used by the serial evolution queue to trigger the Feature Implementer
        when a P0/P1 feature is added, instead of waiting for the next
        scheduled run (which could be hours away).
        Returns True if the job was fired, False otherwise.
        """
        jobs = self.store.get_all()
        target = None
        for job in jobs:
            if job.get("name") == job_name and job.get("enabled"):
                target = job
                break
        if not target:
            return False

        with self._exec_lock:
            if target["id"] in self._executing:
                return False
            slots = MAX_CONCURRENT_RUNS - len(self._executing)
            if slots <= 0:
                return False
            self._executing.add(target["id"])

        self.store.update_state(target["id"], {"runningAtMs": _now_ms()})
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"  {DIM}{now_str}{RST}  {YEL}⏰ Cron fire_now:{RST} {GRN}{target['name']}{RST}")
        threading.Thread(
            target=self._execute_job,
            args=(target,),
            daemon=True,
        ).start()
        return True

    def get_active_count(self):
        """Return the number of currently executing cron jobs."""
        return len(self._executing)

    def get_active_jobs(self):
        """Return the set of currently executing job IDs."""
        return set(self._executing)

    def is_job_running(self, job_name: str) -> bool:
        """Return True if the named job is currently executing."""
        for job in self.store.get_all():
            if job.get("name") == job_name:
                with self._exec_lock:
                    return job["id"] in self._executing
        return False

    # ── Startup maintenance ───────────────────────────────────────

    def _clear_stale_running(self):
        jobs = self.store.get_all()
        now_ms = _now_ms()
        for job in jobs:
            running_at = job.get("state", {}).get("runningAtMs")
            if running_at and (now_ms - running_at) > STUCK_THRESHOLD_S * 1000:
                self.store.update_state(job["id"], {"runningAtMs": None})

    def _run_missed_jobs(self):
        """Fire jobs that were due while Ghost was offline — once per job."""
        now_ms = _now_ms()
        jobs = self.store.get_all()
        missed = []
        for job in jobs:
            if not job.get("enabled"):
                continue
            next_run = job.get("state", {}).get("nextRunAtMs")
            if not next_run or next_run >= now_ms:
                continue
            missed.append(job)

        if missed:
            names = [j["name"] for j in missed]
            print(f"  {YEL}⏰ Catching up {len(missed)} missed job(s): {', '.join(names)}{RST}")

        with self._exec_lock:
            missed = [j for j in missed if j["id"] not in self._executing]
            for job in missed:
                self._executing.add(job["id"])
        for job in missed:
            threading.Thread(
                target=self._execute_job,
                args=(job,),
                daemon=True,
            ).start()

    def _recompute_all(self):
        jobs = self.store.get_all()
        changed = False
        for job in jobs:
            if not job.get("enabled"):
                continue
            if job.get("state", {}).get("runningAtMs"):
                continue
            next_run = compute_next_run(
                job["schedule"], job_id=job["id"],
                created_at_ms=job.get("createdAtMs"),
            )
            old_next = job.get("state", {}).get("nextRunAtMs")
            if next_run != old_next:
                job.setdefault("state", {})["nextRunAtMs"] = next_run
                changed = True
        if changed:
            self.store.save_all(jobs)

    # ── Public API ────────────────────────────────────────────────

    def list_jobs(self, enabled_only=False):
        jobs = self.store.get_all()
        if enabled_only:
            jobs = [j for j in jobs if j.get("enabled")]
        return jobs

    def add_job(self, name, schedule, payload, description="",
                enabled=True, delete_after_run=False):
        job = make_job(
            name=name, schedule=schedule, payload=payload,
            description=description, enabled=enabled,
            delete_after_run=delete_after_run,
        )
        self.store.add(job)
        self._arm_timer()
        return job

    def update_job(self, job_id, **updates):
        if "schedule" in updates:
            job = self.store.get(job_id)
            if job:
                next_run = compute_next_run(
                    updates["schedule"], job_id=job_id,
                    created_at_ms=job.get("createdAtMs"),
                )
                st = job.get("state", {})
                st["nextRunAtMs"] = next_run
                updates["state"] = st
        ok = self.store.update(job_id, updates)
        if ok:
            self._arm_timer()
        return ok

    def remove_job(self, job_id):
        ok = self.store.remove(job_id)
        if ok:
            self._arm_timer()
        return ok

    def run_now(self, job_id):
        job = self.store.get(job_id)
        if not job:
            return False, "Job not found"
        with self._exec_lock:
            if job["id"] in self._executing:
                return False, "Job already running"
            self._executing.add(job["id"])
        threading.Thread(
            target=self._execute_job, args=(job,), daemon=True,
        ).start()
        return True, "Job triggered"

    def enable_job(self, job_id, enabled=True):
        job = self.store.get(job_id)
        if not job:
            return False
        updates = {"enabled": enabled}
        if enabled:
            next_run = compute_next_run(
                job["schedule"], job_id=job_id,
                created_at_ms=job.get("createdAtMs"),
            )
            updates["state"] = job.get("state", {})
            updates["state"]["nextRunAtMs"] = next_run
        return self.store.update(job_id, updates)

    def status(self):
        jobs = self.store.get_all()
        enabled = [j for j in jobs if j.get("enabled")]
        now_ms = _now_ms()
        next_runs = [
            j["state"].get("nextRunAtMs")
            for j in enabled
            if j.get("state", {}).get("nextRunAtMs")
        ]
        next_wake = min(next_runs) if next_runs else None
        return {
            "running": self._running,
            "total_jobs": len(jobs),
            "enabled_jobs": len(enabled),
            "executing": len(self._executing),
            "next_wake_ms": next_wake,
            "next_wake": (
                datetime.fromtimestamp(next_wake / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if next_wake else None
            ),
        }


# ═════════════════════════════════════════════════════════════════════
#  CRON TOOLS (for LLM tool calling)
# ═════════════════════════════════════════════════════════════════════

def build_cron_tools(cron_service):
    """Build tool definitions that let the LLM manage cron jobs."""

    def cron_list_exec(enabled_only=False):
        jobs = cron_service.list_jobs(enabled_only=enabled_only)
        if not jobs:
            return "No cron jobs configured."
        lines = []
        for j in jobs:
            status_icon = "ON" if j.get("enabled") else "OFF"
            sched = describe_schedule(j.get("schedule", {}))
            state = j.get("state", {})
            next_run = state.get("nextRunAtMs")
            next_str = (
                datetime.fromtimestamp(next_run / 1000).strftime("%Y-%m-%d %H:%M:%S")
                if next_run else "none"
            )
            last_status = state.get("lastRunStatus", "never")
            payload = j.get("payload", {})
            ptype = payload.get("type", "?")
            lines.append(
                f"[{status_icon}] {j['id']}  {j['name']}\n"
                f"      Schedule: {sched}\n"
                f"      Next run: {next_str}\n"
                f"      Last: {last_status}  |  Payload: {ptype}"
            )
            if j.get("description"):
                lines[-1] += f"\n      Desc: {j['description']}"
            last_err = state.get("lastError")
            if last_err:
                lines[-1] += f"\n      Error: {last_err}"
        return "\n\n".join(lines)

    def cron_add_exec(name, schedule_type, task, task_type="task",
                      description="", interval_seconds=None,
                      cron_expr=None, run_at=None,
                      delete_after_run=False, enabled=True,
                      confirmed_not_duplicate=False):
        if not confirmed_not_duplicate:
            existing = cron_service.list_jobs()
            if existing:
                summaries = []
                for j in existing:
                    p = j.get("payload", {})
                    prompt_snippet = (p.get("prompt") or p.get("message") or p.get("command") or "")[:120]
                    sched = describe_schedule(j.get("schedule", {}))
                    summaries.append(
                        f"  - [{j['id']}] \"{j['name']}\" ({sched}): {prompt_snippet}"
                    )
                job_list = "\n".join(summaries)
                return (
                    f"DUPLICATE CHECK — before creating \"{name}\", review these existing jobs:\n"
                    f"{job_list}\n\n"
                    f"If none of these already serve the same purpose, call cron_add again "
                    f"with confirmed_not_duplicate=true. "
                    f"If one already does the same thing, tell the user it already exists."
                )

        if schedule_type == "every":
            if not interval_seconds or interval_seconds < 10:
                return "Error: interval_seconds must be >= 10 for 'every' schedule"
            schedule = {"kind": "every", "everyMs": int(interval_seconds * 1000)}
        elif schedule_type == "cron":
            if not cron_expr:
                return "Error: cron_expr is required for 'cron' schedule"
            if not HAS_CRONITER:
                return "Error: croniter package not installed. Run: pip install croniter"
            schedule = {"kind": "cron", "expr": cron_expr}
        elif schedule_type == "at":
            if not run_at:
                return "Error: run_at (ISO datetime) is required for 'at' schedule"
            schedule = {"kind": "at", "at": run_at}
        else:
            return f"Error: Unknown schedule_type '{schedule_type}'. Use: every, cron, at"

        if task_type == "task":
            payload = {"type": "task", "prompt": task}
        elif task_type == "notify":
            payload = {"type": "notify", "title": name, "message": task}
        elif task_type == "shell":
            payload = {"type": "shell", "command": task}
        else:
            return f"Error: Unknown task_type '{task_type}'. Use: task, notify, shell"

        job = cron_service.add_job(
            name=name, schedule=schedule, payload=payload,
            description=description, enabled=enabled,
            delete_after_run=delete_after_run,
        )
        next_run = job.get("state", {}).get("nextRunAtMs")
        next_str = (
            datetime.fromtimestamp(next_run / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if next_run else "N/A"
        )
        return (
            f"Created cron job '{name}' (id: {job['id']})\n"
            f"Schedule: {describe_schedule(schedule)}\n"
            f"Next run: {next_str}\n"
            f"Payload type: {task_type}"
        )

    def cron_remove_exec(job_id):
        ok = cron_service.remove_job(job_id)
        if ok:
            return f"Removed cron job {job_id}"
        return f"Job {job_id} not found"

    def cron_run_exec(job_id):
        ok, msg = cron_service.run_now(job_id)
        return msg

    def cron_status_exec():
        st = cron_service.status()
        lines = [
            f"Cron service: {'RUNNING' if st['running'] else 'STOPPED'}",
            f"Total jobs: {st['total_jobs']}",
            f"Enabled: {st['enabled_jobs']}",
            f"Currently executing: {st['executing']}",
        ]
        if st.get("next_wake"):
            lines.append(f"Next wake: {st['next_wake']}")
        return "\n".join(lines)

    def cron_enable_exec(job_id, enabled=True):
        ok = cron_service.enable_job(job_id, enabled=enabled)
        if ok:
            action = "enabled" if enabled else "disabled"
            return f"Job {job_id} {action}"
        return f"Job {job_id} not found"

    tools = [
        {
            "name": "cron_list",
            "description": "List all scheduled cron jobs with their status, schedule, and next run time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled_only": {
                        "type": "boolean",
                        "description": "Only show enabled jobs",
                        "default": False,
                    },
                },
            },
            "execute": cron_list_exec,
        },
        {
            "name": "cron_add",
            "description": (
                "Create a new scheduled cron job. Schedule types:\n"
                "- 'every': runs at a fixed interval (e.g. every 300 seconds = 5 minutes)\n"
                "- 'cron': standard cron expression (e.g. '0 9 * * *' = daily at 9am)\n"
                "- 'at': one-shot at a specific datetime (ISO format)\n\n"
                "Task types:\n"
                "- 'task': run a prompt through Ghost's AI agent (default)\n"
                "- 'notify': send a system notification\n"
                "- 'shell': execute a shell command"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Job name"},
                    "schedule_type": {
                        "type": "string",
                        "enum": ["every", "cron", "at"],
                        "description": "Schedule type",
                    },
                    "task": {
                        "type": "string",
                        "description": "The prompt, notification message, or shell command",
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["task", "notify", "shell"],
                        "description": "What to do when the job fires",
                        "default": "task",
                    },
                    "description": {"type": "string", "description": "Optional description"},
                    "interval_seconds": {
                        "type": "number",
                        "description": "Interval in seconds (for schedule_type='every', min 10)",
                    },
                    "cron_expr": {
                        "type": "string",
                        "description": "Cron expression (for schedule_type='cron'), e.g. '0 9 * * *'",
                    },
                    "run_at": {
                        "type": "string",
                        "description": "ISO datetime string (for schedule_type='at'), e.g. '2025-12-31T23:59:00'",
                    },
                    "delete_after_run": {
                        "type": "boolean",
                        "description": "Delete the job after it runs (for one-shot 'at' jobs)",
                        "default": False,
                    },
                    "enabled": {"type": "boolean", "default": True},
                    "confirmed_not_duplicate": {
                        "type": "boolean",
                        "description": "Set to true only after reviewing existing jobs and confirming this is not a duplicate",
                        "default": False,
                    },
                },
                "required": ["name", "schedule_type", "task"],
            },
            "execute": cron_add_exec,
        },
        {
            "name": "cron_remove",
            "description": "Remove a scheduled cron job by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job ID to remove"},
                },
                "required": ["job_id"],
            },
            "execute": cron_remove_exec,
        },
        {
            "name": "cron_run",
            "description": "Manually trigger a cron job to run immediately, regardless of its schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job ID to run"},
                },
                "required": ["job_id"],
            },
            "execute": cron_run_exec,
        },
        {
            "name": "cron_status",
            "description": "Get the status of the cron service (running, job count, next wake time).",
            "parameters": {"type": "object", "properties": {}},
            "execute": cron_status_exec,
        },
        {
            "name": "cron_enable",
            "description": "Enable or disable a cron job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job ID"},
                    "enabled": {
                        "type": "boolean",
                        "description": "True to enable, False to disable",
                        "default": True,
                    },
                },
                "required": ["job_id"],
            },
            "execute": cron_enable_exec,
        },
    ]
    return tools
