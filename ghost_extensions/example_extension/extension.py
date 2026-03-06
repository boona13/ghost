"""
Example Ghost Extension — comprehensive reference implementation.

This serves as a template for Ghost's autonomous Feature Implementer.
It demonstrates EVERY pattern an extension should use:

  TOOLS & INTELLIGENCE:
  - Tool registration via api.register_tool()
  - Settings via api.get_setting()
  - LLM-powered intelligence via api.llm_summarize()
  - Persistent memory via api.memory_save() / api.memory_search()
  - Extension-local data via api.read_data() / api.write_data()

  DASHBOARD PAGE + API ROUTES (critical for UI extensions):
  - Flask Blueprint with API routes via api.register_route()
  - Dashboard page via api.register_page()
  - JS page file in static/ that calls /api/<ext_name>/... endpoints
  - IMPORTANT: tools (register_tool) are NOT HTTP endpoints!
    If your page needs to load/save data, you MUST create Flask routes.
    The JS frontend calls /api/<ext_name>/... served by your Blueprint.

  LIFECYCLE:
  - Lifecycle hooks (on_boot, on_chat_message)
  - Channels for notifications via api.channel_send()
"""

import json
import time


def register(api):
    """Entry point called by ExtensionManager during load.

    The `api` argument is an ExtensionAPI instance providing:
      Registration:  register_tool, register_hook, register_cron,
                     register_page, register_route, register_setting
      Intelligence:  llm_summarize(text, instruction, max_tokens)
      Memory:        memory_save(content, tags, memory_type)
                     memory_search(query, limit)
      Channels:      channel_send(message, channel_id)
                     get_channels()
      Settings:      get_setting(key, default) / set_setting(key, value)
      Data:          read_data(filename) / write_data(filename, content)
      Media:         save_media(data, filename, media_type, ...)
      Logging:       log(message)
      Properties:    id, manifest, extension_dir, data_dir
    """

    max_length = api.get_setting("max_summary_length", 200)

    # ═══════════════════════════════════════════════════════════════
    #  TOOL: example_smart_summarize
    # ═══════════════════════════════════════════════════════════════

    def execute_smart_summarize(text: str = "", **_kw):
        """Summarize text using the LLM, not regex."""
        if not text or not text.strip():
            return json.dumps({"status": "error", "error": "No text provided"})

        instruction = (
            f"Summarize the following text in at most {max_length} words. "
            "Extract key decisions, action items, and important facts. "
            "Return a structured summary with bullet points."
        )
        summary = api.llm_summarize(text, instruction=instruction, max_tokens=512)

        if not summary:
            return json.dumps({"status": "error", "error": "LLM summarization failed"})

        history = json.loads(api.read_data("history.json") or "[]")
        history.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "input_length": len(text),
            "summary_preview": summary[:120],
        })
        api.write_data("history.json", json.dumps(history[-50:], indent=2))

        api.memory_save(
            content=f"[example_ext summary] {summary}",
            tags="extension,example,summary",
            memory_type="note",
        )

        return json.dumps({
            "status": "ok",
            "summary": summary,
            "input_length": len(text),
            "extension": api.id,
        })

    api.register_tool({
        "name": "example_smart_summarize",
        "description": (
            "Summarize text using LLM intelligence. Extracts key decisions, "
            "action items, and facts. Saves result to memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to summarize",
                },
            },
            "required": ["text"],
        },
        "execute": execute_smart_summarize,
    })

    # ═══════════════════════════════════════════════════════════════
    #  DASHBOARD API ROUTES (Flask Blueprint)
    #  MANDATORY when your extension has a dashboard page.
    #  The JS frontend calls these endpoints — tools are NOT HTTP!
    # ═══════════════════════════════════════════════════════════════

    from flask import Blueprint, request as flask_request, jsonify

    bp = Blueprint("example_api", __name__, url_prefix="/api/example")

    @bp.route("/history", methods=["GET"])
    def api_history():
        """Return summary history for the dashboard page."""
        raw = api.read_data("history.json") or "[]"
        try:
            history = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            history = []
        return jsonify({"status": "ok", "history": history})

    @bp.route("/summarize", methods=["POST"])
    def api_summarize():
        """Run summarization from the dashboard page."""
        data = flask_request.get_json(silent=True) or {}
        text = data.get("text", "")
        result_str = execute_smart_summarize(text=text)
        return jsonify(json.loads(result_str))

    @bp.route("/clear", methods=["POST"])
    def api_clear():
        """Clear summary history."""
        api.write_data("history.json", "[]")
        return jsonify({"status": "ok"})

    api.register_route(bp)

    # ═══════════════════════════════════════════════════════════════
    #  DASHBOARD PAGE
    #  js_path points to static/<file>.js which must export render().
    #  The JS file calls /api/example/... endpoints served above.
    # ═══════════════════════════════════════════════════════════════

    api.register_page({
        "id": "example_extension",
        "label": "Example",
        "icon": "beaker",
        "section": "system",
        "js_path": "example_page.js",
    })

    # ═══════════════════════════════════════════════════════════════
    #  LIFECYCLE HOOKS
    # ═══════════════════════════════════════════════════════════════

    def on_boot():
        api.log("Example extension booted — demonstrating lifecycle hooks")
        prior = api.memory_search("example_ext summary", limit=1)
        if prior:
            api.log(f"Found {len(prior)} prior summaries in memory")

    api.register_hook("on_boot", on_boot)

    def on_chat_message(**kwargs):
        """Detect long pastes and hint that summarization is available.

        on_chat_message kwargs: role, content, session_id
        """
        content = kwargs.get("content", "")
        if len(content) > 2000:
            api.log(
                f"Long message detected ({len(content)} chars) — "
                "example_smart_summarize could help digest this"
            )

    api.register_hook("on_chat_message", on_chat_message)
