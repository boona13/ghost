from ghost import DEFAULT_CONFIG
from ghost_tools import make_shell_exec, set_shell_caller_context


def _cfg():
    cfg = dict(DEFAULT_CONFIG)
    return cfg


def test_python_allowed_in_sandbox():
    """In sandbox mode, python commands run freely."""
    set_shell_caller_context("interactive")
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("python --version")
    assert "DENIED" not in out
    assert "python" in out.lower() or "Python" in out


def test_pip_allowed_in_sandbox():
    """In sandbox mode, pip commands run freely."""
    set_shell_caller_context("interactive")
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("pip list")
    assert "DENIED" not in out


def test_arbitrary_command_allowed():
    """Any command should be allowed (no allowlist restriction)."""
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("echo hello sandbox")
    assert "DENIED" not in out
    assert "hello sandbox" in out


def test_blocked_pattern_still_denied():
    """Genuinely destructive patterns are still blocked."""
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("rm -rf /")
    assert "DENIED" in out or "Blocked" in out.lower()


def test_interactive_pip_routes_to_sandbox():
    """Interactive pip resolves to sandbox venv, not Ghost's own."""
    set_shell_caller_context("interactive")
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("which pip")
    assert ".ghost/sandbox/.venv/bin/pip" in out


def test_autonomous_pip_routes_to_ghost_venv():
    """Autonomous pip resolves to Ghost's own .venv."""
    set_shell_caller_context("autonomous")
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("which pip")
    assert "Downloads/IMG/.venv/bin/pip" in out or "sandbox" not in out
