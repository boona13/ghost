"""HTTP API Tester — test REST APIs with SSRF protection."""
import json
import time
from typing import Any, Dict

import requests


def register(api):
    """Register API testing tools."""
    
    # Lazy import to avoid startup overhead
    from ghost_web_fetch import validate_url, SsrfBlockedError
    
    def api_request(method: str = "GET", url: str = "", headers: dict = None, 
                    body: str = None, timeout: int = 30, **kwargs) -> str:
        """Make an HTTP request and return structured response data."""
        if not url:
            return json.dumps({"error": "URL is required"})
        
        try:
            validated_url = validate_url(url, allow_local=True)
        except SsrfBlockedError as e:
            return json.dumps({"error": f"SSRF blocked: {e}"})
        
        headers = headers or {}
        request_kwargs = {
            "method": method.upper(),
            "url": validated_url,
            "headers": headers,
            "timeout": timeout,
            "allow_redirects": True
        }
        
        if body and method.upper() in ("POST", "PUT", "PATCH"):
            request_kwargs["data"] = body if isinstance(body, str) else json.dumps(body)
            if isinstance(body, dict):
                request_kwargs["json"] = body
                del request_kwargs["data"]
        
        start_time = time.time()
        try:
            resp = requests.request(**request_kwargs)
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            # Auto-parse JSON if content-type indicates JSON
            content_type = resp.headers.get("Content-Type", "")
            response_body = resp.text
            try:
                if "json" in content_type.lower():
                    response_body = resp.json()
            except (json.JSONDecodeError, ValueError):
                pass  # Keep as text if JSON parsing fails
            
            result = {
                "status_code": resp.status_code,
                "elapsed_ms": elapsed_ms,
                "content_type": content_type,
                "response_headers": dict(resp.headers),
                "response_body": response_body,
                "url": resp.url
            }
            api.log(f"API {method} {url} -> {resp.status_code} ({elapsed_ms}ms)")
            return json.dumps(result, indent=2, default=str)
            
        except requests.exceptions.Timeout:
            return json.dumps({"error": f"Request timed out after {timeout}s"})
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Request failed: {str(e)}"})
    
    def api_health_check(url: str = "", **kwargs) -> str:
        """Quick GET check to verify endpoint is reachable."""
        if not url:
            return json.dumps({"healthy": False, "error": "URL is required"})
        
        try:
            validated_url = validate_url(url, allow_local=True)
        except SsrfBlockedError as e:
            return json.dumps({"healthy": False, "error": f"SSRF blocked: {e}"})
        
        start_time = time.time()
        try:
            resp = requests.get(validated_url, timeout=10, allow_redirects=True)
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            healthy = 200 <= resp.status_code < 300
            result = {
                "healthy": healthy,
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "url": resp.url
            }
            api.log(f"Health check {url} -> {resp.status_code} ({elapsed_ms}ms)")
            return json.dumps(result)
            
        except requests.exceptions.Timeout:
            return json.dumps({"healthy": False, "error": "Timeout after 10s"})
        except requests.exceptions.RequestException as e:
            return json.dumps({"healthy": False, "error": str(e)})
    
    def _get_structure(obj: Any) -> Any:
        """Extract structure (keys/types) for comparison."""
        if isinstance(obj, dict):
            return {k: _get_structure(v) for k, v in obj.items()}
        elif isinstance(obj, list) and obj:
            return [_get_structure(obj[0])]
        elif isinstance(obj, str):
            return "string"
        elif isinstance(obj, bool):
            return "boolean"
        elif isinstance(obj, int):
            return "integer"
        elif isinstance(obj, float):
            return "number"
        elif obj is None:
            return "null"
        return "unknown"
    
    def api_compare(url_a: str = "", url_b: str = "", **kwargs) -> str:
        """Compare two API endpoints' response structures."""
        if not url_a or not url_b:
            return json.dumps({"error": "Both url_a and url_b are required"})
        
        try:
            validated_a = validate_url(url_a, allow_local=True)
            validated_b = validate_url(url_b, allow_local=True)
        except SsrfBlockedError as e:
            return json.dumps({"error": f"SSRF blocked: {e}"})
        
        results = {"url_a": url_a, "url_b": url_b, "comparison": {}}
        
        for label, url in [("a", validated_a), ("b", validated_b)]:
            try:
                resp = requests.get(url, timeout=15)
                data = resp.json() if "json" in resp.headers.get("Content-Type", "") else resp.text
                results[f"response_{label}"] = {
                    "status_code": resp.status_code,
                    "structure": _get_structure(data)
                }
            except Exception as e:
                results[f"response_{label}"] = {"error": str(e)}
        
        # Compare structures
        struct_a = results.get("response_a", {}).get("structure")
        struct_b = results.get("response_b", {}).get("structure")
        
        if struct_a and struct_b:
            results["comparison"] = {
                "structures_match": struct_a == struct_b,
                "structure_a": struct_a,
                "structure_b": struct_b
            }
        
        api.log(f"Compared APIs: {url_a} vs {url_b}")
        return json.dumps(results, indent=2, default=str)
    
    api.register_tool({
        "name": "api_request",
        "description": "Make an HTTP request and return status, headers, body, and timing. Auto-parses JSON responses.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method (GET, POST, PUT, DELETE, etc)", "default": "GET"},
                "url": {"type": "string", "description": "Target URL"},
                "headers": {"type": "object", "description": "Request headers as key-value pairs"},
                "body": {"type": "string", "description": "Request body (string or JSON)"},
                "timeout": {"type": "integer", "description": "Request timeout in seconds", "default": 30}
            },
            "required": ["url"]
        },
        "execute": api_request
    })
    
    api.register_tool({
        "name": "api_health_check",
        "description": "Quick health check: GET an endpoint and return status, latency, and health boolean.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Endpoint URL to check"}
            },
            "required": ["url"]
        },
        "execute": api_health_check
    })
    
    api.register_tool({
        "name": "api_compare",
        "description": "Compare two API endpoints by fetching both and comparing response structures (keys, types).",
        "parameters": {
            "type": "object",
            "properties": {
                "url_a": {"type": "string", "description": "First endpoint URL"},
                "url_b": {"type": "string", "description": "Second endpoint URL"}
            },
            "required": ["url_a", "url_b"]
        },
        "execute": api_compare
    })