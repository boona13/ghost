"""Secrets and Credential Scanner - Scan code for accidentally committed secrets."""
import re
import os
import fnmatch
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Secret patterns to detect
SECRET_REGEX = {
    'aws_access_key': re.compile(r'AKIA[0-9A-Z]{16}'),
    'github_token': re.compile(r'ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'),
    'slack_token': re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}(-[a-zA-Z0-9]{24})?'),
    'stripe_key': re.compile(r'sk_live_[a-zA-Z0-9]{24,}|pk_live_[a-zA-Z0-9]{24,}'),
    'private_key': re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    'jwt_token': re.compile(r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'),
    'db_connection': re.compile(r'(mongodb|postgres|mysql)://[^\s\'"]+'),
    'api_key_generic': re.compile(r'(api[_-]?key|apikey|secret[_-]?key|password|token)\s*[=:]\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
}

# Literal filenames that should be in .gitignore
SECRET_FILES = {
    '.env', '.env.local', '.env.production', '.env.development',
    'credentials.json', 'service_account.json', 'secrets.json',
    'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
    '.htpasswd', '.netrc', '.npmrc', '.pypirc',
}

# Wildcard patterns that should be in .gitignore (matched with fnmatch)
SECRET_PATTERNS = [
    '*.pem', '*.key', '*.p12', '*.pfx', '*.crt', '*.cer',
    '*.keystore', '*.jks', '*.env.*',
]

# Binary file extensions to skip
BINARY_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll', '.so', '.dylib', '.bin', '.dat'}


def _is_binary(filepath):
    """Check if file is binary by extension."""
    return Path(filepath).suffix.lower() in BINARY_EXTENSIONS


def _redact(value, visible=4):
    """Redact a secret value, showing only first N chars."""
    if len(value) <= visible:
        return '*' * len(value)
    return value[:visible] + '*' * (len(value) - visible)


def _read_gitignore(gitignore_path):
    """Read .gitignore and return set of patterns."""
    patterns = set()
    try:
        with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.add(line)
    except FileNotFoundError:
        log.warning(".gitignore not found at %s", gitignore_path)
    except (IOError, OSError) as exc:
        log.warning("Error reading .gitignore at %s: %s", gitignore_path, exc)
    return patterns


def _is_in_gitignore(filename, gitignore_patterns):
    """Check if filename matches any gitignore pattern (literal or wildcard)."""
    for pattern in gitignore_patterns:
        # Try exact match first
        if pattern == filename:
            return True
        # Try fnmatch for wildcards
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def scan_secrets(path='.', **kwargs):
    """Scan a file or directory for accidentally committed secrets.
    
    Args:
        path: File or directory path to scan
        
    Returns:
        dict with findings list (file, line, type, redacted_preview)
    """
    findings = []
    target = Path(path).expanduser().resolve()
    
    if not target.exists():
        log.warning("Path does not exist: %s", path)
        return {'findings': [], 'error': f'Path does not exist: {path}'}
    
    files_to_scan = []
    if target.is_file():
        files_to_scan = [target]
    else:
        try:
            for root, dirs, files in os.walk(target):
                # Skip hidden dirs and common non-source dirs
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'venv', '.git'}]
                for f in files:
                    filepath = Path(root) / f
                    if not _is_binary(filepath):
                        files_to_scan.append(filepath)
        except (OSError, PermissionError) as exc:
            log.error("Error walking directory %s: %s", target, exc)
            return {'findings': [], 'error': f'Error scanning directory: {exc}'}
    
    for filepath in files_to_scan:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                
                for secret_type, pattern in SECRET_REGEX.items():
                    for match in pattern.finditer(content):
                        # Find line number
                        line_num = content[:match.start()].count('\n') + 1
                        matched_value = match.group(0)
                        
                        findings.append({
                            'file': str(filepath.relative_to(target) if target.is_dir() else filepath.name),
                            'line': line_num,
                            'type': secret_type,
                            'preview': _redact(matched_value),
                        })
        except (IOError, OSError) as exc:
            log.warning("Error reading file %s: %s", filepath, exc)
            continue
    
    log.info("scan_secrets completed: %d findings in %s", len(findings), path)
    return {'findings': findings, 'count': len(findings)}


def check_gitignore(path='.', **kwargs):
    """Verify that common secret files are in .gitignore.
    
    Args:
        path: Directory path to check (should contain .gitignore)
        
    Returns:
        dict with missing_entries list and recommendations
    """
    target = Path(path).expanduser().resolve()
    gitignore_path = target / '.gitignore'
    
    gitignore_patterns = _read_gitignore(gitignore_path)
    missing = []
    
    # Check literal filenames
    for secret_file in SECRET_FILES:
        if not _is_in_gitignore(secret_file, gitignore_patterns):
            missing.append(secret_file)
    
    # Check wildcard patterns
    for pattern in SECRET_PATTERNS:
        if not _is_in_gitignore(pattern, gitignore_patterns):
            missing.append(pattern)
    
    log.info("check_gitignore completed: %d missing entries in %s", len(missing), path)
    return {
        'missing_entries': missing,
        'count': len(missing),
        'recommendations': [f"Add '{entry}' to .gitignore" for entry in missing] if missing else ['All common secret patterns are covered'],
        'gitignore_found': gitignore_path.exists(),
    }


def register(api):
    """Register tools with Ghost."""
    api.register_tool({
        'name': 'scan_secrets',
        'description': 'Scan a file or directory for accidentally committed secrets (API keys, tokens, passwords, private keys). Returns findings with file, line, type, and redacted preview.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File or directory path to scan', 'default': '.'},
            },
            'required': [],
        },
        'execute': scan_secrets,
    })
    
    api.register_tool({
        'name': 'check_gitignore',
        'description': 'Verify that common secret files (.env, *.pem, credentials.json, etc.) are listed in .gitignore. Returns missing entries as recommendations.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Directory path containing .gitignore', 'default': '.'},
            },
            'required': [],
        },
        'execute': check_gitignore,
    })
