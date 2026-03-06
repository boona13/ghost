"""
Example Ghost Extension — demonstrates the register(api) pattern.

This is a reference implementation for extension developers and for Ghost's
autonomous Feature Implementer to use as a template.
"""

import json


def register(api):
    """Entry point called by ExtensionManager during load."""

    greeting = api.get_setting("greeting", "Hello from the extension system!")

    def execute_hello(name: str = "World", **_kw):
        return json.dumps({
            "status": "ok",
            "message": f"{greeting} {name}!",
            "extension": api.id,
        })

    api.register_tool({
        "name": "example_hello",
        "description": "A simple greeting tool from the example extension.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to greet",
                },
            },
        },
        "execute": execute_hello,
    })

    def on_boot():
        api.log("Example extension booted successfully")

    api.register_hook("on_boot", on_boot)
