"""LlamaParse document processing tool — uses the REST API directly (no SDK)
to avoid pydantic/Python 3.14 incompatibilities in the llama-cloud package."""

import json
import os
import time
from pathlib import Path

import requests

LLAMA_API = "https://api.cloud.llamaindex.ai/api/v1/parsing"


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def _api_key():
        key = api.get_setting("api_key") or os.environ.get("LLAMAPARSE_API_KEY")
        if not key:
            raise ValueError(
                "LlamaParse API key not configured. "
                "Set LLAMAPARSE_API_KEY in tool settings or environment."
            )
        return key

    def _headers():
        return {
            "Authorization": f"Bearer {_api_key()}",
            "Accept": "application/json",
        }

    def parse_document(source: str, tier: str = "fast",
                       output_format: str = "markdown", **kwargs):
        """Parse a document (file path or URL) via the LlamaParse REST API."""
        try:
            is_url = source.startswith(("http://", "https://"))

            # ── Upload ────────────────────────────────────────
            upload_url = f"{LLAMA_API}/upload"
            data = {"parsing_mode": tier}

            if is_url:
                data["url"] = source
                resp = requests.post(upload_url, headers=_headers(),
                                     data=data, timeout=30)
            else:
                fpath = Path(source).expanduser()
                if not fpath.exists():
                    return json.dumps({
                        "status": "error",
                        "error": f"File not found: {source}",
                        "source": source,
                    })
                with open(fpath, "rb") as f:
                    resp = requests.post(upload_url, headers=_headers(),
                                         data=data,
                                         files={"file": (fpath.name, f)},
                                         timeout=60)

            resp.raise_for_status()
            job_id = resp.json().get("id")
            if not job_id:
                return json.dumps({
                    "status": "error",
                    "error": "No job ID returned from upload",
                    "source": source,
                })

            # ── Poll until done (max ~90s) ────────────────────
            status_url = f"{LLAMA_API}/job/{job_id}"
            for _ in range(30):
                time.sleep(3)
                sr = requests.get(status_url, headers=_headers(), timeout=15)
                sr.raise_for_status()
                status = sr.json().get("status", "")
                if status == "SUCCESS":
                    break
                if status in ("ERROR", "FAILED"):
                    return json.dumps({
                        "status": "error",
                        "error": f"LlamaParse job failed: {sr.json()}",
                        "source": source,
                    })
            else:
                return json.dumps({
                    "status": "error",
                    "error": "LlamaParse job timed out after 90s",
                    "source": source,
                })

            # ── Fetch result ──────────────────────────────────
            fmt = "markdown" if output_format == "markdown" else output_format
            result_url = f"{LLAMA_API}/job/{job_id}/result/{fmt}"
            rr = requests.get(result_url, headers=_headers(), timeout=30)
            rr.raise_for_status()
            result_data = rr.json()

            text = ""
            pages = result_data.get("pages", [])
            if pages:
                text = "\n\n".join(p.get("text", "") for p in pages)
            elif isinstance(result_data, dict) and "text" in result_data:
                text = result_data["text"]
            elif isinstance(result_data, str):
                text = result_data

            api.log(f"Parsed document: {source[:50]}... ({len(text)} chars)")
            api.memory_save(
                f"Parsed document {source[:50]}... using LlamaParse ({tier} tier)",
                tags=["llama_parse", "document"],
            )

            return json.dumps({
                "status": "success",
                "source": source,
                "format": output_format,
                "tier": tier,
                "content": text,
                "character_count": len(text),
            })

        except Exception as e:
            api.log(f"Parse failed: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "source": source,
            })

    api.register_tool({
        "name": "llama_parse",
        "description": (
            "Parse documents (PDF, Word, Excel, images, etc.) into structured "
            "text using the LlamaParse API. Supports file paths or URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "File path or URL to the document to parse",
                },
                "tier": {
                    "type": "string",
                    "enum": ["fast", "cost_effective", "agentic", "agentic_plus"],
                    "default": "fast",
                    "description": "Parsing quality tier",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "json", "text"],
                    "default": "markdown",
                    "description": "Output format for parsed content",
                },
            },
            "required": ["source"],
        },
        "execute": parse_document,
    })
