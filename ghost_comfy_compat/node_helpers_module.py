"""
Ghost compat: node_helpers module.

Provides pillow context manager and conditioning helpers.
"""

import contextlib


@contextlib.contextmanager
def pillow(fn, *args, **kwargs):
    """Context manager wrapping a PIL operation with error handling."""
    try:
        from PIL import Image
        result = fn(*args, **kwargs)
        yield result
    except Exception as e:
        raise ValueError(f"PIL operation failed: {e}") from e


def conditioning_set_values(conditioning, values: dict):
    """Set values on conditioning entries."""
    out = []
    for c in conditioning:
        n = [c[0], dict(c[1])]
        n[1].update(values)
        out.append(n)
    return out


def open_image(path):
    """Open an image file and return a PIL Image."""
    from PIL import Image
    return Image.open(path)
