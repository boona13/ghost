"""Text-to-PDF converter with Unicode-safe fallbacks and cross-platform font discovery."""

import platform
import time
from pathlib import Path

_UNICODE_REPLACEMENTS = {
    "\u2014": "--", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
}


def _normalize_pdf_text(text: str) -> str:
    out = text
    for src, dst in _UNICODE_REPLACEMENTS.items():
        out = out.replace(src, dst)
    return out


def _pick_unicode_font() -> str:
    """Find a Unicode-capable TrueType font on the current OS."""
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    elif system == "Windows":
        windir = Path("C:/Windows/Fonts")
        candidates = [
            str(windir / "arial.ttf"),
            str(windir / "segoeui.ttf"),
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for p in candidates:
        if Path(p).is_file():
            return p
    return ""


def register(api):
    def text_to_pdf(text: str, output_path: str = "", style: str = "formal", **kwargs):
        if not isinstance(text, str) or not text.strip():
            return "Error: text must be a non-empty string"
        if not isinstance(style, str):
            return "Error: style must be a string"

        try:
            from fpdf import FPDF
            from fpdf.errors import FPDFUnicodeEncodingException
        except ImportError:
            return "Error: fpdf2 is not installed — run: pip install fpdf2"

        styles = {
            "formal": ("Times", 12),
            "default": ("Helvetica", 12),
            "compact": ("Courier", 10),
        }
        family, size = styles.get(style.lower().strip(), styles["default"])

        if output_path:
            target = Path(output_path).expanduser()
        else:
            target = Path.home() / ".ghost" / "artifacts" / f"text_to_pdf_{int(time.time())}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        payload = text.strip()

        try:
            font_path = _pick_unicode_font()
            using_unicode = False
            if font_path and style.lower().strip() in {"formal", "default"}:
                pdf.add_font("Unicode", "", font_path)
                pdf.set_font("Unicode", size=size)
                using_unicode = True
            else:
                pdf.set_font(family, size=size)
                payload = _normalize_pdf_text(payload)

            pdf.multi_cell(0, 8 if size >= 12 else 6, payload)
            pdf.output(str(target))
            mode = "unicode-font" if using_unicode else "core-font-normalized"
            return f"OK: PDF written to {target} ({mode})"
        except FPDFUnicodeEncodingException:
            try:
                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                pdf.set_font("Helvetica", size=12)
                pdf.multi_cell(0, 8, _normalize_pdf_text(payload))
                pdf.output(str(target))
                return f"OK: PDF written to {target} (fallback-normalized)"
            except (OSError, ValueError) as e:
                return f"Error: PDF fallback write failed: {e}"
        except (OSError, ValueError) as e:
            return f"Error: PDF generation failed: {e}"

    api.register_tool({
        "name": "text_to_pdf",
        "description": "Convert plain text to PDF with style presets and Unicode-safe fallbacks.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Source text to render in the PDF"},
                "output_path": {"type": "string", "description": "Output PDF path (optional)", "default": ""},
                "style": {"type": "string", "description": "Style preset: formal/default/compact", "default": "formal"},
            },
            "required": ["text"],
        },
        "execute": text_to_pdf,
    })
