"""Text to PDF converter - converts plain text or markdown to styled PDF documents."""

import os
import json


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def text_to_pdf(text, filename="document", style="default", **kwargs):
        """Convert text or markdown to a styled PDF document.
        
        Args:
            text: The text or markdown content to convert (required)
            filename: Output PDF filename without extension (default: 'document')
            style: Style preset - 'default', 'minimal', 'formal', 'code' (default: 'default')
        
        Returns:
            JSON string with {success: bool, filepath: str, error: str}
        """
        try:
            from fpdf import FPDF
            import markdown
        except ImportError:
            return json.dumps({
                "success": False,
                "filepath": None,
                "error": "Dependencies not installed. Install with: pip install fpdf2 markdown"
            })
        
        # Style configurations
        styles = {
            "default": {"title_size": 24, "heading_size": 18, "body_size": 12, "font": "Helvetica"},
            "minimal": {"title_size": 20, "heading_size": 16, "body_size": 11, "font": "Helvetica"},
            "formal": {"title_size": 26, "heading_size": 20, "body_size": 12, "font": "Times"},
            "code": {"title_size": 20, "heading_size": 16, "body_size": 10, "font": "Courier"}
        }
        
        s = styles.get(style, styles["default"])
        
        class PDF(FPDF):
            def header(self):
                self.set_font(s["font"], "", 8)
                self.set_text_color(128)
                self.cell(0, 5, "", 0, 1)
                self.ln(5)
        
        pdf = PDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Convert markdown to HTML, then parse for PDF
        html = markdown.markdown(text, extensions=["extra", "codehilite"])
        
        # Simple HTML-like parsing for basic elements
        lines = text.split("\n")
        in_code_block = False
        code_content = []
        
        for line in lines:
            # Code blocks
            if line.strip().startswith("```"):
                if not in_code_block:
                    in_code_block = True
                    code_content = []
                    continue
                else:
                    # End of code block - output it
                    in_code_block = False
                    pdf.set_font(s["font"], "B", s["heading_size"])
                    pdf.multi_cell(0, 8, "\n".join(code_content))
                    pdf.ln(4)
                    continue
            
            if in_code_block:
                code_content.append(line)
                continue
            
            # Headers
            if line.startswith("### "):
                pdf.set_font(s["font"], "B", s["heading_size"] - 2)
                pdf.multi_cell(0, 7, line[4:])
                pdf.ln(3)
            elif line.startswith("## "):
                pdf.set_font(s["font"], "B", s["heading_size"])
                pdf.multi_cell(0, 8, line[3:])
                pdf.ln(4)
            elif line.startswith("# "):
                pdf.set_font(s["font"], "B", s["title_size"])
                pdf.multi_cell(0, 10, line[2:])
                pdf.ln(5)
            # Bullet points
            elif line.strip().startswith("- ") or line.strip().startswith("* "):
                pdf.set_font(s["font"], "", s["body_size"])
                pdf.cell(10)
                pdf.multi_cell(0, 6, "• " + line.strip()[2:])
            # Numbered lists (basic)
            elif line.strip()[0:2].isdot() if line.strip() else False:
                pass  # Skip for now
            # Bold/italic
            elif "**" in line:
                pdf.set_font(s["font"], "", s["body_size"])
                line = line.replace("**", "")
                pdf.multi_cell(0, 6, line)
                pdf.ln(2)
            # Empty line
            elif line.strip() == "":
                pdf.ln(3)
            # Regular text
            else:
                pdf.set_font(s["font"], "", s["body_size"])
                pdf.multi_cell(0, 6, line)
                pdf.ln(2)
        
        # Ensure safe filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "-_").strip()
        if not safe_name:
            safe_name = "document"
        
        # Output directory
        output_dir = os.path.expanduser("~/.ghost/artifacts")
        os.makedirs(output_dir, exist_ok=True)
        
        filepath = os.path.join(output_dir, f"{safe_name}.pdf")
        pdf.output(filepath)
        
        api.log(f"Created PDF: {filepath}")
        return json.dumps({
            "success": True,
            "filepath": filepath,
            "error": None
        })

    api.register_tool({
        "name": "text_to_pdf",
        "description": "Convert plain text or markdown to a styled PDF document. Supports markdown formatting (headers, lists, bold, italic, code blocks) with style presets (default, minimal, formal, code). Saves to ~/.ghost/artifacts/",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text or markdown content to convert to PDF"
                },
                "filename": {
                    "type": "string",
                    "description": "Output PDF filename without extension (default: 'document')"
                },
                "style": {
                    "type": "string",
                    "description": "Style preset: 'default', 'minimal', 'formal', or 'code'",
                    "enum": ["default", "minimal", "formal", "code"]
                }
            },
            "required": ["text"]
        },
        "execute": text_to_pdf
    })
