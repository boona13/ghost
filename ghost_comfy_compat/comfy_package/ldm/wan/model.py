"""Ghost compat: comfy.ldm.wan.model — Wan model stubs."""

import math


def sinusoidal_embedding_1d(dim, position):
    """Sinusoidal positional embedding."""
    try:
        import torch
        half = dim // 2
        freqs = torch.exp(-math.log(10000.0) * torch.arange(0, half, dtype=torch.float32) / half)
        if isinstance(position, (int, float)):
            position = torch.tensor([position], dtype=torch.float32)
        args = position.unsqueeze(-1).float() * freqs.unsqueeze(0)
        return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)
    except ImportError:
        return None
