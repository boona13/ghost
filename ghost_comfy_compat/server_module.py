"""
Ghost compat: server module.

Provides PromptServer singleton with no-op send_sync for progress reporting.
"""

import logging

log = logging.getLogger("ghost.comfy_compat.server")


class _Routes:
    """Stub routes object for PromptServer.instance.app.add_routes."""
    def __init__(self):
        self._routes = []

    def get(self, path, **kwargs):
        def decorator(func):
            self._routes.append(("GET", path, func))
            return func
        return decorator

    def post(self, path, **kwargs):
        def decorator(func):
            self._routes.append(("POST", path, func))
            return func
        return decorator

    def static(self, prefix, path):
        pass


class _App:
    """Stub aiohttp app."""
    def __init__(self):
        self.router = self

    def add_routes(self, routes):
        pass

    def add_static(self, prefix, path, **kwargs):
        pass


class _StubPromptQueue:
    """Stub prompt queue for custom nodes that access PromptServer.prompt_queue."""
    def put(self, item):
        pass
    def get(self, *args, **kwargs):
        return None
    def task_done(self):
        pass
    def get_current_queue(self):
        return [], []


class PromptServer:
    instance = None

    def __init__(self):
        self.app = _App()
        self.routes = _Routes()
        self.loop = None
        self.messages = None
        self.number = 0
        self.supports = []
        self.client_id = None
        self.prompt_queue = _StubPromptQueue()
        self.last_node_id = None
        self.last_prompt_id = None

    def send_sync(self, event: str, data: dict, sid=None):
        """No-op progress callback — Ghost handles progress via its own system."""
        pass

    def add_routes(self):
        pass

    def add_on_prompt_handler(self, handler):
        """No-op — Ghost doesn't use ComfyUI's prompt handler system."""
        pass

    def send_progress(self, event: str, data: dict, sid=None):
        pass

    @classmethod
    def _ensure_instance(cls):
        if cls.instance is None:
            cls.instance = cls()
        return cls.instance


PromptServer._ensure_instance()

web = _App()

