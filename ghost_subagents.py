"""
Ghost Sub-Agents — Task Delegation and Parallel Execution

Allows Ghost to spawn isolated sub-agents for parallel task execution.
Each sub-agent has:
  - Isolated execution context with its own tool loop
  - Skill-based tool filtering (only tools relevant to assigned skills)
  - Configurable timeouts and resource limits
  - Parent-child result aggregation
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ghost_loop import ToolLoopEngine, ToolRegistry
from ghost_skills import SkillLoader

log = logging.getLogger(__name__)


class SubAgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    success: bool
    output: str = ""
    error: Optional[str] = None
    tool_calls: int = 0
    duration_ms: int = 0
    tokens_used: int = 0


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent."""
    task: str
    skills: List[str] = field(default_factory=list)
    max_steps: int = 50
    timeout_seconds: int = 300
    model: Optional[str] = None
    temperature: float = 0.7
    inherit_memory: bool = True
    tool_whitelist: Optional[List[str]] = None


class SubAgent:
    """
    An isolated sub-agent with its own tool loop and filtered tool set.
    
    Sub-agents are lightweight workers that execute tasks with a subset
    of Ghost's capabilities, defined by their assigned skills.
    """
    
    def __init__(
        self,
        agent_id: str,
        config: SubAgentConfig,
        parent_registry: ToolRegistry,
        skill_loader: Optional[SkillLoader] = None,
        auth_store=None,
        provider_chain=None,
        memory_context: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.config = config
        self.status = SubAgentStatus.PENDING
        self.result: Optional[SubAgentResult] = None
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Threading
        self._thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        
        # Execution context
        self._parent_registry = parent_registry
        self._skill_loader = skill_loader
        self._auth_store = auth_store
        self._provider_chain = provider_chain
        self._memory_context = memory_context
        
        # Build filtered tool registry
        self._tool_registry = self._build_tool_registry()
        
        log.debug("SubAgent %s initialized with %d tools",
                  agent_id, len(self._tool_registry.list_tools()))
    
    def _build_tool_registry(self) -> ToolRegistry:
        """Build a tool registry filtered by assigned skills."""
        registry = ToolRegistry(strict_mode=True)
        
        # Get allowed tools from skills
        allowed_tools: set = set()
        if self._skill_loader and self.config.skills:
            for skill_name in self.config.skills:
                skill = self._skill_loader.get_skill(skill_name)
                if skill and skill.tools:
                    allowed_tools.update(skill.tools)
        
        # If no skills specified or whitelist provided, use whitelist
        if self.config.tool_whitelist:
            allowed_tools = set(self.config.tool_whitelist)
        
        # If still no tools allowed, inherit core tools from parent
        if not allowed_tools:
            # Default: allow safe read-only and utility tools
            allowed_tools = {
                "file_read", "grep", "glob", "web_fetch", "web_search",
                "memory_search", "shell_exec"
            }
        
        # Copy allowed tools from parent registry
        for tool_def in self._parent_registry.list_tools():
            tool_name = tool_def.get("name", "")
            if tool_name in allowed_tools:
                registry.register(tool_def)
        
        return registry

    
    def start(self) -> bool:
        """Start the sub-agent execution in a background thread."""
        with self._lock:
            if self.status != SubAgentStatus.PENDING:
                log.warning("SubAgent %s cannot start: status is %s",
                           self.agent_id, self.status.value)
                return False
            
            self.status = SubAgentStatus.RUNNING
            self.started_at = datetime.utcnow()
        
        self._thread = threading.Thread(
            target=self._run,
            name=f"SubAgent-{self.agent_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        log.info("SubAgent %s started", self.agent_id)
        return True
    
    def _run(self):
        """Main execution loop for the sub-agent."""
        start_time = time.time()
        tool_calls = 0
        
        try:
            # Build the prompt with context
            prompt = self._build_prompt()
            
            # Create isolated tool loop engine
            engine = self._create_engine()
            
            # Run the tool loop with timeout
            output_parts = []
            step = 0
            
            while step < self.config.max_steps:
                if self._cancel_event.is_set():
                    raise InterruptedError("Sub-agent cancelled by parent")
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self.config.timeout_seconds:
                    raise TimeoutError(f"Sub-agent timeout after {self.config.timeout_seconds}s")
                
                # Run one step
                response = engine.run_once(prompt)
                
                if response.get("done"):
                    output_parts.append(response.get("content", ""))
                    break
                
                # Execute tool calls
                tool_calls_list = response.get("tool_calls", [])
                for tc in tool_calls_list:
                    if self._cancel_event.is_set():
                        raise InterruptedError("Sub-agent cancelled by parent")
                    
                    tool_name = tc.get("name", "")
                    tool_result = self._execute_tool(tc)
                    tool_calls += 1
                    
                    # Add to context
                    output_parts.append(f"Tool: {tool_name}\nResult: {tool_result}")
                    
                    # Update prompt for next iteration
                    prompt = self._build_followup_prompt(prompt, tool_name, tool_result)
                
                step += 1
            
            # Build result
            duration_ms = int((time.time() - start_time) * 1000)
            output = "\n\n".join(output_parts)
            
            self.result = SubAgentResult(
                success=True,
                output=output,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
            
            with self._lock:
                self.status = SubAgentStatus.COMPLETED
                self.completed_at = datetime.utcnow()
            
            log.info("SubAgent %s completed in %dms (%d steps, %d tool calls)",
                    self.agent_id, duration_ms, step, tool_calls)
            
        except InterruptedError:
            duration_ms = int((time.time() - start_time) * 1000)
            self.result = SubAgentResult(
                success=False,
                error="Cancelled by parent",
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
            with self._lock:
                self.status = SubAgentStatus.CANCELLED
                self.completed_at = datetime.utcnow()
            log.info("SubAgent %s cancelled after %dms", self.agent_id, duration_ms)
            
        except TimeoutError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.result = SubAgentResult(
                success=False,
                error=str(e),
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
            with self._lock:
                self.status = SubAgentStatus.FAILED
                self.completed_at = datetime.utcnow()
            log.warning("SubAgent %s timed out after %dms", self.agent_id, duration_ms)
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.result = SubAgentResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
            with self._lock:
                self.status = SubAgentStatus.FAILED
                self.completed_at = datetime.utcnow()
            log.exception("SubAgent %s failed after %dms", self.agent_id, duration_ms)

    
    def _build_prompt(self) -> str:
        """Build the initial prompt for the sub-agent."""
        parts = [
            "You are a specialized sub-agent working on a specific task.",
            "Focus only on the assigned task. Use available tools efficiently.",
            "When complete, provide a clear summary of your findings or results.",
            "",
            f"Task: {self.config.task}",
        ]
        
        if self.config.skills:
            parts.append(f"Assigned skills: {', '.join(self.config.skills)}")
        
        if self._memory_context:
            parts.extend([
                "",
                "Relevant context from parent agent:",
                self._memory_context,
            ])
        
        parts.extend([
            "",
            "Available tools:",
            ", ".join(t.get("name", "") for t in self._tool_registry.list_tools()),
        ])
        
        return "\n".join(parts)
    
    def _build_followup_prompt(self, previous: str, tool_name: str, tool_result: str) -> str:
        """Build follow-up prompt after a tool execution."""
        return f"{previous}\n\nYou used {tool_name} and got:\n{tool_result[:2000]}\n\nContinue with the task."
    
    def _create_engine(self) -> ToolLoopEngine:
        """Create an isolated tool loop engine for this sub-agent."""
        # Get API key from auth store or environment
        api_key = None
        if self._auth_store:
            api_key = self._auth_store.get_api_key("openrouter")
        if not api_key:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
        
        model = self.config.model or "anthropic/claude-sonnet-4"
        
        return ToolLoopEngine(
            api_key=api_key,
            model=model,
            fallback_models=["openai/gpt-4.1-mini"],
            auth_store=self._auth_store,
            provider_chain=self._provider_chain,
        )
    
    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """Execute a single tool call."""
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})
        
        tool_def = self._tool_registry.get(tool_name)
        if not tool_def:
            return f"Error: Tool '{tool_name}' not found"
        
        try:
            execute_fn = tool_def.get("execute")
            if not execute_fn:
                return f"Error: Tool '{tool_name}' has no execute function"
            
            result = execute_fn(**arguments)
            
            # Truncate long results
            result_str = str(result)
            if len(result_str) > 5000:
                result_str = result_str[:5000] + "\n... [truncated]"
            
            return result_str
            
        except Exception as e:
            log.warning("SubAgent %s tool %s failed: %s", self.agent_id, tool_name, e)
            return f"Error executing {tool_name}: {str(e)}"
    
    def cancel(self) -> bool:
        """Cancel the sub-agent execution."""
        with self._lock:
            if self.status not in (SubAgentStatus.PENDING, SubAgentStatus.RUNNING):
                return False
            
            self._cancel_event.set()
            return True
    
    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for the sub-agent to complete."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize sub-agent state to dict."""
        with self._lock:
            return {
                "id": self.agent_id,
                "status": self.status.value,
                "config": {
                    "task": self.config.task,
                    "skills": self.config.skills,
                    "max_steps": self.config.max_steps,
                    "timeout_seconds": self.config.timeout_seconds,
                    "model": self.config.model,
                },
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "result": {
                    "success": self.result.success if self.result else None,
                    "output": self.result.output if self.result else None,
                    "error": self.result.error if self.result else None,
                    "tool_calls": self.result.tool_calls if self.result else 0,
                    "duration_ms": self.result.duration_ms if self.result else 0,
                } if self.result else None,
            }


class SubAgentRegistry:
    """
    Thread-safe registry for managing sub-agent instances.
    
    Provides lifecycle management, result aggregation, and cleanup.
    """
    
    def __init__(self, max_agents: int = 10):
        self._agents: Dict[str, SubAgent] = {}
        self._lock = threading.RLock()
        self._max_agents = max_agents
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown = False
        
        # Start background cleanup
        self._start_cleanup()
    
    def _start_cleanup(self):
        """Start background cleanup thread."""
        def cleanup_loop():
            while not self._shutdown:
                try:
                    self._cleanup_finished()
                    time.sleep(30)  # Check every 30 seconds
                except (OSError, ValueError) as e:
                    log.warning("SubAgent cleanup error: %s", e)
        
        self._cleanup_thread = threading.Thread(
            target=cleanup_loop,
            name="SubAgentCleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
    
    def _cleanup_finished(self):
        """Remove completed agents that have been around for a while."""
        with self._lock:
            now = datetime.utcnow()
            to_remove = []
            
            for agent_id, agent in self._agents.items():
                if agent.status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED, SubAgentStatus.CANCELLED):
                    if agent.completed_at:
                        age_seconds = (now - agent.completed_at).total_seconds()
                        if age_seconds > 3600:  # Remove after 1 hour
                            to_remove.append(agent_id)
            
            for agent_id in to_remove:
                del self._agents[agent_id]
                log.debug("Cleaned up sub-agent %s", agent_id)
    
    def spawn(
        self,
        config: SubAgentConfig,
        parent_registry: ToolRegistry,
        skill_loader: Optional[SkillLoader] = None,
        auth_store=None,
        provider_chain=None,
        memory_context: Optional[str] = None,
    ) -> Optional[SubAgent]:
        """
        Spawn a new sub-agent with the given configuration.
        
        Returns the SubAgent instance or None if at capacity.
        """
        with self._lock:
            # Check capacity
            active_count = sum(
                1 for a in self._agents.values()
                if a.status in (SubAgentStatus.PENDING, SubAgentStatus.RUNNING)
            )
            if active_count >= self._max_agents:
                log.warning("SubAgent spawn rejected: at capacity (%d/%d)",
                           active_count, self._max_agents)
                return None
            
            # Generate unique ID
            agent_id = f"sa_{uuid.uuid4().hex[:12]}"
            
            # Create agent
            agent = SubAgent(
                agent_id=agent_id,
                config=config,
                parent_registry=parent_registry,
                skill_loader=skill_loader,
                auth_store=auth_store,
                provider_chain=provider_chain,
                memory_context=memory_context,
            )
            
            self._agents[agent_id] = agent
        
        # Start execution (outside lock to avoid deadlock)
        agent.start()
        
        log.info("Spawned SubAgent %s (task: %s...)", agent_id, config.task[:50])
        return agent
    
    def get(self, agent_id: str) -> Optional[SubAgent]:
        """Get a sub-agent by ID."""
        with self._lock:
            return self._agents.get(agent_id)
    
    def list_agents(self, status: Optional[SubAgentStatus] = None) -> List[SubAgent]:
        """List all sub-agents, optionally filtered by status."""
        with self._lock:
            agents = list(self._agents.values())
            if status:
                agents = [a for a in agents if a.status == status]
            return agents
    
    def cancel(self, agent_id: str) -> bool:
        """Cancel a running sub-agent."""
        agent = self.get(agent_id)
        if not agent:
            return False
        return agent.cancel()
    
    def remove(self, agent_id: str) -> bool:
        """Remove a sub-agent from the registry."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            
            # Only allow removing completed/failed/cancelled agents
            if agent.status in (SubAgentStatus.PENDING, SubAgentStatus.RUNNING):
                return False
            
            del self._agents[agent_id]
            log.debug("Removed sub-agent %s", agent_id)
            return True
    
    def shutdown(self):
        """Shutdown the registry and cancel all running agents."""
        self._shutdown = True
        
        with self._lock:
            for agent in self._agents.values():
                if agent.status in (SubAgentStatus.PENDING, SubAgentStatus.RUNNING):
                    agent.cancel()
        
        # Wait a bit for graceful shutdown
        time.sleep(1)
        
        log.info("SubAgentRegistry shutdown complete")


# Global registry instance
_registry: Optional[SubAgentRegistry] = None
_registry_lock = threading.Lock()


def get_registry(max_agents: int = 10) -> SubAgentRegistry:
    """Get or create the global SubAgentRegistry."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = SubAgentRegistry(max_agents=max_agents)
        return _registry


def build_subagent_tools(cfg: Dict[str, Any], tool_registry: ToolRegistry, skill_loader=None, auth_store=None, provider_chain=None):
    """Build sub-agent management tools."""
    registry = get_registry(max_agents=cfg.get("subagent_max_agents", 10))
    
    def spawn_subagent(
        task: str,
        skills: Optional[List[str]] = None,
        max_steps: int = 50,
        timeout_seconds: int = 300,
        model: Optional[str] = None,
        **kwargs
    ):
        """
        Spawn a new sub-agent to handle a specific task in parallel.
        
        The sub-agent will execute independently with a filtered set of tools
        based on its assigned skills. Use this to parallelize work or delegate
        to specialized workers.
        
        Args:
            task: The task description for the sub-agent
            skills: List of skill names to assign (filters available tools)
            max_steps: Maximum tool loop steps (default: 50)
            timeout_seconds: Timeout in seconds (default: 300)
            model: Optional model override for this sub-agent
        
        Returns:
            Dict with agent_id and status
        """
        try:
            config = SubAgentConfig(
                task=task,
                skills=skills or [],
                max_steps=max_steps,
                timeout_seconds=timeout_seconds,
                model=model,
            )
            
            agent = registry.spawn(
                config=config,
                parent_registry=tool_registry,
                skill_loader=skill_loader,
                auth_store=auth_store,
                provider_chain=provider_chain,
            )
            
            if agent is None:
                return {"error": "Sub-agent capacity reached. Cancel some agents first."}
            
            return {
                "success": True,
                "agent_id": agent.agent_id,
                "status": agent.status.value,
                "message": f"Sub-agent {agent.agent_id} spawned successfully",
            }
            
        except (ValueError, TypeError) as e:
            log.warning("Invalid spawn_subagent params: %s", e)
            return {"error": "Invalid parameters for sub-agent spawn"}
        except Exception:
            log.exception("Failed to spawn sub-agent")
            return {"error": "Failed to spawn sub-agent due to internal error"}
    
    def list_subagents(status: Optional[str] = None, **kwargs):
        """
        List all sub-agents and their current status.
        
        Args:
            status: Filter by status (pending, running, completed, failed, cancelled)
        
        Returns:
            List of sub-agent summaries
        """
        try:
            status_filter = SubAgentStatus(status) if status else None
            agents = registry.list_agents(status=status_filter)
            
            return {
                "success": True,
                "agents": [agent.to_dict() for agent in agents],
                "count": len(agents),
            }
            
        except (ValueError, TypeError) as e:
            log.warning("Invalid list_subagents status: %s", e)
            return {"error": "Invalid status filter"}
        except Exception:
            log.exception("Failed to list sub-agents")
            return {"error": "Failed to list sub-agents due to internal error"}
    
    def get_subagent(agent_id: str, **kwargs):
        """
        Get detailed information about a specific sub-agent.
        
        Args:
            agent_id: The sub-agent ID
        
        Returns:
            Sub-agent details including result if complete
        """
        try:
            agent = registry.get(agent_id)
            if not agent:
                return {"error": f"Sub-agent {agent_id} not found"}
            
            return {
                "success": True,
                "agent": agent.to_dict(),
            }
            
        except (ValueError, TypeError) as e:
            log.warning("Invalid get_subagent params: %s", e)
            return {"error": "Invalid parameters for get sub-agent"}
        except Exception:
            log.exception("Failed to get sub-agent")
            return {"error": "Failed to get sub-agent due to internal error"}
    
    def cancel_subagent(agent_id: str, **kwargs):
        """
        Cancel a running sub-agent.
        
        Args:
            agent_id: The sub-agent ID to cancel
        
        Returns:
            Success status
        """
        try:
            success = registry.cancel(agent_id)
            if not success:
                return {"error": f"Failed to cancel {agent_id} - may not be running"}
            
            return {
                "success": True,
                "message": f"Sub-agent {agent_id} cancelled",
            }
            
        except Exception:
            log.exception("Failed to cancel sub-agent")
            return {"error": "Failed to cancel sub-agent due to internal error"}
    
    def wait_for_subagent(agent_id: str, timeout: int = 60, **kwargs):
        """
        Wait for a sub-agent to complete and return its result.
        
        Args:
            agent_id: The sub-agent ID to wait for
            timeout: Maximum seconds to wait (default: 60)
        
        Returns:
            Sub-agent result if complete, or status if still running
        """
        try:
            agent = registry.get(agent_id)
            if not agent:
                return {"error": f"Sub-agent {agent_id} not found"}
            
            completed = agent.wait(timeout=timeout)
            
            return {
                "success": True,
                "completed": completed,
                "agent": agent.to_dict(),
            }
            
        except (ValueError, TypeError) as e:
            log.warning("Invalid wait_for_subagent params: %s", e)
            return {"error": "Invalid parameters for wait sub-agent"}
        except Exception:
            log.exception("Failed to wait for sub-agent")
            return {"error": "Failed to wait for sub-agent due to internal error"}
    
    return [
        {
            "name": "spawn_subagent",
            "description": "Spawn a new sub-agent to handle a specific task in parallel. The sub-agent runs independently with a filtered set of tools based on assigned skills.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task description for the sub-agent"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "List of skill names to assign (filters available tools)"},
                    "max_steps": {"type": "integer", "description": "Maximum tool loop steps", "default": 50},
                    "timeout_seconds": {"type": "integer", "description": "Timeout in seconds", "default": 300},
                    "model": {"type": "string", "description": "Optional model override for this sub-agent"},
                },
                "required": ["task"]
            },
            "execute": spawn_subagent,
        },
        {
            "name": "list_subagents",
            "description": "List all sub-agents and their current status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (pending, running, completed, failed, cancelled)"},
                },
                "required": []
            },
            "execute": list_subagents,
        },
        {
            "name": "get_subagent",
            "description": "Get detailed information about a specific sub-agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The sub-agent ID"},
                },
                "required": ["agent_id"]
            },
            "execute": get_subagent,
        },
        {
            "name": "cancel_subagent",
            "description": "Cancel a running sub-agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The sub-agent ID to cancel"},
                },
                "required": ["agent_id"]
            },
            "execute": cancel_subagent,
        },
        {
            "name": "wait_for_subagent",
            "description": "Wait for a sub-agent to complete and return its result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The sub-agent ID to wait for"},
                    "timeout": {"type": "integer", "description": "Maximum seconds to wait", "default": 60},
                },
                "required": ["agent_id"]
            },
            "execute": wait_for_subagent,
        },
    ]
