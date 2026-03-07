import re
import json
from datetime import datetime

def register(api):
    def summarize_url(url: str = "", max_length: int = 500, **kwargs):
        if not url:
            return json.dumps({"error": "URL is required"})
        
        try:
            import requests
            from readability import Document
        except ImportError as e:
            return json.dumps({"error": f"Missing dependency: {e}"})
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            
            doc = Document(html)
            title = doc.title() or "Untitled"
            summary_html = doc.summary()
            
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', summary_html)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Truncate at sentence boundary
            word_count = len(text.split())
            if len(text) > max_length:
                truncated = text[:max_length]
                last_period = truncated.rfind('.')
                if last_period > max_length * 0.5:
                    text = truncated[:last_period + 1]
                else:
                    text = truncated.rstrip() + "..."
            
            result = {
                "title": title,
                "summary": text,
                "word_count": word_count,
                "source_url": url,
                "fetched_at": datetime.utcnow().isoformat() + "Z"
            }
            return json.dumps(result, indent=2)
            
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Failed to fetch URL: {e}"})
        except Exception as e:
            return json.dumps({"error": f"Processing failed: {e}"})
    
    api.register_tool(
        name="summarize_url",
        description="Fetch a web page and return a concise summary with title, word count, and metadata",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to summarize"},
                "max_length": {"type": "integer", "description": "Maximum summary length in characters", "default": 500}
            },
            "required": ["url"]
        },
        execute=summarize_url
    )