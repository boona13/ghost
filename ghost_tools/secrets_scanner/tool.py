import re
import os
from pathlib import Path

def register(api):
    # Compiled regex patterns for common secrets
    PATTERNS = {
        'aws_key': re.compile(r'AKIA[0-9A-Z]{16}'),
        'github_token': re.compile(r'ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'),
        'slack_token': re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}(-[a-zA-Z0-9]{24})?'),
        'stripe_key': re.compile(r'sk_live_[a-zA-Z0-9]{24,99}|pk_live_[a-zA-Z0-9]{24,99}'),
        'jwt_token': re.compile(r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'),
        'private_key': re.compile(r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
        'api_key_generic': re.compile(r'(?i)(api[_-]?key|apikey)[\s]*[=:][\s]*["\']?[a-zA-Z0-9_-]{16,}["\']?'),
        'secret_generic': re.compile(r'(?i)(secret|password|token)[\s]*[=:][\s]*["\']?[a-zA-Z0-9_!@#$%^&*.-]{8,}["\']?'),
        'db_connection': re.compile(r'(?i)(mongodb|postgres|mysql|redis)://[^\s"\']+'),
    }
    
    SECRET_FILES = {'.env', '.env.local', '.env.production', '*.pem', '*.key', 'credentials.json', 
                    'secrets.json', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519', '.htpasswd'}
    
    BINARY_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz', 
                         '.exe', '.dll', '.so', '.dylib', '.bin', '.dat'}
    
    def _is_binary(path):
        return any(str(path).lower().endswith(ext) for ext in BINARY_EXTENSIONS)
    
    def _redact(value, visible=4):
        if len(value) <= visible * 2:
            return value[:visible] + '*' * (len(value) - visible)
        return value[:visible] + '*' * (len(value) - visible * 2) + value[-visible:]
    
    def _scan_file(filepath):
        findings = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    for secret_type, pattern in PATTERNS.items():
                        for match in pattern.finditer(line):
                            findings.append({
                                'file': str(filepath),
                                'line': line_num,
                                'type': secret_type,
                                'preview': _redact(match.group())
                            })
        except (IOError, OSError):
            pass
        return findings
    
    def scan_secrets(path, **kwargs):
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return {'error': f'Path not found: {path}'}
        
        findings = []
        if target.is_file():
            if not _is_binary(target):
                findings = _scan_file(target)
        else:
            for filepath in target.rglob('*'):
                if filepath.is_file() and not _is_binary(filepath):
                    findings.extend(_scan_file(filepath))
        
        return {
            'findings': findings,
            'count': len(findings),
            'scanned': str(target)
        }
    
    def check_gitignore(path, **kwargs):
        target = Path(path).expanduser().resolve()
        gitignore = target / '.gitignore' if target.is_dir() else target.parent / '.gitignore'
        
        existing = set()
        if gitignore.exists():
            try:
                content = gitignore.read_text(encoding='utf-8')
                existing = {line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')}
            except (IOError, OSError):
                pass
        
        missing = [f for f in SECRET_FILES if f not in existing and not any(
            existing_pat.replace('*', '') in f for existing_pat in existing if '*' in existing_pat
        )]
        
        return {
            'gitignore_path': str(gitignore),
            'exists': gitignore.exists(),
            'missing_entries': missing,
            'recommendations': [f'Add "{m}" to .gitignore' for m in missing]
        }
    
    api.register_tool({
        'name': 'scan_secrets',
        'description': 'Scan files or directories for accidentally committed secrets (API keys, tokens, passwords)',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'File or directory path to scan'}
            },
            'required': ['path']
        },
        'execute': scan_secrets
    })
    
    api.register_tool({
        'name': 'check_gitignore',
        'description': 'Check if common secret files are properly excluded in .gitignore',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Project path to check'}
            },
            'required': ['path']
        },
        'execute': check_gitignore
    })
