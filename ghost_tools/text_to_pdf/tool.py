"""Text-to-PDF tool: convert plain text/markdown into a styled PDF in artifacts."""

import json
import re
from pathlib import Path


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    styles = {
        "default": {"font": "Helvetica", "title": 24, "heading": 18, "body": 12, "margins": 15},
        "minimal": {"font": "Helvetica", "title": 20, "heading": 16, "body": 11, "margins": 12},
        "formal": {"font": "Times", "title": 26, "heading": 20, "body": 12, "margins": 18},
        "code": {"font": "Courier", "title": 20, "heading": 16, "body": 10, "margins": 14},
    }

    def _sanitize_filename(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "", (name or "").strip())
        return safe[:120] or "document"

    def _clean_inline_md(line: str) -> str:
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        return line

    def _render_text(pdf, text: str, cfg: dict):
        in_code = False
        for raw in text.splitlines():
            line = raw.rstrip("\n")
            if line.strip().startswith("```"):
                in_code = not in_code
                pdf.ln(2)
                continue
            if in_code:
                pdf.set_font("Courier", "", cfg["body"])
                pdf.multi_cell(0, 5, line)
                continue
            if not line.strip():
                pdf.ln(3)
                continue
            if line.startswith("# "):
                pdf.set_font(cfg["font"], "B", cfg["title"])
                pdf.multi_cell(0, 10, _clean_inline_md(line[2:]))
                pdf.ln(2)
                continue
            if line.startswith("## ") or line.startswith("### "):
                size = cfg["heading"] if line.startswith("## ") else max(cfg["heading"] - 2, 10)
                pdf.set_font(cfg["font"], "B", size)
                pdf.multi_cell(0, 8, _clean_inline_md(line.lstrip("# ")))
                pdf.ln(1)
                continue
            bullet = re.match(r"^\s*([-*]|\d+\.)\s+(.*)$", line)
            if bullet:
                pdf.set_font(cfg["font"], "", cfg["body"])
                pdf.multi_cell(0, 6, f"- {_clean_inline_md(bullet.group(2))}")
                continue
            pdf.set_font(cfg["font"], "", cfg["body"])
            pdf.multi_cell(0, 6, _clean_inline_md(line))

    def text_to_pdf(text, filename="document", style="default", **kwargs):
        if not isinstance(text, str) or not text.strip():
            return json.dumps({"success": False, "filepath": None, "error": "text must be a non-empty string"})
        if not isinstance(filename, str):
            return json.dumps({"success": False, "filepath": None, "error": "filename must be a string"})
        if not isinstance(style, str) or style not in styles:
            return json.dumps({"success": False, "filepath": None, "error": "style must be one of: default, minimal, formal, code"})

        try:
            from fpdf import FPDF
        except (ImportError, ModuleNotFoundError):
            return json.dumps({"success": False, "filepath": None, "error": "Missing dependency: fpdf2 is not installed for text_to_pdf"})

        try:
            cfg = styles[style]
            pdf = FPDF()
            pdf.set_margins(cfg["margins"], cfg["margins"], cfg["margins"])
            pdf.set_auto_page_break(auto=True, margin=cfg["margins"])
            pdf.add_page()
            _render_text(pdf, text, cfg)

            out_dir = Path.home() / ".ghost" / "artifacts"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{_sanitize_filename(filename)}.pdf"
            pdf.output(str(path))
            api.log(f"Created PDF: {path}")
            return json.dumps({"success": True, "filepath": str(path), "error": None})
        except (OSError, ValueError, TypeError, UnicodeEncodeError) as exc:
            api.log(f"text_to_pdf failed: {exc}")
            return json.dumps({"success": False, "filepath": None, "error": str(exc)})

    api.register_tool({
        "name": "text_to_pdf",
        "description": "Convert plain text or markdown to a styled PDF document saved in artifacts.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text or markdown content to convert"},
                "filename": {"type": "string", "description": "Output filename without extension", "default": "document"},
                "style": {"type": "string", "enum": ["default", "minimal", "formal", "code"], "default": "default"}
            },
            "required": ["text"]
        },
        "execute": text_to_pdf
    })