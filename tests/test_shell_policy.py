from ghost import DEFAULT_CONFIG
from ghost_tools import make_shell_exec


def _cfg():
    cfg = dict(DEFAULT_CONFIG)
    return cfg


def test_python_denied_without_workspace():
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("python --version")
    assert out.startswith("DENIED:")
    assert "workspace" in out.lower()


def test_python_denied_untrusted_without_confirmation_even_with_workspace():
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("python --version", workspace="tmp-proj")
    assert out.startswith("DENIED:")
    assert "elevated confirmation" in out.lower()


def test_python_allowed_trusted_with_workspace():
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("python --version", workspace="tmp-proj", trusted_context=True)
    assert "Python" in out or "python" in out


def test_pip_install_denied_untrusted_without_confirmation():
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("pip install requests", workspace="tmp-proj")
    assert out.startswith("DENIED:")
    assert "elevated confirmation" in out.lower()


def test_pip_install_allowed_trusted_with_workspace():
    tool = make_shell_exec(_cfg())
    out = tool["execute"]("pip list", workspace="tmp-proj", trusted_context=True)
    assert "DENIED:" not in out
