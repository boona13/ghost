"""Example ghost tool — demonstrates the register(api) pattern.

This tool is disabled by default (enabled: false in TOOL.yaml).
To enable: set enabled: true, or use Ghost's tools_enable("_example").
"""

import json


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    api.register_setting({
        "key": "greeting_prefix",
        "label": "Greeting Prefix",
        "type": "string",
        "description": "Word used to greet (e.g. Hello, Hi, Hey)",
    })

    prefix = api.get_setting("greeting_prefix", "Hello")

    def execute_greet(name: str = "world", **kwargs):
        greeting = f"{prefix}, {name}! This is a ghost tool."
        api.log(f"Greeted {name}")
        return json.dumps({"status": "ok", "message": greeting})

    api.register_tool({
        "name": "example_greet",
        "description": "Greet someone by name (example tool).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to greet",
                },
            },
        },
        "execute": execute_greet,
    })

    def on_boot():
        api.log("Example tool ready")

    api.register_hook("on_boot", on_boot)
