"""
Ghost Browser-Use Integration — AI-Native Browser Automation

Uses browser-use (browser-use.com) for LLM-powered browser automation with:
- Intelligent element detection and interaction
- Multi-step task planning
- Self-healing capabilities when page elements change
- Vision-based automation support

Complements the existing Playwright-based ghost_browser.py with AI-native control.

Requirements:
    pip install browser-use

Note: browser-use requires Playwright and an LLM API key to function.
"""

import logging
import json
import asyncio
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

try:
    from browser_use import Agent, Browser, BrowserConfig
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = None
    Browser = None
    BrowserConfig = None

log = logging.getLogger(__name__)

# Thread-safe session storage
_sessions_lock = threading.Lock()
_sessions: Dict[str, Dict[str, Any]] = {}
_session_counter = 0


@dataclass
class BrowserUseSession:
    """Represents an active browser-use session."""
    id: str
    url: str
    task: Optional[str] = None
    status: str = "idle"  # idle, running, paused, error, completed
    history: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    browser: Any = None
    agent: Any = None
    error_message: Optional[str] = None


def _get_next_session_id() -> str:
    """Generate unique session ID."""
    global _session_counter
    with _sessions_lock:
        _session_counter += 1
        return f"bu_{_session_counter:04d}"


def get_session(session_id: str) -> Optional[BrowserUseSession]:
    """Retrieve a session by ID."""
    with _sessions_lock:
        data = _sessions.get(session_id)
        if data:
            return BrowserUseSession(**data)
        return None


def save_session(session: BrowserUseSession) -> None:
    """Save session to storage."""
    with _sessions_lock:
        _sessions[session.id] = {
            "id": session.id,
            "url": session.url,
            "task": session.task,
            "status": session.status,
            "history": session.history,
            "created_at": session.created_at,
            "browser": session.browser,
            "agent": session.agent,
            "error_message": session.error_message,
        }


def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions (without browser/agent objects for serialization)."""
    with _sessions_lock:
        result = []
        for sid, data in _sessions.items():
            result.append({
                "id": data["id"],
                "url": data["url"],
                "task": data.get("task"),
                "status": data.get("status", "unknown"),
                "created_at": data.get("created_at"),
                "history_count": len(data.get("history", [])),
                "error_message": data.get("error_message"),
            })
        return result


def delete_session(session_id: str) -> bool:
    """Delete a session and close its browser."""
    with _sessions_lock:
        data = _sessions.pop(session_id, None)
        if not data:
            return False
        browser = data.get("browser")
        if browser:
            try:
                asyncio.get_event_loop().run_until_complete(browser.close())
            except Exception as exc:
                log.warning("Error closing browser for session %s: %s", session_id, exc)
        return True


async def _run_browser_task(
    session_id: str,
    task: str,
    start_url: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    headless: bool = True,
) -> Dict[str, Any]:
    """Run a browser-use task asynchronously."""
    if not BROWSER_USE_AVAILABLE:
        return {"success": False, "error": "browser-use package not installed"}
    
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    session.status = "running"
    session.task = task
    save_session(session)
    
    try:
        browser_config = BrowserConfig(headless=headless)
        browser = Browser(config=browser_config)
        session.browser = browser
        save_session(session)
        
        # Create LLM - try different providers
        llm = None
        if api_key:
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model=model or "gpt-4o", api_key=api_key)
            except ImportError:
                log.warning("langchain-openai not installed")
        
        if not llm:
            try:
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model=model or "gpt-4o")
            except Exception as exc:
                return {"success": False, "error": f"LLM init failed: {exc}"}
        
        agent = Agent(task=task, llm=llm, browser=browser)
        session.agent = agent
        save_session(session)
        
        result = await agent.run()
        
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "start_url": start_url,
            "result": result.model_dump() if hasattr(result, "model_dump") else str(result),
            "success": True,
        }
        session.history.append(history_entry)
        session.status = "completed"
        save_session(session)
        
        return {"success": True, "result": history_entry["result"], "session_id": session_id}
        
    except Exception as exc:
        log.exception("Browser-use task failed for session %s", session_id)
        session.status = "error"
        session.error_message = str(exc)
        session.history.append({
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "start_url": start_url,
            "error": str(exc),
            "success": False,
        })
        save_session(session)
        return {"success": False, "error": str(exc), "session_id": session_id}



def browser_use_create_session(url: str = "https://google.com", **kwargs) -> str:
    """Create a new browser-use automation session."""
    session_id = _get_next_session_id()
    session = BrowserUseSession(id=session_id, url=url, status="idle")
    save_session(session)
    log.info("Created browser-use session %s starting at %s", session_id, url)
    return session_id


def browser_use_run_task(
    session_id: str,
    task: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    headless: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """Run an AI-powered browser task using browser-use."""
    if not BROWSER_USE_AVAILABLE:
        return {"success": False, "error": "browser-use not installed. Run: pip install browser-use"}
    
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    start_url = kwargs.get("url") or session.url
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_browser_task(
            session_id=session_id,
            task=task,
            start_url=start_url,
            api_key=api_key,
            model=model,
            headless=headless,
        ))
        return result
    except Exception as exc:
        log.exception("Failed to run browser-use task")
        return {"success": False, "error": str(exc)}


def browser_use_get_status(session_id: str, **kwargs) -> Dict[str, Any]:
    """Get the status and history of a browser-use session."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    return {
        "success": True,
        "session": {
            "id": session.id,
            "url": session.url,
            "task": session.task,
            "status": session.status,
            "created_at": session.created_at,
            "history": session.history,
            "error_message": session.error_message,
        }
    }


def browser_use_list_sessions(**kwargs) -> Dict[str, Any]:
    """List all active browser-use sessions."""
    sessions = list_sessions()
    return {
        "success": True,
        "sessions": sessions,
        "count": len(sessions),
        "browser_use_available": BROWSER_USE_AVAILABLE,
    }


def browser_use_close_session(session_id: str, **kwargs) -> Dict[str, Any]:
    """Close a browser-use session and release resources."""
    if delete_session(session_id):
        return {"success": True, "message": f"Session {session_id} closed"}
    return {"success": False, "error": f"Session {session_id} not found"}


def browser_use_navigate(session_id: str, url: str, **kwargs) -> Dict[str, Any]:
    """Navigate to a URL in an existing browser-use session."""
    if not BROWSER_USE_AVAILABLE:
        return {"success": False, "error": "browser-use not installed"}
    
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    try:
        if session.browser:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            page = loop.run_until_complete(session.browser.get_current_page())
            loop.run_until_complete(page.goto(url))
            session.url = url
            save_session(session)
            return {"success": True, "message": f"Navigated to {url}"}
        else:
            session.url = url
            save_session(session)
            return {"success": True, "message": f"URL updated to {url} (browser not started)"}
    except Exception as exc:
        log.exception("Navigation failed")
        return {"success": False, "error": str(exc)}


def browser_use_get_html(session_id: str, **kwargs) -> Dict[str, Any]:
    """Get the current page HTML from a browser-use session."""
    if not BROWSER_USE_AVAILABLE:
        return {"success": False, "error": "browser-use not installed"}
    
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    try:
        if not session.browser:
            return {"success": False, "error": "Browser not started for this session"}
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        page = loop.run_until_complete(session.browser.get_current_page())
        html = loop.run_until_complete(page.content())
        
        max_len = kwargs.get("max_length", 50000)
        if len(html) > max_len:
            html = html[:max_len] + f"\n... [truncated, total: {len(html)} chars]"
        
        return {"success": True, "html": html, "url": session.url}
    except Exception as exc:
        log.exception("Failed to get HTML")
        return {"success": False, "error": str(exc)}


def browser_use_screenshot(session_id: str, output_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Take a screenshot from a browser-use session."""
    if not BROWSER_USE_AVAILABLE:
        return {"success": False, "error": "browser-use not installed"}
    
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    try:
        if not session.browser:
            return {"success": False, "error": "Browser not started for this session"}
        
        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(Path.home() / ".ghost" / "screenshots" / f"browser_use_{session_id}_{ts}.png")
        
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        page = loop.run_until_complete(session.browser.get_current_page())
        loop.run_until_complete(page.screenshot(path=str(path), full_page=kwargs.get("full_page", True)))
        
        return {"success": True, "path": str(path), "url": session.url}
    except Exception as exc:
        log.exception("Screenshot failed")
        return {"success": False, "error": str(exc)}



def build_browser_use_tools(cfg=None):
    """Build and return browser-use tool definitions."""
    return [
        {
            "name": "browser_use_create_session",
            "description": "Create a new AI-powered browser automation session using browser-use. Returns a session ID for use with other browser_use tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Starting URL for the session",
                        "default": "https://google.com"
                    }
                },
                "required": []
            },
            "execute": browser_use_create_session
        },
        {
            "name": "browser_use_run_task",
            "description": "Run an AI-powered browser task using browser-use. The LLM will control the browser to complete the described task. Examples: 'Find the price of iPhone 15 on Amazon', 'Fill out the contact form and submit it', 'Extract all article titles from the news page'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from browser_use_create_session"
                    },
                    "task": {
                        "type": "string",
                        "description": "Natural language description of the task to perform"
                    },
                    "api_key": {
                        "type": "string",
                        "description": "Optional OpenAI API key (falls back to OPENAI_API_KEY env var)",
                        "default": None
                    },
                    "model": {
                        "type": "string",
                        "description": "LLM model to use (default: gpt-4o)",
                        "default": "gpt-4o"
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run browser in headless mode (default: True)",
                        "default": True
                    }
                },
                "required": ["session_id", "task"]
            },
            "execute": browser_use_run_task
        },
        {
            "name": "browser_use_get_status",
            "description": "Get the status and history of a browser-use session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to check"
                    }
                },
                "required": ["session_id"]
            },
            "execute": browser_use_get_status
        },
        {
            "name": "browser_use_list_sessions",
            "description": "List all active browser-use sessions with their status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            },
            "execute": browser_use_list_sessions
        },
        {
            "name": "browser_use_close_session",
            "description": "Close a browser-use session and release resources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to close"
                    }
                },
                "required": ["session_id"]
            },
            "execute": browser_use_close_session
        },
        {
            "name": "browser_use_navigate",
            "description": "Navigate to a URL in an existing browser-use session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    }
                },
                "required": ["session_id", "url"]
            },
            "execute": browser_use_navigate
        },
        {
            "name": "browser_use_get_html",
            "description": "Get the current page HTML content from a browser-use session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum HTML length to return (default: 50000)",
                        "default": 50000
                    }
                },
                "required": ["session_id"]
            },
            "execute": browser_use_get_html
        },
        {
            "name": "browser_use_screenshot",
            "description": "Take a screenshot from a browser-use session and save it to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional path to save screenshot (auto-generated if not provided)",
                        "default": None
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page or just viewport (default: True)",
                        "default": True
                    }
                },
                "required": ["session_id"]
            },
            "execute": browser_use_screenshot
        },
    ]
