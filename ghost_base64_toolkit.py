"""
ghost_base64_toolkit.py - Base64 encoding and decoding tools

Provides simple base64 encode/decode functionality for text and files.
Pure Python, no external dependencies.
"""

import base64
from pathlib import Path
from typing import Optional


def build_base64_toolkit_tools():
    """Build base64 toolkit tools for the ghost tool registry."""
    return [make_base64_encode(), make_base64_decode()]


def make_base64_encode():
    """Create the base64_encode tool."""

    def execute(text: Optional[str] = None, file_path: Optional[str] = None, **kwargs):
        """
        Encode text or a file to base64.
        
        Args:
            text: Plain text to encode
            file_path: Path to file to encode (mutually exclusive with text)
            
        Returns:
            Base64 encoded string or error dict
        """
        if text is None and file_path is None:
            return {"error": "Either 'text' or 'file_path' must be provided"}
        
        if text is not None and file_path is not None:
            return {"error": "Provide only 'text' OR 'file_path', not both"}
        
        try:
            if text is not None:
                encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
                return {"result": encoded, "mode": "text"}
            else:
                path = Path(file_path).expanduser()
                if not path.exists():
                    return {"error": f"File not found: {file_path}"}
                data = path.read_bytes()
                encoded = base64.b64encode(data).decode('utf-8')
                return {"result": encoded, "mode": "file", "file_name": path.name, "size": len(data)}
        except Exception as e:
            return {"error": f"Encoding failed: {str(e)}"}

    return {
        "name": "base64_encode",
        "description": "Encode text or a file to base64.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Plain text to encode"},
                "file_path": {"type": "string", "description": "Path to file to encode"}
            }
        },
        "execute": execute
    }


def make_base64_decode():
    """Create the base64_decode tool."""

    def execute(data: str, output_file: Optional[str] = None, **kwargs):
        """
        Decode a base64 string.
        
        Args:
            data: Base64 encoded string to decode
            output_file: Optional path to write decoded binary data
            
        Returns:
            Decoded string or file write confirmation
        """
        if not data:
            return {"error": "Base64 'data' must be provided"}
        
        try:
            decoded = base64.b64decode(data, validate=True)
            
            # Try to decode as UTF-8 text
            try:
                text_result = decoded.decode('utf-8')
                return {"result": text_result, "mode": "text"}
            except UnicodeDecodeError:
                # Binary data - return as hex or write to file
                if output_file:
                    path = Path(output_file).expanduser()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(decoded)
                    return {"result": f"Binary data written to {output_file}", "mode": "file", "size": len(decoded)}
                else:
                    # Return as hex representation for safety
                    hex_repr = decoded.hex()
                    return {"result": hex_repr[:1000] + "..." if len(hex_repr) > 1000 else hex_repr, "mode": "binary_hex", "size": len(decoded)}
        except Exception as e:
            return {"error": f"Decoding failed: {str(e)}"}

    return {
        "name": "base64_decode",
        "description": "Decode a base64 string back to text or binary.",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Base64 encoded string"},
                "output_file": {"type": "string", "description": "Optional path to write decoded binary data"}
            },
            "required": ["data"]
        },
        "execute": execute
    }