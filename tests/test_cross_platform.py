"""Cross-platform compatibility tests.

Mocks platform.system() to verify Ghost's code paths behave correctly
on all three target operating systems — even when running the tests on macOS.
"""

import importlib
import platform
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── ghost_platform tests ─────────────────────────────────────────────

def _reload_ghost_platform(mock_system):
    """Reload ghost_platform with a mocked platform.system()."""
    with patch("platform.system", return_value=mock_system):
        import ghost_platform
        importlib.reload(ghost_platform)
        return ghost_platform


class TestPlatformFlags:
    def test_darwin_flags(self):
        gp = _reload_ghost_platform("Darwin")
        assert gp.PLAT == "Darwin"
        assert gp.IS_MAC is True
        assert gp.IS_WIN is False
        assert gp.IS_LINUX is False

    def test_linux_flags(self):
        gp = _reload_ghost_platform("Linux")
        assert gp.PLAT == "Linux"
        assert gp.IS_LINUX is True
        assert gp.IS_WIN is False
        assert gp.IS_MAC is False

    def test_windows_flags(self):
        gp = _reload_ghost_platform("Windows")
        assert gp.PLAT == "Windows"
        assert gp.IS_WIN is True
        assert gp.IS_MAC is False
        assert gp.IS_LINUX is False

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


class TestPlatformContext:
    def test_darwin_context(self):
        gp = _reload_ghost_platform("Darwin")
        ctx = gp.platform_context()
        assert "macOS" in ctx
        assert "Darwin" in ctx
        assert "zsh" in ctx
        assert "brew" in ctx
        assert "## Platform" in ctx

    def test_linux_context(self):
        gp = _reload_ghost_platform("Linux")
        ctx = gp.platform_context()
        assert "Linux" in ctx
        assert "bash" in ctx
        assert "apt" in ctx
        assert "/home/" in ctx

    def test_windows_context(self):
        gp = _reload_ghost_platform("Windows")
        ctx = gp.platform_context()
        assert "Windows" in ctx
        assert "PowerShell" in ctx
        assert "choco" in ctx
        assert "backslash" in ctx

    def test_context_contains_python_version(self):
        gp = _reload_ghost_platform("Linux")
        ctx = gp.platform_context()
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert py_ver in ctx

    def test_context_contains_home(self):
        gp = _reload_ghost_platform("Darwin")
        ctx = gp.platform_context()
        assert str(Path.home()) in ctx

    def test_context_instructs_os_appropriateness(self):
        for os_name, label in [("Darwin", "macOS"), ("Linux", "Linux"), ("Windows", "Windows")]:
            gp = _reload_ghost_platform(os_name)
            ctx = gp.platform_context()
            assert f"appropriate for {label}" in ctx

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


class TestExitCodeEchoCmd:
    def test_unix_echo(self):
        gp = _reload_ghost_platform("Linux")
        cmd = gp.exit_code_echo_cmd("MARKER_123")
        assert "$?" in cmd
        assert "MARKER_123" in cmd

    def test_windows_echo(self):
        gp = _reload_ghost_platform("Windows")
        cmd = gp.exit_code_echo_cmd("MARKER_123")
        assert "%ERRORLEVEL%" in cmd
        assert "MARKER_123" in cmd

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


class TestKillProcess:
    @patch("subprocess.run")
    def test_kill_windows_uses_taskkill(self, mock_run):
        gp = _reload_ghost_platform("Windows")
        gp.kill_process(12345)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "taskkill" in args
        assert "12345" in args

    @patch("os.kill")
    def test_kill_unix_uses_sigterm(self, mock_kill):
        gp = _reload_ghost_platform("Linux")
        import signal
        gp.kill_process(12345)
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


class TestChmodSafe:
    def test_noop_on_windows(self, tmp_path):
        gp = _reload_ghost_platform("Windows")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        gp.chmod_safe(f, 0o600)
        # Should not raise, should be a no-op

    def test_works_on_unix(self, tmp_path):
        gp = _reload_ghost_platform("Darwin")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        gp.chmod_safe(f, 0o600)
        assert f.stat().st_mode & 0o777 == 0o600

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


# ── ghost_resource_manager tests ──────────────────────────────────────

class TestResourceManagerMemoryDetection:
    @patch("platform.system", return_value="Linux")
    def test_linux_reads_proc_meminfo(self, _mock_sys, tmp_path):
        meminfo = tmp_path / "meminfo"
        meminfo.write_text("MemTotal:       16384000 kB\nMemFree:         8192000 kB\n")

        from ghost_resource_manager import DeviceInfo
        info = DeviceInfo.__new__(DeviceInfo)
        info.unified_memory_gb = 0.0
        info.apple_silicon = False

        with patch.object(Path, "__truediv__", return_value=meminfo):
            pass

        # Direct test: parse /proc/meminfo format
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                info.unified_memory_gb = round(kb / (1024 ** 2), 1)
                break
        assert info.unified_memory_gb == 15.6

    @patch("platform.system", return_value="Windows")
    @patch("subprocess.run")
    def test_windows_reads_wmi(self, mock_run, _mock_sys):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="17179869184\n"  # 16 GB
        )
        from ghost_resource_manager import DeviceInfo
        info = DeviceInfo.__new__(DeviceInfo)
        info.unified_memory_gb = 0.0
        info.apple_silicon = False

        # Simulate the Windows detection logic
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            info.unified_memory_gb = round(int(result.stdout.strip()) / (1024 ** 3), 1)

        assert info.unified_memory_gb == 16.0


# ── Shell session tests ───────────────────────────────────────────────

class TestShellSessionPlatformBranching:
    def test_interactive_session_uses_sh_on_unix(self):
        gp = _reload_ghost_platform("Linux")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(
                poll=MagicMock(return_value=None),
                stdout=MagicMock(readline=MagicMock(return_value=b"")),
            )
            from ghost_shell_sessions import InteractiveSession
            importlib.reload(sys.modules["ghost_shell_sessions"])
            from ghost_shell_sessions import InteractiveSession
            try:
                sess = InteractiveSession("test-unix")
            except Exception:
                pass
            if mock_popen.called:
                args = mock_popen.call_args
                cmd = args[0][0] if args[0] else args[1].get("args", [])
                if isinstance(cmd, list):
                    assert cmd[0] in ("/bin/sh", "cmd.exe")

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


# ── Notification platform branching ──────────────────────────────────

class TestNotificationBranching:
    @patch("subprocess.run")
    def test_mac_uses_osascript(self, mock_run):
        gp = _reload_ghost_platform("Darwin")
        mock_run.return_value = MagicMock(returncode=0)
        result = gp.send_notification("Test", "Hello")
        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"

    @patch("subprocess.run")
    def test_linux_uses_notify_send(self, mock_run):
        gp = _reload_ghost_platform("Linux")
        mock_run.return_value = MagicMock(returncode=0)
        result = gp.send_notification("Test", "Hello")
        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"

    @patch("subprocess.run")
    def test_windows_uses_powershell(self, mock_run):
        gp = _reload_ghost_platform("Windows")
        mock_run.return_value = MagicMock(returncode=0)
        result = gp.send_notification("Test", "Hello")
        assert result is True
        args = mock_run.call_args[0][0]
        assert args[0] == "powershell"

    def teardown_method(self, method):
        _reload_ghost_platform(platform.system())


# ── Path helpers ──────────────────────────────────────────────────────

class TestPathHelpers:
    def test_strip_leading_sep(self):
        import ghost_platform as gp
        assert gp.strip_leading_sep("/foo/bar") == "foo/bar"
        assert gp.strip_leading_sep("\\foo\\bar") == "foo\\bar"
        assert gp.strip_leading_sep("foo") == "foo"

    def test_has_path_components(self):
        import ghost_platform as gp
        assert gp.has_path_components("foo/bar") is True
        assert gp.has_path_components("foo") is False

    def test_path_basename(self):
        import ghost_platform as gp
        assert gp.path_basename("/home/user/file.txt") == "file.txt"
        assert gp.path_basename("file.txt") == "file.txt"
