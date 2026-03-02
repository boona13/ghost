"""
GHOST Reasoning/Think Mode Directive

Adds /think directive support that forces the agent to show its reasoning
before responding. Similar to OpenClaw's /think directive.

Usage:
- User types '/think <question>' to enable reasoning mode for that message
- Or toggles reasoning mode ON via UI for all subsequent messages
- LLM outputs reasoning in <thinking>...</thinking> tags before final response
"""

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

# Reasoning instruction added to system prompt when /think mode is active
REASONING_INSTRUCTION = """

## REASONING MODE (/think)
The user has requested that you show your reasoning process before giving your final answer.
You MUST:
1. First, provide your step-by-step thinking inside <thinking>...</thinking> tags
2. Then, provide your final response after the thinking tags
3. Be thorough in your reasoning - explain your approach, considerations, and why you chose specific tools or strategies
4. The content inside <thinking> tags is for the user's benefit to understand your thought process

Example format:
<thinking>
Let me break this down:
1. The user wants to understand X
2. I should first check Y using tool Z
3. Based on the result, I'll determine the best approach...
</thinking>

[Your final response here]
""".strip()

# Regex to detect /think directive at start of message
_THINK_DIRECTIVE_RE = re.compile(r'^/think\s+', re.IGNORECASE)


def detect_think_directive(message: str) -> tuple[bool, str]:
    """
    Detect if message starts with /think directive.
    
    Returns:
        (has_directive, cleaned_message): Tuple of (bool, str)
        - has_directive: True if /think was detected and removed
        - cleaned_message: Message with /think prefix removed
    """
    if not message or not isinstance(message, str):
        return False, message
    
    match = _THINK_DIRECTIVE_RE.match(message.strip())
    if match:
        cleaned = message[match.end():].strip()
        return True, cleaned
    return False, message


def build_reasoning_prompt(base_system_prompt: str, enable_reasoning: bool = False) -> str:
    """
    Build system prompt with reasoning instruction if enabled.
    
    Args:
        base_system_prompt: The original system prompt
        enable_reasoning: Whether to add reasoning instruction
    
    Returns:
        Modified system prompt with reasoning instruction if enabled
    """
    if not enable_reasoning:
        return base_system_prompt
    
    # Avoid adding duplicate reasoning instructions
    if REASONING_INSTRUCTION.split('\n')[0] in base_system_prompt:
        return base_system_prompt
    
    return base_system_prompt + "\n\n" + REASONING_INSTRUCTION


def parse_reasoning_response(response: str) -> tuple[Optional[str], str]:
    """
    Parse a response that may contain <thinking>...</thinking> tags.
    
    Args:
        response: The full response text
    
    Returns:
        (reasoning, final_response): Tuple of (Optional[str], str)
        - reasoning: Content inside <thinking> tags, or None if not present
        - final_response: Content after </thinking> tag, or full response if no tags
    """
    if not response or not isinstance(response, str):
        return None, response or ""
    
    # Match <thinking>...</thinking> with any content including newlines
    pattern = re.compile(r'<thinking>(.*?)</thinking>', re.DOTALL | re.IGNORECASE)
    match = pattern.search(response)
    
    if match:
        reasoning = match.group(1).strip()
        # Remove the thinking block from response to get final response
        final_response = pattern.sub('', response, count=1).strip()
        return reasoning, final_response
    
    return None, response.strip()


class ReasoningModeState:
    """
    Per-session reasoning mode state.
    Tracks whether reasoning mode is enabled for a chat session.
    """
    
    def __init__(self):
        self._sessions: dict[str, bool] = {}
        self._lock = __import__('threading').Lock()
    
    def is_enabled(self, session_id: str) -> bool:
        """Check if reasoning mode is enabled for a session."""
        with self._lock:
            return self._sessions.get(session_id, False)
    
    def set_enabled(self, session_id: str, enabled: bool) -> None:
        """Enable or disable reasoning mode for a session."""
        with self._lock:
            self._sessions[session_id] = enabled
            log.debug("Reasoning mode %s for session %s", 
                     "enabled" if enabled else "disabled", session_id[:8])
    
    def toggle(self, session_id: str) -> bool:
        """Toggle reasoning mode for a session. Returns new state."""
        with self._lock:
            new_state = not self._sessions.get(session_id, False)
            self._sessions[session_id] = new_state
            log.debug("Reasoning mode toggled to %s for session %s",
                     new_state, session_id[:8])
            return new_state
    
    def clear_session(self, session_id: str) -> None:
        """Remove session state (call when session ends)."""
        with self._lock:
            self._sessions.pop(session_id, None)


# Global state instance
_reasoning_state = ReasoningModeState()


def get_reasoning_state() -> ReasoningModeState:
    """Get the global reasoning state manager."""
    return _reasoning_state
