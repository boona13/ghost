"""
ghost_sandbox.py — Docker-based sandboxing for safe evolution testing.

Mirrored from OpenClaw's sandbox architecture.
All Docker interaction via CLI (no Docker SDK).
Containers kept alive with `sleep infinity`, commands run via `docker exec`.
"""

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_DIR = Path.home() / ".ghost"
SANDBOX_DIR = GHOST_DIR / "sandbox"
REGISTRY_FILE = SANDBOX_DIR / "containers.json"

BLOCKED_HOST_PATHS = {"/etc", "/proc", "/sys", "/dev", "/root", "/run/docker.sock"}
BLOCKED_NETWORK_MODES = {"host"}
HOT_CONTAINER_GRACE_SEC = 300
PRUNE_MIN_INTERVAL_SEC = 300


@dataclass
class SandboxConfig:
    image: str = "ghost-sandbox:bookworm-slim"
    container_prefix: str = "ghost-sbx-"
    workdir: str = "/workspace"
    read_only_root: bool = True
    tmpfs: list[str] = field(default_factory=lambda: ["/tmp", "/var/tmp", "/run"])
    network: str = "none"
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    memory: str = "512m"
    cpus: float = 1.0
    pids_limit: int = 256
    workspace_access: str = "ro"
    setup_command: str | None = None
    prune_idle_hours: int = 24
    prune_max_age_days: int = 7


# ---------------------------------------------------------------------------
# Docker CLI helpers
# ---------------------------------------------------------------------------

def docker_available() -> bool:
    """Check if Docker daemon is reachable."""
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def exec_docker(args: list[str], timeout: int = 30, allow_failure: bool = False) -> dict:
    """Run `docker <args>` and return {stdout, stderr, returncode}."""
    cmd = ["docker"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 and not allow_failure:
            raise RuntimeError(f"docker {args[0]} failed ({r.returncode}): {r.stderr.strip()[:500]}")
        return {"stdout": r.stdout.strip(), "stderr": r.stderr.strip(), "returncode": r.returncode}
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"docker {args[0]} timed out after {timeout}s")


def docker_container_state(name: str) -> dict:
    """Returns {exists: bool, running: bool} for a container."""
    try:
        result = exec_docker(
            ["inspect", "--format", "{{.State.Running}}", name],
            allow_failure=True,
        )
        if result["returncode"] != 0:
            return {"exists": False, "running": False}
        running = result["stdout"].strip().lower() == "true"
        return {"exists": True, "running": running}
    except RuntimeError:
        return {"exists": False, "running": False}


def ensure_docker_image(image: str) -> bool:
    """Ensure the sandbox image exists with python3 installed.
    
    Builds from debian:bookworm-slim with python3 pre-installed so
    evolve_test and other sandbox operations can run Python code.
    """
    result = exec_docker(["image", "inspect", image], allow_failure=True)
    if result["returncode"] == 0:
        # Verify python3 is actually present (handles images built before this fix)
        check = exec_docker(
            ["run", "--rm", image, "python3", "--version"],
            allow_failure=True, timeout=10,
        )
        if check["returncode"] == 0:
            return True
        # python3 missing — rebuild the image

    base = "debian:bookworm-slim"
    try:
        exec_docker(["pull", base], timeout=120)
        # Build image with python3 installed
        container_name = "ghost-sbx-build-tmp"
        exec_docker(["rm", "-f", container_name], allow_failure=True)
        exec_docker(["create", "--name", container_name, base, "sleep", "infinity"], timeout=30)
        exec_docker(["start", container_name], timeout=10)
        exec_docker(
            ["exec", container_name, "sh", "-c",
             "apt-get update -qq && apt-get install -y -qq python3 python3-pip > /dev/null 2>&1"],
            timeout=180,
        )
        exec_docker(["commit", container_name, image], timeout=60)
        exec_docker(["rm", "-f", container_name], allow_failure=True)
        return True
    except RuntimeError:
        # Cleanup on failure
        exec_docker(["rm", "-f", "ghost-sbx-build-tmp"], allow_failure=True)
        return False


# ---------------------------------------------------------------------------
# Security validation
# ---------------------------------------------------------------------------

def validate_sandbox_security(cfg: SandboxConfig) -> list[str]:
    """Validate config for dangerous settings. Returns list of issues (empty = OK)."""
    issues = []

    if cfg.network in BLOCKED_NETWORK_MODES:
        issues.append(f"Network mode '{cfg.network}' is blocked for sandbox isolation")

    ws_path = str(PROJECT_DIR)
    for blocked in BLOCKED_HOST_PATHS:
        if ws_path.startswith(blocked):
            issues.append(f"Workspace path '{ws_path}' overlaps with blocked path '{blocked}'")

    if cfg.workspace_access not in ("ro", "rw", "none"):
        issues.append(f"Invalid workspace_access '{cfg.workspace_access}', must be ro/rw/none")

    if "ALL" not in cfg.cap_drop:
        issues.append("cap_drop should include 'ALL' for maximum isolation")

    return issues


# ---------------------------------------------------------------------------
# Config hash for idempotent create/recreate
# ---------------------------------------------------------------------------

def config_hash(cfg: SandboxConfig) -> str:
    """SHA-256 of sorted config for idempotent container management."""
    d = {
        "image": cfg.image,
        "read_only_root": cfg.read_only_root,
        "tmpfs": sorted(cfg.tmpfs),
        "network": cfg.network,
        "cap_drop": sorted(cfg.cap_drop),
        "memory": cfg.memory,
        "cpus": cfg.cpus,
        "pids_limit": cfg.pids_limit,
        "workspace_access": cfg.workspace_access,
    }
    raw = json.dumps(d, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Build docker create args
# ---------------------------------------------------------------------------

def build_create_args(cfg: SandboxConfig, container_name: str, host_workspace: str) -> list[str]:
    """Build the full `docker create` argument list."""
    args = ["create", "--name", container_name]

    if cfg.read_only_root:
        args.append("--read-only")

    for mount in cfg.tmpfs:
        args.extend(["--tmpfs", mount])

    args.extend(["--network", cfg.network])

    for cap in cfg.cap_drop:
        args.extend(["--cap-drop", cap])

    args.extend(["--security-opt", "no-new-privileges"])
    args.extend(["--pids-limit", str(cfg.pids_limit)])
    args.extend(["--memory", cfg.memory])
    args.extend(["--cpus", str(cfg.cpus)])

    if cfg.workspace_access != "none":
        mode = cfg.workspace_access
        args.extend(["-v", f"{host_workspace}:{cfg.workdir}:{mode}"])

    args.extend(["-w", cfg.workdir])

    chash = config_hash(cfg)
    args.extend([
        "--label", "ghost.sandbox=1",
        "--label", f"ghost.created_at_ms={int(time.time() * 1000)}",
        "--label", f"ghost.config_hash={chash}",
    ])

    args.extend(["--entrypoint", "sleep"])
    args.append(cfg.image)
    args.append("infinity")

    return args


# ---------------------------------------------------------------------------
# Sandbox Registry (JSON persistence with file-locking)
# ---------------------------------------------------------------------------

class SandboxRegistry:
    """Persists container metadata to JSON at ~/.ghost/sandbox/containers.json."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path or REGISTRY_FILE)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_raw(self, entries: list[dict]):
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2))
        tmp.replace(self._path)

    def read(self) -> list[dict]:
        return self._read_raw()

    def update(self, entry: dict):
        """Upsert by container_name."""
        entries = self._read_raw()
        found = False
        for i, e in enumerate(entries):
            if e.get("container_name") == entry["container_name"]:
                entries[i] = {**e, **entry}
                found = True
                break
        if not found:
            entries.append(entry)
        self._write_raw(entries)

    def remove(self, name: str):
        entries = [e for e in self._read_raw() if e.get("container_name") != name]
        self._write_raw(entries)


# ---------------------------------------------------------------------------
# Sandbox Manager
# ---------------------------------------------------------------------------

class SandboxManager:
    """Main lifecycle manager for sandbox containers."""

    def __init__(self, cfg: SandboxConfig | None = None):
        self._cfg = cfg or SandboxConfig()
        self._registry = SandboxRegistry()
        self._last_prune = 0.0

    @staticmethod
    def _verify_python3(container_name: str) -> bool:
        """Check if python3 is available inside a running container."""
        try:
            result = exec_docker(
                ["exec", container_name, "sh", "-lc", "python3 --version"],
                timeout=5, allow_failure=True,
            )
            return result["returncode"] == 0
        except RuntimeError:
            return False

    def _container_name(self, session_key: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", session_key)[:32]
        return f"{self._cfg.container_prefix}{slug}"

    def ensure_container(self, session_key: str, cfg: SandboxConfig | None = None) -> str:
        """Create / start / reuse a container. Returns container name."""
        cfg = cfg or self._cfg
        name = self._container_name(session_key)
        chash = config_hash(cfg)

        issues = validate_sandbox_security(cfg)
        if issues:
            raise RuntimeError(f"Sandbox security validation failed: {'; '.join(issues)}")

        if not ensure_docker_image(cfg.image):
            raise RuntimeError(f"Failed to ensure Docker image '{cfg.image}'")

        state = docker_container_state(name)

        if state["exists"]:
            reg_entries = self._registry.read()
            old_hash = None
            last_used = 0
            for e in reg_entries:
                if e.get("container_name") == name:
                    old_hash = e.get("config_hash")
                    last_used = e.get("last_used_at_ms", 0)
                    break

            idle_sec = (time.time() * 1000 - last_used) / 1000 if last_used else float("inf")
            need_recreate = old_hash and old_hash != chash and idle_sec > HOT_CONTAINER_GRACE_SEC

            if need_recreate:
                exec_docker(["rm", "-f", name], allow_failure=True)
                state = {"exists": False, "running": False}
            elif not state["running"]:
                exec_docker(["start", name])
                if not self._verify_python3(name):
                    exec_docker(["rm", "-f", name], allow_failure=True)
                    state = {"exists": False, "running": False}
                else:
                    self._registry.update({
                        "container_name": name,
                        "last_used_at_ms": int(time.time() * 1000),
                        "config_hash": chash,
                    })
                    return name
            else:
                if not self._verify_python3(name):
                    exec_docker(["rm", "-f", name], allow_failure=True)
                    state = {"exists": False, "running": False}
                else:
                    self._registry.update({
                        "container_name": name,
                        "last_used_at_ms": int(time.time() * 1000),
                    })
                    return name

        create_args = build_create_args(cfg, name, str(PROJECT_DIR))
        exec_docker(create_args, timeout=30)
        exec_docker(["start", name])

        if cfg.setup_command:
            try:
                exec_docker(
                    ["exec", name, "sh", "-c", cfg.setup_command],
                    timeout=60, allow_failure=True,
                )
            except RuntimeError:
                pass

        self._registry.update({
            "container_name": name,
            "created_at_ms": int(time.time() * 1000),
            "last_used_at_ms": int(time.time() * 1000),
            "config_hash": chash,
        })
        return name

    def exec_in_sandbox(self, container_name: str, command: str, timeout: int = 30) -> dict:
        """Run a command inside the sandbox. Returns {stdout, stderr, returncode}.
        Uses login shell (-lc) to ensure proper PATH (python3, etc.)."""
        return exec_docker(
            ["exec", "-i", container_name, "sh", "-lc", command],
            timeout=timeout, allow_failure=True,
        )

    def destroy(self, container_name: str):
        """Force-remove a container."""
        exec_docker(["rm", "-f", container_name], allow_failure=True)
        self._registry.remove(container_name)

    def prune(self, idle_hours: int | None = None, max_age_days: int | None = None):
        """Remove idle and old containers. Rate-limited to every 5 min."""
        now = time.time()
        if now - self._last_prune < PRUNE_MIN_INTERVAL_SEC:
            return
        self._last_prune = now

        idle_hours = idle_hours or self._cfg.prune_idle_hours
        max_age_days = max_age_days or self._cfg.prune_max_age_days
        idle_ms = idle_hours * 3600 * 1000
        age_ms = max_age_days * 86400 * 1000
        now_ms = int(now * 1000)

        for entry in self._registry.read():
            name = entry.get("container_name", "")
            last_used = entry.get("last_used_at_ms", 0)
            created = entry.get("created_at_ms", 0)

            too_idle = (now_ms - last_used) > idle_ms if last_used else False
            too_old = (now_ms - created) > age_ms if created else False

            if too_idle or too_old:
                self.destroy(name)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global _manager
    if _manager is None:
        _manager = SandboxManager()
    return _manager


# ---------------------------------------------------------------------------
# Tool builder
# ---------------------------------------------------------------------------

def build_sandbox_tools() -> list[dict]:
    """Build sandbox_exec tool for Ghost's tool registry."""
    return [_make_sandbox_exec()]


def _make_sandbox_exec() -> dict:
    def execute(command: str, session_key: str = "default", timeout: int = 30):
        if not docker_available():
            return "Docker is not available. Cannot run sandbox commands."
        mgr = get_sandbox_manager()
        try:
            name = mgr.ensure_container(session_key)
            result = mgr.exec_in_sandbox(name, command, timeout=timeout)
            output = result["stdout"]
            if result["stderr"]:
                output += f"\n[stderr] {result['stderr']}"
            if result["returncode"] != 0:
                output += f"\n[exit code: {result['returncode']}]"
            return output or "(no output)"
        except RuntimeError as e:
            return f"Sandbox error: {e}"

    return {
        "name": "sandbox_exec",
        "description": (
            "Execute a command in an isolated Docker sandbox. "
            "Safe for testing code changes — the sandbox has no network, "
            "read-only workspace mount, and resource limits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run inside the sandbox"},
                "session_key": {"type": "string", "default": "default", "description": "Session key for container reuse"},
                "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
            },
            "required": ["command"],
        },
        "execute": execute,
    }
