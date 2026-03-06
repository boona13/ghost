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


def _run_pip_audit(requirements_file: Path = None, allowed_roots: list = None) -> dict:
    """Run pip-audit and return parsed results.
    
    Args:
        requirements_file: Optional path to requirements.txt (must be within allowed_roots)
        allowed_roots: List of allowed directory roots for path validation
    
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

    # Validate requirements_file path to prevent path traversal
    if requirements_file:
        try:
            req_path = Path(requirements_file).resolve()
            # Default allowed roots if none provided
            roots = allowed_roots or [Path.cwd().resolve()]
            # Ensure the file is within allowed roots using proper path comparison
            is_allowed = any(req_path.is_relative_to(Path(r).resolve()) for r in roots)
            if not is_allowed:
                return {
                    "installed": True,
                    "vulnerabilities": [],
                    "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                    "error": f"Requirements file path not allowed: {requirements_file}",
                }
            if not req_path.exists():
                return {
                    "installed": True,
                    "vulnerabilities": [],
                    "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                    "error": f"Requirements file not found: {requirements_file}",
                }
            requirements_file = req_path
        except (OSError, ValueError) as exc:
            return {
                "installed": True,
                "vulnerabilities": [],
                "summary": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0},
                "error": f"Invalid requirements file path: {exc}",
            }

    cmd = [sys.executable, "-m", "pip_audit", "--format=json", "--desc"]
    if requirements_file:
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
    """Extract severity from vulnerability data using pip-audit CVSS data.
    
    pip-audit provides severity in the 'severity' field with CVSS scores.
    Maps CVSS scores to severity levels:
    - Critical: 9.0-10.0
    - High: 7.0-8.9
    - Medium: 4.0-6.9
    - Low: 0.1-3.9
    """
    # Use pip-audit's severity field if available
    severity_data = vuln.get("severity")
    if severity_data:
        # Handle both string and dict formats
        if isinstance(severity_data, dict):
            score = severity_data.get("score")
            if score is not None:
                try:
                    score_val = float(score)
                    if score_val >= 9.0:
                        return "critical"
                    elif score_val >= 7.0:
                        return "high"
                    elif score_val >= 4.0:
                        return "medium"
                    else:
                        return "low"
                except (ValueError, TypeError):
                    pass
            # Check for severity label in dict
            label = severity_data.get("label", "").lower()
            if label in ("critical", "high", "medium", "low"):
                return label
        elif isinstance(severity_data, str):
            sev_lower = severity_data.lower()
            if sev_lower in ("critical", "high", "medium", "low"):
                return sev_lower
    
    # Check for CVSS score in metadata
    metadata = vuln.get("metadata", {})
    cvss_score = metadata.get("cvss_score")
    if cvss_score is not None:
        try:
            score_val = float(cvss_score)
            if score_val >= 9.0:
                return "critical"
            elif score_val >= 7.0:
                return "high"
            elif score_val >= 4.0:
                return "medium"
            else:
                return "low"
        except (ValueError, TypeError):
            pass
    
    # Fallback: no fix available = higher severity
    fix_versions = vuln.get("fix_versions", [])
    if not fix_versions:
        return "high"
    
    return "medium"


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
    
    # Severity priority for filtering (constant)
    SEVERITY_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    def execute_audit_vulnerabilities(requirements_file: str = "", **kwargs):
        """Run pip-audit vulnerability scan.
        
        Args:
            requirements_file: Optional path to requirements.txt to scan (must be within project directory)
        """
        # Read settings at execution time (not cached at registration)
        severity_threshold = api.get_setting("severity_threshold", "medium")
        auto_notify = api.get_setting("auto_notify_critical", True)
        threshold_level = SEVERITY_PRIORITY.get(severity_threshold.lower(), 2)
        
        # Validate requirements_file path - only allow paths within allowed directories
        allowed_roots = [Path.cwd().resolve()]
        req_path = Path(requirements_file) if requirements_file else None
        
        result = _run_pip_audit(req_path, allowed_roots=allowed_roots)
        
        # Filter by severity threshold (using locally-read setting)
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
        
        # Read history with proper JSON error handling
        history_raw = api.read_data("audit_history.json") or "[]"
        try:
            history = json.loads(history_raw)
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Failed to parse audit history, starting fresh: %s", exc)
            history = []
        
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
                    # Use --upgrade to handle dependency conflicts gracefully
                    upgrade_result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--upgrade", f"{pkg}=={target_version}"],
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
            
        # Check for previous critical findings with proper JSON error handling
        try:
            history_raw = api.read_data("audit_history.json") or "[]"
            history = json.loads(history_raw)
            if not isinstance(history, list):
                history = []
            if history:
                last = history[-1]
                summary = last.get("result", {}).get("summary", {})
                critical = summary.get("critical", 0)
                if critical > 0:
                    api.log(f"Previous audit found {critical} critical vulnerabilities - run security_audit_vulnerabilities")
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Failed to parse audit history on boot: %s", exc)
        except Exception as exc:
            log.warning("Error checking audit history on boot: %s", exc)

    api.register_hook("on_boot", on_boot)
