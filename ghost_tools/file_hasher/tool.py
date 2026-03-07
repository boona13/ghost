"""File hash and diff calculator tool for Ghost.

Provides file integrity checking and comparison capabilities using
pure Python standard library (hashlib and difflib).
"""
import hashlib
import difflib
import json
import os
from datetime import datetime
from pathlib import Path


def register(api):
    """Register file hasher tools with Ghost."""
    
    def file_hash(path: str, algorithm: str = "sha256", **kwargs) -> str:
        """Compute hash of a file.
        
        Args:
            path: Path to the file to hash
            algorithm: Hash algorithm (md5, sha1, sha256, sha512). Default: sha256
        
        Returns:
            JSON string with hash result or error
        """
        supported = ["md5", "sha1", "sha256", "sha512"]
        if algorithm not in supported:
            return json.dumps({
                "error": f"Unsupported algorithm: {algorithm}. Use: {', '.join(supported)}"
            })
        
        try:
            file_path = Path(path)
            if not file_path.exists():
                return json.dumps({"error": f"File not found: {path}"})
            if not file_path.is_file():
                return json.dumps({"error": f"Not a file: {path}"})
            
            hasher = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            
            result = {
                "path": str(file_path.resolve()),
                "algorithm": algorithm,
                "hash": hasher.hexdigest(),
                "size_bytes": file_path.stat().st_size
            }
            api.log(f"Computed {algorithm} hash for {path}")
            return json.dumps(result)
        except OSError as e:
            return json.dumps({"error": f"I/O error reading {path}: {e}"})
        except Exception as e:
            return json.dumps({"error": f"Unexpected error: {e}"})
