"""
ghost_platform.py — Cross-platform utility helpers for Ghost.

Centralises OS-specific logic so the rest of the codebase can call a
single, portable API instead of scattering platform checks everywhere.
"""

import logging
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import List, Set

log = logging.getLogger(__name__)

PLAT: str = platform.system()          # "Darwin" | "Linux" | "Windows"
IS_WIN: bool = PLAT == "Windows"
IS_MAC: bool = PLAT == "Darwin"
IS_LINUX: bool = PLAT == "Linux"

# ── Path helpers ─────────────────────────────────────────────────────

def path_basename(p: str) -> str:
    """Cross-platform basename — handles both ``/`` and ``\\``."""
    return Path(p).name


def has_path_components(p: str) -> bool:
    """True when *p* contains directory components (not a bare filename)."""
    return len(Path(p).parts) > 1


def strip_leading_sep(p: str) -> str:
    """Strip leading path separators (``/`` and ``\\``)."""
    return p.strip().lstrip("/\\")


def is_root_path(p: str) -> bool:
    """Check whether *p* represents the filesystem root on any platform."""
    try:
        resolved = str(Path(p).resolve())
    except (OSError, ValueError):
        return False
    if IS_WIN:
        # e.g. "C:\\"
        return len(resolved) <= 3 and resolved[1:3] == ":\\"
    return resolved == "/"


# ── Process helpers ──────────────────────────────────────────────────

def kill_process(pid: int) -> None:
    """Terminate a single process, cross-platform."""
    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def kill_process_group(pid: int) -> None:
    """Kill an entire process group; falls back to tree-kill on Windows."""
    if hasattr(os, "killpg"):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    # Windows (or Unix fallback)
    try:
        if IS_WIN:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def find_ghost_processes(my_pid: int) -> List[int]:
    """Return PIDs of other running ``ghost.py start`` processes."""
    pids: List[int] = []
    try:
        if IS_WIN:
            ps_cmd = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -like '*ghost.py start*' } | "
                "Select-Object -ExpandProperty ProcessId"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.strip().splitlines():
                tok = line.strip()
                if tok.isdigit() and int(tok) != my_pid:
                    pids.append(int(tok))
        else:
            r = subprocess.run(
                ["pgrep", "-f", "ghost.py start"],
                capture_output=True, text=True, timeout=3,
            )
            for line in r.stdout.strip().splitlines():
                tok = line.strip()
                if tok.isdigit() and int(tok) != my_pid:
                    pids.append(int(tok))
    except Exception:
        pass
    return pids


# ── Subprocess helpers ───────────────────────────────────────────────

def popen_detached(cmd, cwd=None, **extra):
    """Launch a fully detached subprocess (daemon-style), cross-platform."""
    kwargs = {
        "cwd": cwd,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        **extra,
    }
    if IS_WIN:
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def popen_new_session(cmd, **kwargs):
    """``Popen`` with ``start_new_session`` on Unix, ``creationflags`` on Windows."""
    if IS_WIN:
        kwargs.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


# ── Notification helper ──────────────────────────────────────────────

def send_notification(title: str, message: str, sound: bool = True) -> bool:
    """Best-effort cross-platform desktop notification. Returns True on success."""
    try:
        if IS_MAC:
            sound_str = 'sound name "default"' if sound else ""
            osa = f'display notification "{message}" with title "{title}" {sound_str}'
            subprocess.run(["osascript", "-e", osa], capture_output=True, timeout=5)
            return True
        if IS_LINUX:
            subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)
            return True
        if IS_WIN:
            ps_cmd = (
                '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; '
                '$n = New-Object System.Windows.Forms.NotifyIcon; '
                '$n.Icon = [System.Drawing.SystemIcons]::Information; '
                '$n.Visible = $true; '
                f'$n.ShowBalloonTip(5000, "{title}", "{message}", '
                '[System.Windows.Forms.ToolTipIcon]::Info)'
            )
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
            return True
    except Exception:
        pass
    return False


# ── Filesystem permission helper ─────────────────────────────────────

def chmod_safe(path: Path, mode: int) -> None:
    """``chmod`` wrapper that is a silent no-op on Windows."""
    if IS_WIN:
        return
    try:
        path.chmod(mode)
    except OSError as exc:
        log.debug("chmod_safe(%s, %o) failed: %s", path, mode, exc)


# ── Sandbox / security helpers ───────────────────────────────────────

def blocked_host_paths() -> Set[str]:
    """Platform-specific host paths that should never be bind-mounted into containers."""
    if IS_WIN:
        sys_root = os.environ.get("SystemRoot", r"C:\Windows")
        return {sys_root, r"C:\Program Files", r"C:\Program Files (x86)"}
    return {"/etc", "/proc", "/sys", "/dev", "/root", "/run/docker.sock"}


# ── Shell session helpers ────────────────────────────────────────────

def exit_code_echo_cmd(marker: str) -> str:
    """Shell snippet that echoes *marker* followed by the last exit code."""
    if IS_WIN:
        return f"echo {marker}%ERRORLEVEL%"
    return f'echo "{marker}$?"'


# ── Console / ANSI helpers ──────────────────────────────────────────

def enable_ansi_colors() -> None:
    """Enable ANSI escape-code processing on Windows 10+ consoles.

    On Unix this is a no-op. On Windows it calls SetConsoleMode to turn on
    ENABLE_VIRTUAL_TERMINAL_PROCESSING so that ANSI color codes render
    correctly in cmd.exe and PowerShell.
    """
    if not IS_WIN:
        return
    try:
        import ctypes
        import ctypes.wintypes as wt
        kernel32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        STD_OUTPUT_HANDLE = -11
        ENABLE_VTP = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = wt.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VTP)
        STD_ERROR_HANDLE = -12
        handle_err = kernel32.GetStdHandle(STD_ERROR_HANDLE)
        mode_err = wt.DWORD()
        if kernel32.GetConsoleMode(handle_err, ctypes.byref(mode_err)):
            kernel32.SetConsoleMode(handle_err, mode_err.value | ENABLE_VTP)
    except Exception:
        pass


# ── UTF-8 console encoding ─────────────────────────────────────────

def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows to avoid UnicodeEncodeError.

    On Unix this is a no-op because the default encoding is already UTF-8.
    """
    if not IS_WIN:
        return
    try:
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name, None)
            if stream and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
