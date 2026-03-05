"""Ghost compat: comfy_execution.graph_utils + comfy_execution.graph — stubs."""


class GraphBuilder:
    """Stub GraphBuilder for nodes that build dynamic sub-graphs."""
    def __init__(self):
        self.nodes = {}

    def node(self, class_type, **kwargs):
        node = _BuilderNode(class_type, kwargs)
        self.nodes[id(node)] = node
        return node

    def finalize(self):
        return {"nodes": self.nodes}


class _BuilderNode:
    def __init__(self, class_type, kwargs):
        self.class_type = class_type
        self.kwargs = kwargs
        self.out_idx = 0

    def out(self, idx=0):
        return (id(self), idx)

    def set_input(self, key, value):
        self.kwargs[key] = value


class ExecutionBlocker:
    """Sentinel value that blocks execution of downstream nodes."""
    def __init__(self, message=""):
        self.message = message
