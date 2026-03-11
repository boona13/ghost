"""Base64 toolkit: encode/decode text and small files safely."""

import base64
import binascii
import json
from pathlib import Path

_MAX_FILE_BYTES = 2 * 1024 * 1024


def register(api):
    """Register base64 toolkit tools."""

    def _encode(mode="text", text="", file_path="", **kwargs):
        if mode not in ("text", "file"):
            return json.dumps({"ok": False, "error": "mode must be 'text' or 'file'"})

        if mode == "text":
            if not isinstance(text, str):
                return json.dumps({"ok": False, "error": "text must be a string"})
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            return json.dumps({"ok": True, "mode": "text", "result": encoded})

        if not isinstance(file_path, str) or not file_path.strip():
            return json.dumps({"ok": False, "error": "file_path is required for file mode"})

        try:
            p = Path(file_path).expanduser().resolve()
            if not p.exists() or not p.is_file():
                return json.dumps({"ok": False, "error": "file_path does not exist or is not a file"})

            size = p.stat().st_size
            if size > _MAX_FILE_BYTES:
                return json.dumps({"ok": False, "error": "file is too large (max 2MB)"})

            data = p.read_bytes()
        except OSError as exc:
            return json.dumps({"ok": False, "error": f"unable to read file: {exc}"})

        encoded = base64.b64encode(data).decode("ascii")
        return json.dumps({"ok": True, "mode": "file", "result": encoded, "bytes": len(data)})

    def _decode(base64_input="", **kwargs):
        if not isinstance(base64_input, str) or not base64_input.strip():
            return json.dumps({"ok": False, "error": "base64_input must be a non-empty string"})

        try:
            raw = base64.b64decode(base64_input, validate=True)
        except (binascii.Error, ValueError) as exc:
            return json.dumps({"ok": False, "error": f"invalid base64 input: {exc}"})

        try:
            text = raw.decode("utf-8")
            return json.dumps({"ok": True, "result": text, "decoded_as": "text"})
        except UnicodeDecodeError:
            encoded_bytes = base64.b64encode(raw).decode("ascii")
            return json.dumps({"ok": True, "result": encoded_bytes, "decoded_as": "binary_base64"})

    api.register_tool({
        "name": "base64_encode",
        "description": "Encode UTF-8 text or a small file (max 2MB) into base64.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "description": "text or file", "default": "text"},
                "text": {"type": "string", "description": "Text to encode when mode=text"},
                "file_path": {"type": "string", "description": "File path to encode when mode=file"}
            }
        },
        "execute": _encode
    })

    api.register_tool({
        "name": "base64_decode",
        "description": "Decode base64 string. Returns UTF-8 text if possible, else binary re-encoded as base64.",
        "parameters": {
            "type": "object",
            "properties": {
                "base64_input": {"type": "string", "description": "Base64 string to decode"}
            },
            "required": ["base64_input"]
        },
        "execute": _decode
    })
