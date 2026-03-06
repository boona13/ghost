"""LlamaParse document processing tool - parses PDFs, Word docs, Excel, images and 90+ formats into structured markdown/JSON using LlamaIndex's LlamaParse API."""

import json
import os
import warnings


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def _get_client():
        """Lazy import and initialize LlamaParse client."""
        # Suppress urllib3/requests warnings before importing
        warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')
        warnings.filterwarnings('ignore', category=UserWarning, module='requests')
        
        from llama_cloud import LlamaParse
        
        api_key = api.get_setting("api_key") or os.environ.get("LLAMAPARSE_API_KEY")
        if not api_key:
            raise ValueError("LlamaParse API key not configured. Set LLAMAPARSE_API_KEY in tool settings or environment.")
        
        return LlamaParse(api_key=api_key)

    def parse_document(source: str, tier: str = "fast", output_format: str = "markdown", 
                       **kwargs):
        """
        Parse a document (file path or URL) using LlamaParse.
        
        Args:
            source: File path or URL to document
            tier: Parsing tier - 'fast', 'cost_effective', 'agentic', 'agentic_plus'
            output_format: Output format - 'markdown', 'json', 'text'
        """
        try:
            client = _get_client()
            
            # Determine if source is URL or file path
            is_url = source.startswith(('http://', 'https://'))
            
            # Map tier to LlamaParse parameter
            tier_map = {
                "fast": "fast",
                "cost_effective": "balanced", 
                "agentic": "premium",
                "agentic_plus": "ultra"
            }
            parsing_tier = tier_map.get(tier, "fast")
            
            # Parse the document
            if is_url:
                result = client.load_data(source, parsing_tier=parsing_tier)
            else:
                result = client.load_data(source, parsing_tier=parsing_tier)
            
            # Extract text content
            if result and len(result) > 0:
                text = "\n\n".join([doc.text for doc in result if hasattr(doc, 'text')])
                metadata = result[0].metadata if hasattr(result[0], 'metadata') else {}
            else:
                text = ""
                metadata = {}
            
            # Format output
            if output_format == "json":
                output = {
                    "text": text,
                    "metadata": metadata,
                    "pages": len(result) if result else 0
                }
            else:
                output = text
            
            api.log(f"Parsed document: {source[:50]}... ({len(text)} chars)")
            api.memory_save(f"Parsed document {source[:50]}... using LlamaParse ({tier} tier)", 
                          tags=["llama_parse", "document"])
            
            return json.dumps({
                "status": "success",
                "source": source,
                "format": output_format,
                "tier": tier,
                "content": output,
                "character_count": len(text)
            })
            
        except Exception as e:
            api.log(f"Parse failed: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "source": source
            })

    api.register_tool({
        "name": "llama_parse",
        "description": "Parse documents (PDF, Word, Excel, images, etc.) into structured text using LlamaParse API. Supports file paths or URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "File path or URL to the document to parse"
                },
                "tier": {
                    "type": "string",
                    "enum": ["fast", "cost_effective", "agentic", "agentic_plus"],
                    "default": "fast",
                    "description": "Parsing quality tier - fast is quickest, agentic_plus is highest quality"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "json", "text"],
                    "default": "markdown",
                    "description": "Output format for parsed content"
                }
            },
            "required": ["source"]
        },
        "execute": parse_document
    })
