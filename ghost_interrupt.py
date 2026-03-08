"""
GHOST Mid-Generation Interrupt and Prompt Injection Controls

Provides real-time interruption of LLM generation and prompt modification
while generation is in progress — Claude-like escape-to-stop functionality.
"""

import json
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

import requests

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_DELAY = 2.0


class GenerationState(Enum):
    """States for interruptible generation."""
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    PAUSED = "paused"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class InjectPrompt:
    """A prompt injection request."""
    text: str
    timestamp: float = field(default_factory=time.time)
    inject_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class StreamChunk:
    """A chunk of streamed content."""
    content: str
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    is_complete: bool = False


class InterruptibleGeneration:
    """
    Manages a single interruptible generation session.
    
    Thread-safe state management for:
    - Cancellation (immediate stop)
    - Prompt injection (queue new prompts to be included)
    - Streaming response accumulation
    """
    
    def __init__(self, session_id: str, model: str, provider_id: str = "openrouter"):
        self.session_id = session_id
        self.model = model
        self.provider_id = provider_id
        
        # State management
        self._state = GenerationState.IDLE
        self._state_lock = threading.Lock()
        self._cancel_event = threading.Event()
        
        # Prompt injection queue
        self._inject_queue: List[InjectPrompt] = []
        self._inject_lock = threading.Lock()
        
        # Stream accumulation
        self._accumulated_text = ""
        self._accumulated_chunks: List[StreamChunk] = []
        self._accumulate_lock = threading.Lock()
        
        # Metadata
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.error: Optional[str] = None
        self.total_tokens = 0
        
    @property
    def state(self) -> GenerationState:
        with self._state_lock:
            return self._state
    
    @state.setter
    def state(self, value: GenerationState):
        with self._state_lock:
            self._state = value
            if value == GenerationState.STREAMING and self.started_at is None:
                self.started_at = time.time()
            if value in (GenerationState.COMPLETE, GenerationState.ERROR, GenerationState.CANCELLED):
                self.finished_at = time.time()
    
    @property
    def is_active(self) -> bool:
        return self.state in (GenerationState.CONNECTING, GenerationState.STREAMING, GenerationState.PAUSED)
    
    @property
    def accumulated_text(self) -> str:
        with self._accumulate_lock:
            return self._accumulated_text
    
    def cancel(self) -> bool:
        """Request cancellation. Returns True if was active."""
        with self._state_lock:
            was_active = self._state in (GenerationState.CONNECTING, GenerationState.STREAMING, GenerationState.PAUSED)
            if was_active:
                self._state = GenerationState.CANCELLED
        self._cancel_event.set()
        return was_active
    
    def check_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_event.is_set()
    
    def inject_prompt(self, text: str) -> str:
        """Queue a prompt injection. Returns inject_id."""
        prompt = InjectPrompt(text=text)
        with self._inject_lock:
            self._inject_queue.append(prompt)
        log.info("[%s] Queued prompt injection: %s...", self.session_id, text[:50])
        return prompt.inject_id
    
    def get_pending_injections(self, clear: bool = True) -> List[InjectPrompt]:
        """Get queued injections, optionally clearing them."""
        with self._inject_lock:
            injections = list(self._inject_queue)
            if clear:
                self._inject_queue.clear()
            return injections
    
    def append_chunk(self, chunk: StreamChunk):
        """Append a stream chunk."""
        with self._accumulate_lock:
            self._accumulated_chunks.append(chunk)
            self._accumulated_text += chunk.content
    
    def get_elapsed(self) -> float:
        """Get elapsed time since start."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return end - self.started_at


class GenerationRegistry:
    """Registry for all active interruptible generations."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._generations: Dict[str, InterruptibleGeneration] = {}
                    cls._instance._gen_lock = threading.Lock()
        return cls._instance
    
    def create(self, session_id: str, model: str, provider_id: str = "openrouter") -> InterruptibleGeneration:
        """Create and register a new generation."""
        gen = InterruptibleGeneration(session_id, model, provider_id)
        with self._gen_lock:
            self._cleanup_old()
            self._generations[session_id] = gen
        return gen
    
    def get(self, session_id: str) -> Optional[InterruptibleGeneration]:
        """Get a generation by ID."""
        with self._gen_lock:
            return self._generations.get(session_id)
    
    def cancel(self, session_id: str) -> bool:
        """Cancel a generation by ID."""
        gen = self.get(session_id)
        if gen:
            return gen.cancel()
        return False
    
    def inject(self, session_id: str, text: str) -> Optional[str]:
        """Inject a prompt into a generation. Returns inject_id or None."""
        gen = self.get(session_id)
        if gen and gen.is_active:
            return gen.inject_prompt(text)
        return None
    
    def list_active(self) -> List[str]:
        """List IDs of active generations."""
        with self._gen_lock:
            return [sid for sid, gen in self._generations.items() if gen.is_active]
    
    def _cleanup_old(self, max_age: float = 3600):
        """Remove generations older than max_age seconds."""
        now = time.time()
        to_remove = [sid for sid, gen in self._generations.items() if gen.finished_at and (now - gen.finished_at) > max_age]
        for sid in to_remove:
            del self._generations[sid]


def make_interrupt_tools(registry=None, config: Optional[Dict] = None) -> List[Dict]:
    """
    Build interrupt control tools.
    
    Returns tools for:
    - interrupt_generation: Cancel an active generation
    - inject_prompt: Add a prompt to an active generation
    """
    tools = []
    reg = GenerationRegistry()
    
    def interrupt_generation(session_id: str) -> str:
        """Cancel/interrupt an active generation by session ID."""
        if reg.cancel(session_id):
            return f"Generation {session_id} cancelled successfully"
        return f"No active generation found for session {session_id}"
    
    def inject_prompt(session_id: str, text: str) -> str:
        """Inject a prompt into an active generation."""
        inject_id = reg.inject(session_id, text)
        if inject_id:
            return f"Prompt injected with ID {inject_id}"
        return f"No active generation found for session {session_id}"
    
    def get_generation_status(session_id: str) -> Dict:
        """Get the status of a generation session."""
        gen = reg.get(session_id)
        if not gen:
            return {"error": "Session not found"}
        return {
            "session_id": gen.session_id,
            "state": gen.state.value,
            "model": gen.model,
            "elapsed": gen.get_elapsed(),
            "text_length": len(gen.accumulated_text),
            "is_active": gen.is_active,
        }
    
    def list_active_generations() -> List[str]:
        """List all active generation session IDs."""
        return reg.list_active()
    
    tools.append({
        "name": "interrupt_generation",
        "description": "Cancel/interrupt an active LLM generation by session ID. Use when the user wants to stop generation immediately.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The generation session ID to cancel"}
            },
            "required": ["session_id"]
        },
        "execute": interrupt_generation
    })
    
    tools.append({
        "name": "inject_prompt",
        "description": "Inject a prompt into an active generation. The text will be included in the conversation context mid-generation.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The generation session ID"},
                "text": {"type": "string", "description": "The prompt text to inject"}
            },
            "required": ["session_id", "text"]
        },
        "execute": inject_prompt
    })
    
    tools.append({
        "name": "get_generation_status",
        "description": "Get the status of a generation session including state, elapsed time, and text length.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "The generation session ID"}
            },
            "required": ["session_id"]
        },
        "execute": get_generation_status
    })
    
    tools.append({
        "name": "list_active_generations",
        "description": "List all active generation session IDs.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "execute": list_active_generations
    })
    
    return tools
