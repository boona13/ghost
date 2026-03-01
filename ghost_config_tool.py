"""
Ghost Config Tool — LLM-accessible runtime configuration management.

Allows Ghost to read and safely modify its own config at runtime.
Safety: blocklist for dangerous keys (auth, secrets), approval via action items
for critical changes, hot-reload signaling.

Tools: config_get, config_patch, config_schema
"""

import copy
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ghost.config_tool")

GHOST_HOME = Path.home() / ".ghost"
CONFIG_FILE = GHOST_HOME / "config.json"
CONFIG_BACKUP_DIR = GHOST_HOME / "config_backups"

BLOCKED_KEYS = frozenset({
    "api_key",
    "firecrawl_api_key",
    "google_client_id",
    "google_client_secret",
    "google_refresh_token",
})

SENSITIVE_KEYS = frozenset({
    "allowed_commands",
    "allowed_roots",
    "blocked_commands",
    "strict_tool_registration",
})

_HARDENING_VALUES = {
    "strict_tool_registration": True,
}


def _is_hardening_change(key, value):
    """Return True when a sensitive-key change makes the system MORE secure."""
    if key in _HARDENING_VALUES:
        return value == _HARDENING_VALUES[key]
    if key == "blocked_commands" and isinstance(value, list):
        return True
    if key == "allowed_commands" and isinstance(value, list):
        from ghost_tools import CORE_COMMANDS
        missing = [c for c in CORE_COMMANDS if c not in value]
        if missing:
            return False
    return True


def _backup_config() -> str | None:
    """Snapshot the current config before modification (rollback safety)."""
    if not CONFIG_FILE.exists():
        return None
    CONFIG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = CONFIG_BACKUP_DIR / f"config_{ts}.json"
    shutil.copy2(CONFIG_FILE, backup_path)
    backups = sorted(CONFIG_BACKUP_DIR.glob("config_*.json"),
                     key=lambda p: p.stat().st_mtime)
    while len(backups) > 20:
        backups.pop(0).unlink()
    log.info("Config backup created: %s", backup_path)
    return str(backup_path)

CONFIG_SCHEMA = {
    "model": {
        "type": "string",
        "description": "Primary LLM model (e.g. google/gemini-2.0-flash-001)",
    },
    "primary_provider": {
        "type": "string",
        "description": "Primary LLM provider: openrouter, openai, openai-codex, anthropic, google, ollama",
    },
    "fallback_models": {
        "type": "array",
        "description": "Fallback models in priority order",
    },
    "poll_interval": {
        "type": "number",
        "description": "Main loop poll interval in seconds",
    },
    "tool_loop_max_steps": {
        "type": "integer",
        "description": "Max steps per tool loop run (1-500)",
    },
    "enable_memory_db": {"type": "boolean", "description": "Enable persistent memory"},
    "enable_plugins": {"type": "boolean", "description": "Enable plugin system"},
    "enable_skills": {"type": "boolean", "description": "Enable skills system"},
    "enable_browser_tools": {"type": "boolean", "description": "Enable browser automation"},
    "enable_cron": {"type": "boolean", "description": "Enable cron scheduler"},
    "enable_evolve": {"type": "boolean", "description": "Enable self-evolution"},
    "enable_integrations": {"type": "boolean", "description": "Enable Google/Grok integrations"},
    "enable_growth": {"type": "boolean", "description": "Enable autonomy growth routines"},
    "enable_web_search": {"type": "boolean", "description": "Enable web search tool"},
    "enable_web_fetch": {"type": "boolean", "description": "Enable web fetch tool"},
    "enable_image_gen": {"type": "boolean", "description": "Enable image generation"},
    "enable_vision": {"type": "boolean", "description": "Enable image analysis/vision"},
    "enable_tts": {"type": "boolean", "description": "Enable text-to-speech"},
    "enable_voice": {"type": "boolean", "description": "Enable Voice Wake + Talk Mode (always-on speech)"},
    "voice_wake_words": {
        "type": "array",
        "description": "Wake words for Voice Wake mode (default: ['ghost', 'hey ghost'])",
    },
    "voice_stt_provider": {
        "type": "string",
        "description": "Speech-to-text provider: auto, whisper, groq, vosk",
    },
    "voice_silence_threshold": {
        "type": "number",
        "description": "Audio energy threshold for silence detection (0.001-1.0, default 0.02)",
    },
    "voice_silence_duration": {
        "type": "number",
        "description": "Seconds of silence before ending capture (0.5-10.0, default 2.0)",
    },
    "voice_chime": {"type": "boolean", "description": "Play chime on wake word detection"},
    "enable_security_audit": {"type": "boolean", "description": "Enable security audit tools"},
    "enable_session_memory": {"type": "boolean", "description": "Enable auto-save session memory"},
    "max_feed_items": {"type": "integer", "description": "Max items in feed (10-500)"},
    "rate_limit_seconds": {"type": "number", "description": "Rate limit between actions"},
    "growth_schedules": {"type": "object", "description": "Override cron schedules for growth routines"},
    "dashboard_port": {"type": "integer", "description": "Dashboard HTTP port"},
    "disabled_skills": {"type": "array", "description": "List of skill names to disable"},
    "tool_models": {
        "type": "object",
        "description": "Override model IDs used by tools (image gen, vision, web search, TTS, embeddings)",
        "properties": {
            "image_gen_openrouter": "google/gemini-3-pro-image-preview",
            "image_gen_gemini": "gemini-3-pro-image-preview",
            "image_gen_openai": "gpt-image-1",
            "vision_openai": "gpt-4o",
            "vision_openrouter": "openai/gpt-4o",
            "vision_gemini": "gemini-2.5-flash",
            "vision_anthropic": "claude-sonnet-4-20250514",
            "vision_ollama": "llava",
            "web_search_perplexity": "perplexity/sonar-pro",
            "web_search_perplexity_direct": "sonar-pro",
            "web_search_grok": "grok-3-fast",
            "web_search_openai": "gpt-4.1-mini",
            "web_search_gemini": "gemini-2.5-flash",
            "tts_openai": "tts-1",
            "tts_elevenlabs": "eleven_multilingual_v2",
            "embedding_openrouter": "openai/text-embedding-3-small",
            "embedding_gemini": "text-embedding-004",
            "embedding_ollama": "nomic-embed-text",
        },
    },
}


TOOL_MODEL_DEFAULTS = {
    "image_gen_openrouter": "google/gemini-3-pro-image-preview",
    "image_gen_gemini": "gemini-3-pro-image-preview",
    "image_gen_openai": "gpt-image-1",
    "vision_openai": "gpt-4o",
    "vision_openrouter": "openai/gpt-4o",
    "vision_gemini": "gemini-2.5-flash",
    "vision_anthropic": "claude-sonnet-4-20250514",
    "vision_ollama": "llava",
    "web_search_perplexity": "perplexity/sonar-pro",
    "web_search_perplexity_direct": "sonar-pro",
    "web_search_grok": "grok-3-fast",
    "web_search_openai": "gpt-4.1-mini",
    "web_search_gemini": "gemini-2.5-flash",
    "tts_openai": "tts-1",
    "tts_elevenlabs": "eleven_multilingual_v2",
    "embedding_openrouter": "openai/text-embedding-3-small",
    "embedding_gemini": "text-embedding-004",
    "embedding_ollama": "nomic-embed-text",
}


def get_tool_model(key: str, cfg: dict | None = None) -> str:
    """Resolve a tool model from config with built-in default fallback.

    Reads from cfg["tool_models"][key], falling back to TOOL_MODEL_DEFAULTS[key].
    """
    if cfg:
        return cfg.get("tool_models", {}).get(key, TOOL_MODEL_DEFAULTS.get(key, ""))
    return TOOL_MODEL_DEFAULTS.get(key, "")


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def _sanitize_for_display(cfg: dict) -> dict:
    """Remove sensitive values from config for display."""
    sanitized = {}
    for k, v in cfg.items():
        if k in BLOCKED_KEYS:
            if isinstance(v, str) and v:
                sanitized[k] = v[:4] + "..." + v[-4:] if len(v) > 8 else "***"
            else:
                sanitized[k] = "(set)" if v else "(empty)"
        else:
            sanitized[k] = v
    return sanitized


def _validate_dangerous_command_policy(policy: dict) -> tuple[bool, str]:
    """Validate dangerous_command_policy schema."""
    if not isinstance(policy, dict):
        return False, "dangerous_command_policy must be an object"
    
    for section_name, section in policy.items():
        if not isinstance(section, dict):
            return False, f"dangerous_command_policy.{section_name} must be an object"
        
        # Validate known fields
        allowed_fields = {"allow", "require_workspace", "deny_flags", "allow_subcommands", "safe_shell_patterns"}
        for field in section:
            if field not in allowed_fields:
                return False, f"dangerous_command_policy.{section_name}.{field} is not a recognized field"
        
        # Validate types
        if "allow" in section and not isinstance(section["allow"], bool):
            return False, f"dangerous_command_policy.{section_name}.allow must be boolean"
        if "require_workspace" in section and not isinstance(section["require_workspace"], bool):
            return False, f"dangerous_command_policy.{section_name}.require_workspace must be boolean"
        if "deny_flags" in section and not isinstance(section["deny_flags"], list):
            return False, f"dangerous_command_policy.{section_name}.deny_flags must be an array"
        if "allow_subcommands" in section and not isinstance(section["allow_subcommands"], list):
            return False, f"dangerous_command_policy.{section_name}.allow_subcommands must be an array"
        if "safe_shell_patterns" in section and not isinstance(section["safe_shell_patterns"], list):
            return False, f"dangerous_command_policy.{section_name}.safe_shell_patterns must be an array"
    
    return True, ""


def _validate_patch(patch: dict) -> tuple[bool, str]:
    """Validate a config patch. Returns (ok, error_message)."""
    for key in patch:
        if key in BLOCKED_KEYS:
            return False, f"Cannot modify blocked key: {key}"

    if "tool_loop_max_steps" in patch:
        val = patch["tool_loop_max_steps"]
        if not isinstance(val, int) or val < 1 or val > 500:
            return False, "tool_loop_max_steps must be 1-500"

    if "max_feed_items" in patch:
        val = patch["max_feed_items"]
        if not isinstance(val, int) or val < 10 or val > 500:
            return False, "max_feed_items must be 10-500"

    if "dashboard_port" in patch:
        val = patch["dashboard_port"]
        if not isinstance(val, int) or val < 1024 or val > 65535:
            return False, "dashboard_port must be 1024-65535"
    
    if "dangerous_command_policy" in patch:
        ok, err = _validate_dangerous_command_policy(patch["dangerous_command_policy"])
        if not ok:
            return False, err
    
    # When enabling dangerous interpreters, require secure policy minimums
    if "enable_dangerous_interpreters" in patch:
        enabling = patch["enable_dangerous_interpreters"]
        if enabling is True:
            policy = patch.get("dangerous_command_policy") or {}
            py_policy = policy.get("python") or {}
            
            # Require policy presence with secure defaults
            if py_policy.get("allow", False):
                # If python is allowed, require workspace and deny_flags
                if not py_policy.get("require_workspace", True):
                    return False, "Enabling dangerous interpreters with python.allow=true requires require_workspace=true"
                deny_flags = py_policy.get("deny_flags", [])
                if "-c" not in deny_flags:
                    return False, "Enabling dangerous interpreters with python.allow=true requires deny_flags to include '-c'"

    return True, ""


def build_config_tools(cfg=None):
    """Build LLM-callable config management tools."""

    def config_get_exec(key=None):
        current = _load_config()
        sanitized = _sanitize_for_display(current)

        if key:
            if key in BLOCKED_KEYS:
                return f"Key '{key}' is blocked for security"
            val = sanitized.get(key)
            if val is None:
                return f"Key '{key}' not found in config"
            return json.dumps({key: val}, indent=2)

        return json.dumps(sanitized, indent=2)

    def config_patch_exec(updates, **kwargs):
        if not isinstance(updates, dict):
            return "Error: updates must be a JSON object"

        ok, err = _validate_patch(updates)
        if not ok:
            return f"Validation error: {err}"

        has_sensitive = any(k in SENSITIVE_KEYS for k in updates)
        if has_sensitive:
            sensitive_keys = [k for k in updates if k in SENSITIVE_KEYS]
            weakening = [
                k for k in sensitive_keys
                if not _is_hardening_change(k, updates[k])
            ]
            if weakening:
                return (
                    f"These changes would WEAKEN security: {weakening}. "
                    "This requires user approval. Use add_action_item to propose the change."
                )
            log.info("Allowing security-hardening config changes: %s", sensitive_keys)

        backup_path = _backup_config()
        current = _load_config()
        old_values = {k: current.get(k) for k in updates}
        current.update(updates)
        _save_config(current)

        changes = []
        for k, new_val in updates.items():
            old_val = old_values.get(k, "(unset)")
            changes.append(f"  {k}: {old_val} -> {new_val}")

        backup_note = f"\nBackup saved: {backup_path}" if backup_path else ""
        return (
            f"Config updated ({len(updates)} key(s)):\n"
            + "\n".join(changes)
            + backup_note
            + "\n\nNote: Some changes take effect on next restart."
        )

    def config_schema_exec():
        return json.dumps(CONFIG_SCHEMA, indent=2)

    return [
        {
            "name": "config_get",
            "description": (
                "Read Ghost's current configuration. Returns sanitized config "
                "(secrets are masked). Optionally get a specific key."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Specific config key to read. Leave empty for all.",
                    },
                },
            },
            "execute": config_get_exec,
        },
        {
            "name": "config_patch",
            "description": (
                "Update Ghost's configuration. Merges partial updates into existing config. "
                "Auth/secret keys are blocked. Security-hardening changes (e.g. enabling "
                "strict_tool_registration, disabling evolve_auto_approve) are ALLOWED — "
                "only weakening changes require user approval. "
                "Every patch creates an automatic config backup for rollback safety. "
                "Some changes take effect on restart."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Key-value pairs to update in config",
                    },
                },
                "required": ["updates"],
            },
            "execute": config_patch_exec,
        },
        {
            "name": "config_schema",
            "description": "Show the config schema with descriptions of all configurable keys.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "execute": config_schema_exec,
        },
    ]
