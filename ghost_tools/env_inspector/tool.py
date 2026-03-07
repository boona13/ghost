import logging

log = logging.getLogger(__name__)


def register(api):
    """Register environment inspector tools."""

    def list_packages(filter_str="", **kwargs):
        """List installed pip packages with optional name filter."""
        from importlib.metadata import distributions
        
        pkgs = []
        for dist in distributions():
            name = dist.metadata.get("Name", "")
            version = dist.version
            if not filter_str or filter_str.lower() in name.lower():
                pkgs.append({"name": name, "version": version})
        
        pkgs.sort(key=lambda x: x["name"].lower())
        return {"packages": pkgs, "count": len(pkgs)}

    def check_dependency(package_name, **kwargs):
        """Check if a package is installed and get its details."""
        from importlib.metadata import distribution, PackageNotFoundError
        
        try:
            dist = distribution(package_name)
            deps = []
            if dist.requires:
                deps = [str(req) for req in dist.requires]
            
            return {
                "installed": True,
                "name": dist.metadata.get("Name", package_name),
                "version": dist.version,
                "location": str(dist.locate_file("") if hasattr(dist, 'locate_file') else ""),
                "dependencies": deps
            }
        except PackageNotFoundError:
            return {"installed": False, "name": package_name, "error": "Package not found"}

    def system_info(**kwargs):
        """Get Python and system environment information."""
        import sys
        import platform
        import shutil
        import os
        
        # Check if in virtual environment
        in_venv = hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        )
        
        # Get pip version
        pip_version = "unknown"
        try:
            import subprocess
            result = subprocess.run([sys.executable, "-m", "pip", "--version"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                pip_version = result.stdout.strip().split()[1]
        except Exception:
            pass
        
        # Disk usage
        disk = shutil.disk_usage("/")
        
        return {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "architecture": platform.machine(),
            "virtual_env": in_venv,
            "venv_path": sys.prefix if in_venv else None,
            "pip_version": pip_version,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_used_percent": round((disk.used / disk.total) * 100, 1)
        }

    api.register_tool({
        "name": "list_packages",
        "description": "List all installed pip packages with versions, optionally filtered by name substring",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_str": {"type": "string", "description": "Optional substring to filter package names", "default": ""}
            }
        },
        "execute": list_packages
    })

    api.register_tool({
        "name": "check_dependency",
        "description": "Check if a package is installed and get its version, location, and dependencies",
        "parameters": {
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Name of the package to check"}
            },
            "required": ["package_name"]
        },
        "execute": check_dependency
    })

    api.register_tool({
        "name": "system_info",
        "description": "Get Python version, OS, architecture, venv status, pip version, and disk space",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "execute": system_info
    })

    log.info("Environment inspector tools registered")
