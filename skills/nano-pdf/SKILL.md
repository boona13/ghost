---
name: nano-pdf
description: "AI-powered PDF editing using natural language. Edit PDF pages by describing changes in plain English—powered by Google's Gemini 3 Pro Image model."
homepage: https://github.com/gavrielc/Nano-PDF
triggers:
  - pdf
  - document
  - page
  - nano-pdf
  - edit pdf
  - modify pdf
  - change pdf
  - update pdf
  - fix pdf
  - pdf edit
  - slide deck
  - presentation pdf
tools:
  - shell_exec
  - file_read
priority: 5
requires:
  bins: ["python3", "pip"]
  python: ["nano-pdf"]
content_types: ["document", "pdf"]
---

# Nano-PDF Skill

Edit PDF files using natural language instructions. Instead of learning complex PDF manipulation tools, just describe what you want to change—like "remove the second slide" or "change the title to Q3 Results."

Powered by Google's Gemini 3 Pro Image model ("Nano Banana") for intelligent document understanding.

## Installation

```bash
pip install nano-pdf
```

Or install from source:
```bash
pip install git+https://github.com/gavrielc/Nano-PDF.git
```

## Usage

### Basic Edit

```bash
nano-pdf edit deck.pdf 1 "Change the title to 'Q3 Results' and fix the typo in the subtitle"
```

### Common Examples

- **Fix typos**: `"Fix the typo 'teh' to 'the' on the first page"`
- **Update titles**: `"Change the presentation title to 'Annual Report 2026'"`
- **Remove content**: `"Remove the third slide entirely"`
- **Add text**: `"Add a disclaimer footer to page 2"`
- **Restyle**: `"Make the title font larger and change it to blue"`
- **Fix formatting**: `"Align the table columns properly"`

### Edit Specific Pages

```bash
# Edit page 1
nano-pdf edit report.pdf 1 "Update the header logo"

# Edit page 5
nano-pdf edit presentation.pdf 5 "Fix the chart labels"
```

### Batch-style Workflow

```bash
# Check current PDF first
file_read report.pdf

# Apply edits
nano-pdf edit report.pdf 1 "Change date to today"
nano-pdf edit report.pdf 2 "Fix the typo in the conclusion"

# Verify the output
ls -la report.pdf
```

## How It Works

1. **Renders** the specified PDF page to an image
2. **Sends** the image + your instruction to Gemini 3 Pro
3. **Generates** an edited version based on your description
4. **Replaces** the original page with the edited version
5. **Outputs** a new PDF with your changes

## Best Practices

- **Be specific**: "Change the title" is vague; "Change 'Old Title' to 'New Title'" works better
- **Page numbers**: Note that page numbers may be 0-based or 1-based depending on version; if the result looks off by one, retry with the other
- **Backup originals**: The tool modifies in-place; keep backups of important documents
- **Sanity-check output**: Always review AI-edited PDFs before sending them out—AI can hallucinate or misinterpret instructions
- **Complex edits**: Break complex changes into simpler, sequential instructions

## Limitations

- Requires internet connection (calls Gemini API)
- One page at a time (currently)
- AI interpretation may vary—clear instructions work best
- Original text layers may be replaced with images

## When to Use Nano-PDF vs Other Tools

| Task | Use Nano-PDF | Use Other Tools (pdftk, pypdf) |
|------|--------------|-------------------------------|
| Text changes, typos | ✅ Natural language | ❌ Complex command syntax |
| Page reordering | ❌ Not designed for this | ✅ `pdftk A=in.pdf cat A1-3 A5 output out.pdf` |
| Merging PDFs | ❌ Not designed for this | ✅ `pdftk *.pdf cat output combined.pdf` |
| Splitting PDFs | ❌ Not designed for this | ✅ `pdftk in.pdf burst` |
| Extracting text | ⚠️ Can work but slow | ✅ `pdftotext` or `pypdf` |
| Design/layout changes | ✅ "Make it look more professional" | ❌ Impossible |

## Troubleshooting

```bash
# Check if installed
nano-pdf --version

# Verify Python environment
python3 -c "import nano_pdf; print('OK')"

# If page numbers seem wrong, try 0-based indexing
nano-pdf edit doc.pdf 0 "Change the title"  # First page as 0
```

## See Also

- For text extraction without editing: `pdftotext` or `pypdf`
- For PDF manipulation (merge/split): `pdftk` or `pypdf`
- For OCR: `olmocr` or `pdf2image` + `pytesseract`
