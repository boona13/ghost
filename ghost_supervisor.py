#!/usr/bin/env python3
"""
Ghost Supervisor — lightweight process manager for safe self-evolution restarts.

Launches ghost.py as a child process and handles:
  - Deploy signals (watches ~/.ghost/evolve/deploy_pending)
  - Graceful restarts after self-modification
  - Crash recovery with exponential backoff
  - Auto-rollback after repeated crashes
  - Crash diagnosis: captures stderr and writes crash reports for Ghost to self-repair

Usage:
    python ghost_supervisor.py [ghost.py args...]
    python ghost_supervisor.py --api-key sk-or-... start

This replaces running 'python ghost.py start' directly when self-evolution is active.
"""

import collections
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

GHOST_HOME = Path.home() / ".ghost"
EVOLVE_DIR = GHOST_HOME / "evolve"
DEPLOY_MARKER = EVOLVE_DIR / "deploy_pending"
LAST_DEPLOY_FILE = EVOLVE_DIR / "last_deploy.json"
SHUTDOWN_MARKER = GHOST_HOME / "shutdown_requested"
BACKUP_DIR = EVOLVE_DIR / "backups"
SUPERVISOR_PID_FILE = GHOST_HOME / "supervisor.pid"
SUPERVISOR_LOG = GHOST_HOME / "supervisor.log"
CRASH_REPORT_FILE = GHOST_HOME / "crash_report.json"

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_SCRIPT = PROJECT_DIR / "ghost.py"

MAX_CRASH_COUNT = 5
CRASH_WINDOW = 120
DEPLOY_POLL_INTERVAL = 2
HEALTH_CHECK_DELAY = 5
RESTART_DELAY = 1
STDERR_BUFFER_LINES = 200


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(str(SUPERVISOR_LOG), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_latest_backup():
    backups = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
    return str(backups[-1]) if backups else None


def restore_backup(backup_path):
    """Restore files from a backup archive."""
    import tarfile
    bp = Path(backup_path)
    if not bp.exists():
        log(f"Backup not found: {backup_path}")
        return False
    log(f"Restoring backup: {backup_path}")
    with tarfile.open(str(bp), "r:gz") as tar:
        tar.extractall(path=str(PROJECT_DIR))
    log("Backup restored successfully")
    return True


class StderrCapture:
    """Tee pattern: captures stderr into a ring buffer while printing in real-time."""

    def __init__(self, pipe, maxlines=STDERR_BUFFER_LINES):
        self.pipe = pipe
        self.buffer = collections.deque(maxlen=maxlines)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        try:
            for line in iter(self.pipe.readline, ""):
                sys.stderr.write(line)
                sys.stderr.flush()
                self.buffer.append(line.rstrip("\n"))
        except (ValueError, OSError):
            pass
        finally:
            try:
                self.pipe.close()
            except Exception:
                pass

    def get_tail(self):
        return list(self.buffer)

    def join(self, timeout=2):
        self._thread.join(timeout=timeout)


class GhostSupervisor:
    def __init__(self, ghost_args):
        self.ghost_args = ghost_args
        self.process = None
        self.running = True
        self.crash_times = []
        self.stderr_capture = None
        self._pending_deploy = False
        self._last_deploy_info = None

    def start(self):
        SUPERVISOR_PID_FILE.write_text(str(os.getpid()))
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        SHUTDOWN_MARKER.unlink(missing_ok=True)

        log(f"Supervisor started (PID {os.getpid()})")
        log(f"Ghost args: {self.ghost_args}")

        intentional_exit_codes = (
            0, None,
            -signal.SIGTERM, -signal.SIGINT,
            128 + signal.SIGTERM, 128 + signal.SIGINT,
            signal.SIGTERM, signal.SIGINT,
        )

        try:
            while self.running:
                self._launch_ghost()

                if self._pending_deploy:
                    if not self._post_launch_health_check():
                        continue
                    self._pending_deploy = False

                exit_reason = self._monitor_loop()

                if not self.running or exit_reason == "shutdown":
                    break

                if exit_reason == "deploy" or DEPLOY_MARKER.exists():
                    self._handle_deploy()
                    continue

                rc = self.process.returncode if self.process else 0
                if rc not in intentional_exit_codes:
                    self._handle_crash()
                else:
                    if rc is not None and rc != 0:
                        log(f"Ghost exited with signal-based code {rc} (intentional)")
                    else:
                        log("Ghost exited cleanly")
                    break
        finally:
            self._cleanup()

    def _launch_ghost(self):
        cmd = [sys.executable, "-u", str(GHOST_SCRIPT), "--supervised"] + self.ghost_args
        log(f"Launching: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=sys.stdout,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.stderr_capture = StderrCapture(self.process.stderr)
        log(f"Ghost started (PID {self.process.pid})")

    def _monitor_loop(self):
        """Watch for deploy marker, shutdown marker, or process exit.

        Returns:
            "deploy"   — deploy marker detected, Ghost stopped
            "shutdown" — shutdown requested, Ghost stopped
            "exited"   — Ghost exited on its own
        """
        while self.running and self.process.poll() is None:
            if SHUTDOWN_MARKER.exists():
                log("Shutdown marker detected — stopping Ghost and supervisor")
                SHUTDOWN_MARKER.unlink(missing_ok=True)
                self.running = False
                self._stop_ghost()
                return "shutdown"
            if DEPLOY_MARKER.exists():
                log("Deploy marker detected — initiating graceful restart")
                self._stop_ghost()
                return "deploy"
            time.sleep(DEPLOY_POLL_INTERVAL)
        return "exited"

    def _stop_ghost(self):
        if self.process and self.process.poll() is None:
            log(f"Sending SIGTERM to Ghost (PID {self.process.pid})")
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log("Ghost did not stop in time, sending SIGKILL")
                self.process.kill()
                self.process.wait(timeout=5)
        if self.stderr_capture:
            self.stderr_capture.join(timeout=2)
        log("Ghost stopped")

    def _handle_deploy(self):
        """Process a deploy signal: read marker, persist for new process, clear crash history.

        Writes deploy info to last_deploy.json so the new Ghost process can
        read it on startup (e.g. to auto-complete the deployed feature).
        The deploy_pending marker is then deleted — it's a one-shot signal.
        """
        deploy_info = {}
        try:
            deploy_info = json.loads(DEPLOY_MARKER.read_text())
        except Exception:
            pass

        # Persist deploy context for the new Ghost process before deleting the marker.
        try:
            EVOLVE_DIR.mkdir(parents=True, exist_ok=True)
            LAST_DEPLOY_FILE.write_text(json.dumps(deploy_info, indent=2))
        except Exception as e:
            log(f"Warning: could not write last_deploy.json: {e}")

        DEPLOY_MARKER.unlink(missing_ok=True)
        self._last_deploy_info = deploy_info

        evo_id = deploy_info.get("evolution_id", "unknown")
        is_rollback = deploy_info.get("rollback", False)

        if is_rollback:
            log(f"Processing rollback: {evo_id}")
        else:
            log(f"Deploying evolution: {evo_id}")

        self.crash_times.clear()
        self._pending_deploy = True
        time.sleep(RESTART_DELAY)

    def _post_launch_health_check(self):
        """Run after _launch_ghost during a deploy cycle to verify the new code works."""
        deploy_info = getattr(self, "_last_deploy_info", None) or {}
        is_rollback = deploy_info.get("rollback", False)

        time.sleep(HEALTH_CHECK_DELAY)
        if self.process.poll() is not None:
            log(f"Ghost failed health check (exit code: {self.process.returncode})")
            self._pending_deploy = False
            if not is_rollback:
                backup = deploy_info.get("backup_path") or get_latest_backup()
                if backup:
                    log("Auto-rolling back after failed deploy")
                    restore_backup(backup)
                    time.sleep(RESTART_DELAY)
                else:
                    log("No backup available for auto-rollback!")
            return False
        log("Health check passed — Ghost is running with new code")
        self._last_deploy_info = None
        return True

    def _handle_crash(self):
        rc = self.process.returncode
        now = time.time()
        self.crash_times.append(now)

        self.crash_times = [t for t in self.crash_times if now - t < CRASH_WINDOW]

        stderr_tail = []
        if self.stderr_capture:
            self.stderr_capture.join(timeout=2)
            stderr_tail = self.stderr_capture.get_tail()

        log(f"Ghost crashed (exit code {rc}). Crashes in last {CRASH_WINDOW}s: {len(self.crash_times)}")

        self._write_crash_report(rc, stderr_tail)

        if len(self.crash_times) >= MAX_CRASH_COUNT:
            log(f"Too many crashes ({MAX_CRASH_COUNT} in {CRASH_WINDOW}s) — attempting auto-rollback")
            backup = get_latest_backup()
            if backup:
                if restore_backup(backup):
                    self.crash_times.clear()
                    try:
                        CRASH_REPORT_FILE.unlink(missing_ok=True)
                    except Exception:
                        pass
                    time.sleep(RESTART_DELAY)
                    return
            log("Auto-rollback failed. Stopping supervisor.")
            self.running = False
            return

        delay = min(2 ** len(self.crash_times), 30)
        log(f"Restarting in {delay}s...")
        time.sleep(delay)

    def _write_crash_report(self, exit_code, stderr_tail):
        """Write crash diagnostics for Ghost to self-repair on next startup."""
        report = {
            "exit_code": exit_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stderr_tail": stderr_tail,
            "crash_count": len(self.crash_times),
            "crash_window_seconds": CRASH_WINDOW,
            "max_crashes_before_rollback": MAX_CRASH_COUNT,
        }
        try:
            GHOST_HOME.mkdir(parents=True, exist_ok=True)
            CRASH_REPORT_FILE.write_text(json.dumps(report, indent=2))
            log(f"Crash report written to {CRASH_REPORT_FILE}")
        except Exception as e:
            log(f"Failed to write crash report: {e}")

    def _handle_signal(self, signum, frame):
        log(f"Received signal {signum}")
        self.running = False
        self._stop_ghost()

    def _cleanup(self):
        try:
            SUPERVISOR_PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        if not self.running:
            try:
                CRASH_REPORT_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        log("Supervisor exiting")


def main():
    args = sys.argv[1:]
    if not args:
        args = ["start"]

    supervisor = GhostSupervisor(args)
    supervisor.start()


if __name__ == "__main__":
    main()
