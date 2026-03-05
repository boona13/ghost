"""Ghost compat: comfy.ldm.util"""


def exists(val):
    return val is not None


def default(val, d):
    if exists(val):
        return val
    return d() if callable(d) else d
