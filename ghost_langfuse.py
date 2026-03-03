"""
GHOST Langfuse Integration — AI Agent Observability

Open-source LLM tracing and monitoring via Langfuse (langfuse.com).
Provides automatic tracing of LLM calls, token usage tracking, and
session-based observability for debugging and optimization.

Features:
- @observe decorator for automatic LLM call tracing
- Manual trace/span management for complex workflows
- Token usage and cost estimation
- Session-based trace grouping
- Dashboard integration for trace visualization
"""

import functools
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

log = logging.getLogger(__name__)

# Module-level state
_langfuse_client = None
_langfuse_lock = threading.Lock()
_traces_store = []  # In-memory store for recent traces (bounded)
_max_stored_traces = 100


@dataclass
class TraceSpan:
    """Represents a single span within a trace."""
    id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    level: str = "DEFAULT"  # DEFAULT, DEBUG, INFO, WARNING, ERROR


@dataclass
class Trace:
    """Represents a complete trace of an operation."""
    id: str
    name: str
    session_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    spans: List[TraceSpan] = field(default_factory=list)
    status: str = "running"  # running, completed, error
    error_message: Optional[str] = None


class LangfuseClient:
    """Langfuse client wrapper with local trace storage."""
    
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.enabled = cfg.get("enable_langfuse", False)
        self.host = cfg.get("langfuse_host", "https://cloud.langfuse.com")
        self.public_key = cfg.get("langfuse_public_key", "")
        self.secret_key = cfg.get("langfuse_secret_key", "")
        self.project_id = cfg.get("langfuse_project_id", "")
        self._client = None
        self._local_only = False
        
        if self.enabled:
            self._init_client()
    
    def _init_client(self):
        """Initialize the Langfuse SDK client if credentials are available."""
        try:
            from langfuse import Langfuse
            
            if not self.public_key or not self.secret_key:
                log.warning("Langfuse enabled but missing API keys - using local-only mode")
                self._local_only = True
                return
            
            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )
            log.info("Langfuse client initialized successfully")
        except ImportError:
            log.warning("langfuse package not installed - using local-only mode")
            self._local_only = True
        except Exception as e:
            log.warning("Failed to initialize Langfuse client: %s - using local-only mode", e)
            self._local_only = True
    
    def is_configured(self) -> bool:
        """Check if Langfuse is properly configured."""
        return self.enabled and (self._client is not None or self._local_only)
    
    def create_trace(self, name: str, session_id: Optional[str] = None, 
                     input_data: Optional[Any] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> Trace:
        """Create a new trace."""
        import uuid
        
        trace = Trace(
            id=str(uuid.uuid4()),
            name=name,
            session_id=session_id,
            input_data=input_data,
            metadata=metadata or {},
        )
        
        # Store locally
        with _langfuse_lock:
            _traces_store.insert(0, trace)
            if len(_traces_store) > _max_stored_traces:
                _traces_store.pop()
        
        # Send to Langfuse if configured
        if self._client and not self._local_only:
            try:
                lf_trace = self._client.trace(
                    id=trace.id,
                    name=name,
                    session_id=session_id,
                    input=input_data,
                    metadata=metadata,
                )
                trace.metadata["_lf_trace"] = lf_trace
            except Exception as e:
                log.debug("Failed to create Langfuse trace: %s", e)
        
        return trace
    
    def end_trace(self, trace: Trace, output_data: Optional[Any] = None,
                  status: str = "completed", error_message: Optional[str] = None):
        """End a trace."""
        trace.end_time = time.time()
        trace.output_data = output_data
        trace.status = status
        trace.error_message = error_message
        
        if self._client and not self._local_only:
            try:
                lf_trace = trace.metadata.get("_lf_trace")
                if lf_trace:
                    lf_trace.update(
                        output=output_data,
                        status=status,
                        metadata={"error": error_message} if error_message else None,
                    )
            except Exception as e:
                log.debug("Failed to update Langfuse trace: %s", e)
    
    def create_span(self, trace: Trace, name: str, 
                    input_data: Optional[Any] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> TraceSpan:
        """Create a new span within a trace."""
        import uuid
        
        span = TraceSpan(
            id=str(uuid.uuid4()),
            name=name,
            start_time=time.time(),
            input_data=input_data,
            metadata=metadata or {},
        )
        trace.spans.append(span)
        
        if self._client and not self._local_only:
            try:
                lf_trace = trace.metadata.get("_lf_trace")
                if lf_trace:
                    lf_span = lf_trace.span(
                        id=span.id,
                        name=name,
                        input=input_data,
                        metadata=metadata,
                    )
                    span.metadata["_lf_span"] = lf_span
            except Exception as e:
                log.debug("Failed to create Langfuse span: %s", e)
        
        return span
    
    def end_span(self, span: TraceSpan, output_data: Optional[Any] = None,
                 tokens_input: int = 0, tokens_output: int = 0,
                 cost_usd: float = 0.0, level: str = "DEFAULT"):
        """End a span with usage data."""
        span.end_time = time.time()
        span.output_data = output_data
        span.tokens_input = tokens_input
        span.tokens_output = tokens_output
        span.cost_usd = cost_usd
        span.level = level
        
        if self._client and not self._local_only:
            try:
                lf_span = span.metadata.get("_lf_span")
                if lf_span:
                    lf_span.update(
                        output=output_data,
                        usage={
                            "input": tokens_input,
                            "output": tokens_output,
                            "total": tokens_input + tokens_output,
                        } if tokens_input or tokens_output else None,
                    )
            except Exception as e:
                log.debug("Failed to update Langfuse span: %s", e)


class LangfuseManager:
    """Singleton manager for Langfuse client."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, cfg: Optional[Dict[str, Any]] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        if self._initialized or cfg is None:
            return
        self.client = LangfuseClient(cfg)
        self._initialized = True
    
    def get_client(self) -> Optional[LangfuseClient]:
        """Get the Langfuse client if configured."""
        return self.client if self._initialized else None


def get_langfuse_manager(cfg: Optional[Dict[str, Any]] = None) -> LangfuseManager:
    """Get or create the Langfuse manager singleton."""
    return LangfuseManager(cfg)


def observe(name: Optional[str] = None, session_id: Optional[str] = None,
            capture_input: bool = True, capture_output: bool = True):
    """Decorator to automatically trace function calls.
    
    Usage:
        @observe(name="my_function")
        def my_function(arg1, arg2):
            return result
    
    Or with LLM calls:
        @observe(name="llm_call", capture_input=True, capture_output=True)
        def call_llm(prompt):
            return llm_response
    """
    def decorator(func: Callable) -> Callable:
        trace_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            manager = get_langfuse_manager()
            client = manager.get_client() if manager else None
            
            if not client or not client.enabled:
                return func(*args, **kwargs)
            
            # Create trace
            input_data = None
            if capture_input:
                try:
                    input_data = {
                        "args": [str(a)[:1000] for a in args],
                        "kwargs": {k: str(v)[:1000] for k, v in kwargs.items()},
                    }
                except (TypeError, ValueError) as exc:
                    log.debug("Failed to capture input data: %s", exc)
            
            trace = client.create_trace(
                name=trace_name,
                session_id=session_id,
                input_data=input_data,
            )
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Capture output
                output_data = None
                if capture_output:
                    try:
                        output_data = str(result)[:2000]
                    except (TypeError, ValueError) as exc:
                        log.debug("Failed to capture output data: %s", exc)
                
                client.end_trace(trace, output_data=output_data, status="completed")
                return result
                
            except Exception as e:
                client.end_trace(
                    trace,
                    status="error",
                    error_message=str(e)[:500],
                )
                raise
        
        return wrapper
    return decorator


def get_recent_traces(limit: int = 50, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent traces for dashboard display."""
    with _langfuse_lock:
        traces = list(_traces_store)
    
    if session_id:
        traces = [t for t in traces if t.session_id == session_id]
    
    traces = traces[:limit]
    
    result = []
    for trace in traces:
        duration_ms = None
        if trace.end_time:
            duration_ms = int((trace.end_time - trace.start_time) * 1000)
        
        total_tokens = sum(
            s.tokens_input + s.tokens_output for s in trace.spans
        )
        total_cost = sum(s.cost_usd for s in trace.spans)
        
        result.append({
            "id": trace.id,
            "name": trace.name,
            "session_id": trace.session_id,
            "status": trace.status,
            "start_time": datetime.fromtimestamp(trace.start_time).isoformat(),
            "duration_ms": duration_ms,
            "span_count": len(trace.spans),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "error_message": trace.error_message,
        })
    
    return result


def get_trace_stats(hours: int = 24) -> Dict[str, Any]:
    """Get aggregated trace statistics."""
    cutoff = time.time() - (hours * 3600)
    
    with _langfuse_lock:
        recent_traces = [t for t in _traces_store if t.start_time >= cutoff]
    
    total_calls = len(recent_traces)
    completed = sum(1 for t in recent_traces if t.status == "completed")
    errors = sum(1 for t in recent_traces if t.status == "error")
    
    total_tokens = 0
    total_cost = 0.0
    for trace in recent_traces:
        for span in trace.spans:
            total_tokens += span.tokens_input + span.tokens_output
            total_cost += span.cost_usd
    
    return {
        "period_hours": hours,
        "total_traces": total_calls,
        "completed": completed,
        "errors": errors,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "avg_duration_ms": (
            int(sum(
                (t.end_time - t.start_time) * 1000 
                for t in recent_traces if t.end_time
            ) / max(len([t for t in recent_traces if t.end_time]), 1))
        ),
    }


def test_connection(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Test connection to Langfuse server."""
    host = cfg.get("langfuse_host", "https://cloud.langfuse.com")
    public_key = cfg.get("langfuse_public_key", "")
    secret_key = cfg.get("langfuse_secret_key", "")
    
    if not public_key or not secret_key:
        return {
            "success": False,
            "error": "Missing API credentials",
            "details": "Both langfuse_public_key and langfuse_secret_key are required",
        }
    
    try:
        from langfuse import Langfuse
        
        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        
        # Try to create a test trace
        test_trace = client.trace(name="ghost_connection_test")
        test_trace.update(output={"status": "ok"})
        
        return {
            "success": True,
            "message": "Connection successful",
            "host": host,
            "test_trace_id": test_trace.id,
        }
        
    except ImportError:
        return {
            "success": False,
            "error": "langfuse package not installed",
            "details": "Run: pip install langfuse",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "details": "Check your API credentials and host URL",
        }



def build_langfuse_tools(cfg: Dict[str, Any]):
    """Build Langfuse tools for the tool registry."""
    
    def _langfuse_trace_start(name: str, session_id: Optional[str] = None,
                               input_data: Optional[str] = None, **kwargs):
        """Start a new Langfuse trace for observability.
        
        Args:
            name: Name of the trace/operation
            session_id: Optional session ID for grouping related traces
            input_data: Optional input data to capture
        """
        manager = get_langfuse_manager(cfg)
        client = manager.get_client() if manager else None
        
        if not client or not client.enabled:
            return {"error": "Langfuse not enabled or not configured"}
        
        try:
            parsed_input = json.loads(input_data) if input_data else None
        except json.JSONDecodeError:
            parsed_input = {"raw": input_data}
        
        trace = client.create_trace(
            name=name,
            session_id=session_id,
            input_data=parsed_input,
        )
        
        return {
            "trace_id": trace.id,
            "name": trace.name,
            "session_id": trace.session_id,
            "status": "started",
        }
    
    def _langfuse_trace_end(trace_id: str, output_data: Optional[str] = None,
                            status: str = "completed", error_message: Optional[str] = None, **kwargs):
        """End a Langfuse trace.
        
        Args:
            trace_id: ID of the trace to end
            output_data: Optional output data to capture
            status: Final status (completed, error)
            error_message: Error message if status is error
        """
        manager = get_langfuse_manager(cfg)
        client = manager.get_client() if manager else None
        
        if not client or not client.enabled:
            return {"error": "Langfuse not enabled or not configured"}
        
        # Find the trace
        with _langfuse_lock:
            trace = None
            for t in _traces_store:
                if t.id == trace_id:
                    trace = t
                    break
        
        if not trace:
            return {"error": f"Trace {trace_id} not found"}
        
        try:
            parsed_output = json.loads(output_data) if output_data else None
        except json.JSONDecodeError:
            parsed_output = {"raw": output_data}
        
        client.end_trace(
            trace,
            output_data=parsed_output,
            status=status,
            error_message=error_message,
        )
        
        return {
            "trace_id": trace_id,
            "status": status,
            "duration_ms": int((trace.end_time - trace.start_time) * 1000) if trace.end_time else None,
        }
    
    def _langfuse_get_stats(hours: int = 24, **kwargs):
        """Get Langfuse trace statistics.
        
        Args:
            hours: Time period in hours (default: 24)
        """
        return get_trace_stats(hours)
    
    def _langfuse_test_connection(**kwargs):
        """Test connection to Langfuse server."""
        return test_connection(cfg)
    
    return [
        {
            "name": "langfuse_trace_start",
            "description": "Start a new Langfuse trace for observability. Use this to begin tracking an operation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the trace/operation"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session ID for grouping related traces"
                    },
                    "input_data": {
                        "type": "string",
                        "description": "Optional input data to capture (JSON string)"
                    },
                },
                "required": ["name"]
            },
            "execute": _langfuse_trace_start,
        },
        {
            "name": "langfuse_trace_end",
            "description": "End a Langfuse trace. Use this to complete tracking of an operation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trace_id": {
                        "type": "string",
                        "description": "ID of the trace to end"
                    },
                    "output_data": {
                        "type": "string",
                        "description": "Optional output data to capture (JSON string)"
                    },
                    "status": {
                        "type": "string",
                        "description": "Final status: completed or error",
                        "enum": ["completed", "error"],
                        "default": "completed"
                    },
                    "error_message": {
                        "type": "string",
                        "description": "Error message if status is error"
                    },
                },
                "required": ["trace_id"]
            },
            "execute": _langfuse_trace_end,
        },
        {
            "name": "langfuse_get_stats",
            "description": "Get Langfuse trace statistics including total calls, tokens, and cost estimates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Time period in hours",
                        "default": 24
                    },
                },
            },
            "execute": _langfuse_get_stats,
        },
        {
            "name": "langfuse_test_connection",
            "description": "Test connection to Langfuse server with configured credentials.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "execute": _langfuse_test_connection,
        },
    ]
