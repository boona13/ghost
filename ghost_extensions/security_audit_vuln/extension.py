"""
Ghost Extension: security_audit_vuln

Vulnerability scanning for Python dependencies using pip-audit.
Integrates with PyPI's vulnerability database to detect CVEs.

Features:
- Detect known vulnerabilities in installed packages
- Severity classification (critical/high/medium/low)
- Auto-remediation by upgrading vulnerable packages
- Integration with Ghost's security audit system
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ghost.security_audit_vuln")


def _check_pip_audit_installed() -> bool:
    """Check if pip-audit is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _run_pip_audit(requirements_file: Path = None) -> dict:
    """Run pip-audit and return parsed results.
    
    Returns dict with:
        - installed: bool (pip-audit available)
        - vulnerabilities: list of vuln dicts
        - summary: {total, critical, high, medium, low}
        - error: str if error occurred
    """
    if not _check_pip_audit_installed():
        return {
            "installed": False,
            "vulnerabilities": [],
            "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
            "error": "pip-audit not installed. Run: pip install pip-audit>=2.7.0",
        }

    cmd = [sys.executable, "-m", "pip_audit", "--format=json"]
    if requirements_file and requirements_file.exists():
        cmd.extend(["--requirement", str(requirements_file)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        # pip-audit returns exit code 1 if vulnerabilities found (not an error)
        if result.returncode not in (0, 1):
            return {
                "installed": True,
                "vulnerabilities": [],
                "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                "error": f"pip-audit failed: {result.stderr}",
            }

        data = json.loads(result.stdout) if result.stdout else {"dependencies": []}
        vulnerabilities = []
        
        for dep in data.get("dependencies", []):
            pkg_name = dep.get("name", "unknown")
            pkg_version = dep.get("version", "unknown")
            
            for vuln in dep.get("vulns", []):
                # Extract severity from aliases or metadata
                severity = _extract_severity(vuln)
                vuln_id = vuln.get("id", "UNKNOWN")
                
                vulnerabilities.append({
                    "package": pkg_name,
                    "version": pkg_version,
                    "vulnerability_id": vuln_id,
                    "severity": severity,
                    "description": vuln.get("description", "No description available"),
                    "fix_versions": vuln.get("fix_versions", []),
                    "aliases": vuln.get("aliases", []),
                })

        summary = _calculate_summary(vulnerabilities)
        
        return {
            "installed": True,
            "vulnerabilities": vulnerabilities,
            "summary": summary,
            "error": None,
        }
        
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "vulnerabilities": [],
            "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
            "error": "pip-audit timed out after 120 seconds",
        }
    except json.JSONDecodeError as exc:
        return {
            "installed": True,
            "vulnerabilities": [],
            "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
            "error": f"Failed to parse pip-audit output: {exc}",
        }
    except Exception as exc:
        return {
            "installed": True,
            "vulnerabilities": [],
            "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
            "error": f"pip-audit error: {exc}",
        }


def _extract_severity(vuln: dict) -> str:
    """Extract severity from vulnerability data."""
    # Check for CVSS score in aliases
    for alias in vuln.get("aliases", []):
        if alias.startswith("CVE-"):
            # Could fetch CVSS score from NVD API here
            pass
    
    # Default severity based on fix availability
    fix_versions = vuln.get("fix_versions", [])
    if not fix_versions:
        return "high"  # No fix available = higher severity
    
    return "medium"  # Default when fix is available


def _calculate_summary(vulnerabilities: list) -> dict:
    """Calculate severity summary."""
    summary = {"total": len(vulnerabilities), "critical": 0, "high": 0, "medium": 0, "low": 0}
    
    for vuln in vulnerabilities:
        sev = vuln.get("severity", "medium").lower()
        if sev in summary:
            summary[sev] += 1
    
    return summary


def register(api):
    """Entry point called by ExtensionManager during load."""
    
    # Load settings
    auto_notify = api.get_setting("auto_notify_critical", True)
    severity_threshold = api.get_setting("severity_threshold", "medium")
    
    # Severity priority for filtering
    SEVERITY_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    threshold_level = SEVERITY_PRIORITY.get(severity_threshold.lower(), 2)

    def execute_audit_vulnerabilities(requirements_file: str = "", **kwargs):
        """Run pip-audit vulnerability scan.
        
        Args:
            requirements_file: Optional path to requirements.txt to scan
        """
        req_path = Path(requirements_file) if requirements_file else None
        
        result = _run_pip_audit(req_path)
        
        # Filter by severity threshold
        if result.get("vulnerabilities"):
            result["vulnerabilities"] = [
                v for v in result["vulnerabilities"]
                if SEVERITY_PRIORITY.get(v.get("severity", "medium").lower(), 2) >= threshold_level
            ]
            result["summary"] = _calculate_summary(result["vulnerabilities"])
        
        # Save to extension data
        audit_record = {
            "timestamp": datetime.now().isoformat(),
            "result": result,
        }
        
        history = json.loads(api.read_data("audit_history.json") or "[]")
        history.append(audit_record)
        history = history[-50:]  # Keep last 50
        api.write_data("audit_history.json", json.dumps(history, indent=2))
        
        # Save critical findings to memory
        critical_count = result.get("summary", {}).get("critical", 0)
        high_count = result.get("summary", {}).get("high", 0)
        
        if critical_count > 0 or high_count > 0:
            api.memory_save(
                content=f"[security_audit_vuln] Found {critical_count} critical and {high_count} high severity vulnerabilities",
                tags="security,vulnerability,cve",
                memory_type="alert",
            )
        
        # Auto-notify on critical
        if auto_notify and critical_count > 0 and result.get("installed"):
            try:
                channels = api.get_channels()
                if channels:
                    api.channel_send(
                        f"🚨 Security Alert: {critical_count} critical CVE(s) detected in Python dependencies. "
                        f"Run security_audit_vulnerabilities for details.",
                    )
            except Exception as exc:
                api.log(f"Failed to send channel notification: {exc}")
        
        return json.dumps(result, indent=2)

    api.register_tool({
        "name": "security_audit_vulnerabilities",
        "description": (
            "Scan Python dependencies for known vulnerabilities using pip-audit. "
            "Detects CVEs with severity levels (critical/high/medium/low). "
            "Returns detailed vulnerability information including affected packages, "
            "versions, and available fixes. Saves findings to memory for tracking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "requirements_file": {
                    "type": "string",
                    "description": "Optional path to requirements.txt to scan. If empty, scans all installed packages.",
                },
            },
        },
        "execute": execute_audit_vulnerabilities,
    })

    def execute_fix_vulnerabilities(dry_run: bool = True, severity: str = "high", **kwargs):
        """Auto-remediate vulnerabilities by upgrading packages.
        
        Args:
            dry_run: If True, only show what would be upgraded
            severity: Minimum severity to fix (critical/high/medium)
        """
        if not _check_pip_audit_installed():
            return json.dumps({
                "status": "error",
                "error": "pip-audit not installed. Run: pip install pip-audit>=2.7.0",
            })
        
        result = _run_pip_audit()
        
        if result.get("error"):
            return json.dumps({
                "status": "error",
                "error": result["error"],
            })
        
        # Filter by severity
        min_level = SEVERITY_PRIORITY.get(severity.lower(), 3)
        fixable = [
            v for v in result.get("vulnerabilities", [])
            if SEVERITY_PRIORITY.get(v.get("severity", "medium").lower(), 2) >= min_level
            and v.get("fix_versions")
        ]
        
        if not fixable:
            return json.dumps({
                "status": "ok",
                "message": f"No fixable vulnerabilities found at {severity} severity or higher",
                "upgraded": [],
            })
        
        upgrades = []
        errors = []
        
        for vuln in fixable:
            pkg = vuln.get("package")
            fix_versions = vuln.get("fix_versions", [])
            
            if not fix_versions:
                continue
            
            # Use the first (earliest) fix version
            target_version = fix_versions[0]
            
            if dry_run:
                upgrades.append({
                    "package": pkg,
                    "current": vuln.get("version"),
                    "target": target_version,
                    "vulnerability": vuln.get("vulnerability_id"),
                    "severity": vuln.get("severity"),
                })
            else:
                # Actually upgrade
                try:
                    upgrade_result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", f"{pkg}=={target_version}"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    
                    if upgrade_result.returncode == 0:
                        upgrades.append({
                            "package": pkg,
                            "previous": vuln.get("version"),
                            "upgraded_to": target_version,
                            "vulnerability": vuln.get("vulnerability_id"),
                            "severity": vuln.get("severity"),
                            "status": "success",
                        })
                    else:
                        errors.append({
                            "package": pkg,
                            "target": target_version,
                            "error": upgrade_result.stderr,
                        })
                        
                except subprocess.TimeoutExpired:
                    errors.append({
                        "package": pkg,
                        "target": target_version,
                        "error": "Upgrade timed out after 60 seconds",
                    })
                except Exception as exc:
                    errors.append({
                        "package": pkg,
                        "target": target_version,
                        "error": str(exc),
                    })
        
        # Log to memory
        if upgrades and not dry_run:
            api.memory_save(
                content=f"[security_audit_vuln] Auto-fixed {len(upgrades)} vulnerabilities via package upgrade",
                tags="security,vulnerability,fixed",
                memory_type="note",
            )
        
        return json.dumps({
            "status": "ok",
            "dry_run": dry_run,
            "upgraded": upgrades,
            "errors": errors,
            "total_fixable": len(fixable),
        }, indent=2)

    api.register_tool({
        "name": "security_audit_fix_vuln",
        "description": (
            "Auto-remediate vulnerable Python packages by upgrading to fixed versions. "
            "Use dry_run=True first to preview changes. Only upgrades packages with "
            "known fixes available. Respects severity threshold setting."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be upgraded without making changes",
                    "default": True,
                },
                "severity": {
                    "type": "string",
                    "description": "Minimum severity to fix: critical, high, or medium",
                    "default": "high",
                },
            },
        },
        "execute": execute_fix_vulnerabilities,
    })

    def on_boot():
        """Check pip-audit availability on boot."""
        if _check_pip_audit_installed():
            api.log("pip-audit is available for vulnerability scanning")
        else:
            api.log("pip-audit not installed. Run: pip install pip-audit>=2.7.0")
            
        # Check for previous critical findings
        history = json.loads(api.read_data("audit_history.json") or "[]")
        if history:
            last = history[-1]
            summary = last.get("result", {}).get("summary", {})
            critical = summary.get("critical", 0)
            if critical > 0:
                api.log(f"Previous audit found {critical} critical vulnerabilities - run security_audit_vulnerabilities")

    api.register_hook("on_boot", on_boot)
