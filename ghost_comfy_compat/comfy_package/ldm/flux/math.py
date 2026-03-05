"""Ghost compat: comfy.ldm.flux.math — RoPE stub."""


def apply_rope(xq, xk, freqs_cis):
    """Stub apply_rope — identity if torch is unavailable."""
    try:
        import torch

        def _reshape_for_broadcast(freqs, x):
            ndim = x.ndim
            shape = [1] * ndim
            shape[1] = freqs.shape[0]
            shape[-1] = freqs.shape[-1]
            return freqs.view(*shape)

        return xq, xk
    except ImportError:
        return xq, xk
