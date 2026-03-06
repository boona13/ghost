"""
Example Ghost Extension — comprehensive reference implementation.

This serves as a template for Ghost's autonomous Feature Implementer.
It demonstrates EVERY pattern an extension should use:
  - Settings via api.get_setting()
  - LLM-powered intelligence via api.llm_summarize()
  - Persistent memory via api.memory_save() / api.memory_search()
  - Extension-local data via api.read_data() / api.write_data()
  - Input validation, error handling, and structured output
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

    def on_boot():
        api.log("Example extension booted — demonstrating lifecycle hooks")
        prior = api.memory_search("example_ext summary", limit=1)
        if prior:
            api.log(f"Found {len(prior)} prior summaries in memory")

    api.register_hook("on_boot", on_boot)

    def on_chat_message(**kwargs):
        """Detect long pastes and hint that summarization is available."""
        data = kwargs if kwargs else {}
        msg = data.get("message", "")
        if len(msg) > 2000:
            api.log(
                f"Long message detected ({len(msg)} chars) — "
                "example_smart_summarize could help digest this"
            )

    api.register_hook("on_chat_message", on_chat_message)
