"""Ghost compat: comfy.ldm.modules.attention — attention stubs.

Provides attention function variants and transformer block stubs that
AnimateDiff-Evolved and Advanced-ControlNet reference at import time.
"""

import logging
import torch
import torch.nn as nn

log = logging.getLogger("ghost.comfy_compat.attention")


def default(val, d):
    """Return val if it exists/is not None, else d (or call d if callable)."""
    if val is not None:
        return val
    return d() if callable(d) else d


def exists(val):
    return val is not None


class GEGLU(nn.Module):
    def __init__(self, dim_in, dim_out):
        super().__init__()
        self.proj = nn.Linear(dim_in, dim_out * 2)
    def forward(self, x):
        x, gate = self.proj(x).chunk(2, dim=-1)
        return x * torch.nn.functional.gelu(gate)


class FeedForward(nn.Module):
    def __init__(self, dim, dim_out=None, mult=4, glu=False, dropout=0.0):
        super().__init__()
        inner_dim = int(dim * mult)
        dim_out = default(dim_out, dim)
        self.net = nn.Sequential(
            GEGLU(dim, inner_dim),
            nn.Dropout(dropout),
            nn.Linear(inner_dim, dim_out),
        )
    def forward(self, x, **kwargs):
        return self.net(x)


class CrossAttention(nn.Module):
    def __init__(self, query_dim, context_dim=None, heads=8, dim_head=64, dropout=0.0, dtype=None, device=None, operations=None):
        super().__init__()
        inner_dim = dim_head * heads
        context_dim = default(context_dim, query_dim)
        ops = operations or nn
        self.heads = heads
        self.dim_head = dim_head
        self.to_q = ops.Linear(query_dim, inner_dim, bias=False)
        self.to_k = ops.Linear(context_dim, inner_dim, bias=False)
        self.to_v = ops.Linear(context_dim, inner_dim, bias=False)
        self.to_out = nn.Sequential(ops.Linear(inner_dim, query_dim), nn.Dropout(dropout))
    def forward(self, x, context=None, value=None, mask=None, transformer_options={}):
        context = default(context, x)
        q = self.to_q(x)
        k = self.to_k(context)
        v = self.to_v(default(value, context))
        out = optimized_attention(q, k, v, self.heads, mask=mask)
        return self.to_out(out)


class BasicTransformerBlock(nn.Module):
    def __init__(self, dim, n_heads, d_head, dropout=0.0, context_dim=None, gated_ff=True, checkpoint=True, ff_inner_dim=None, dtype=None, device=None, operations=None):
        super().__init__()
        self.attn1 = CrossAttention(query_dim=dim, heads=n_heads, dim_head=d_head, dropout=dropout, dtype=dtype, device=device, operations=operations)
        self.ff = FeedForward(dim, dropout=dropout, glu=gated_ff)
        self.attn2 = CrossAttention(query_dim=dim, context_dim=context_dim, heads=n_heads, dim_head=d_head, dropout=dropout, dtype=dtype, device=device, operations=operations)
        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.norm3 = nn.LayerNorm(dim)
        self.n_heads = n_heads
        self.d_head = d_head
    def forward(self, x, context=None, transformer_options={}):
        x = self.attn1(self.norm1(x), transformer_options=transformer_options) + x
        x = self.attn2(self.norm2(x), context=context, transformer_options=transformer_options) + x
        x = self.ff(self.norm3(x)) + x
        return x


class SpatialTransformer(nn.Module):
    def __init__(self, in_channels, n_heads, d_head, depth=1, dropout=0.0, context_dim=None, disable_self_attn=False, use_linear=False, use_checkpoint=True, dtype=None, device=None, operations=None):
        super().__init__()
        inner_dim = n_heads * d_head
        ops = operations or nn
        self.norm = nn.GroupNorm(32, in_channels, eps=1e-6)
        self.proj_in = ops.Linear(in_channels, inner_dim) if use_linear else ops.Conv2d(in_channels, inner_dim, kernel_size=1)
        self.transformer_blocks = nn.ModuleList([
            BasicTransformerBlock(inner_dim, n_heads, d_head, dropout=dropout, context_dim=context_dim, dtype=dtype, device=device, operations=operations)
            for _ in range(depth)
        ])
        self.proj_out = ops.Linear(inner_dim, in_channels) if use_linear else ops.Conv2d(inner_dim, in_channels, kernel_size=1)
        self.use_linear = use_linear
        self.in_channels = in_channels
    def forward(self, x, context=None, transformer_options={}):
        b, c, h, w = x.shape
        x_in = x
        x = self.norm(x)
        if not self.use_linear:
            x = self.proj_in(x)
        x = x.permute(0, 2, 3, 1).reshape(b, h * w, c)
        if self.use_linear:
            x = self.proj_in(x)
        for block in self.transformer_blocks:
            x = block(x, context=context, transformer_options=transformer_options)
        if self.use_linear:
            x = self.proj_out(x)
        x = x.reshape(b, h, w, c).permute(0, 3, 1, 2)
        if not self.use_linear:
            x = self.proj_out(x)
        return x + x_in


class SpatialVideoTransformer(SpatialTransformer):
    pass


def optimized_attention(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False):
    """Stub optimized attention — uses naive scaled dot product."""
    try:
        import torch
        import torch.nn.functional as F

        if not skip_reshape:
            b, seq_q, dim = q.shape
            seq_k = k.shape[1]
            head_dim = dim // heads
            q = q.view(b, seq_q, heads, head_dim).transpose(1, 2)
            k = k.view(b, seq_k, heads, head_dim).transpose(1, 2)
            v = v.view(b, seq_k, heads, head_dim).transpose(1, 2)

        out = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)

        if not skip_reshape:
            out = out.transpose(1, 2).reshape(b, seq_q, dim)
        return out
    except Exception as e:
        raise NotImplementedError(f"optimized_attention fallback failed: {e}")


def optimized_attention_masked(q, k, v, heads, mask=None, attn_precision=None):
    return optimized_attention(q, k, v, heads, mask=mask, attn_precision=attn_precision)


def wrap_attn(attn_fn):
    """Identity wrapper — returns the attention function unchanged."""
    return attn_fn


def attention_basic(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False):
    return optimized_attention(q, k, v, heads, mask=mask, attn_precision=attn_precision, skip_reshape=skip_reshape)


def attention_sub_quad(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False):
    return optimized_attention(q, k, v, heads, mask=mask, attn_precision=attn_precision, skip_reshape=skip_reshape)


def attention_split(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False):
    return optimized_attention(q, k, v, heads, mask=mask, attn_precision=attn_precision, skip_reshape=skip_reshape)


def attention_pytorch(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False):
    return optimized_attention(q, k, v, heads, mask=mask, attn_precision=attn_precision, skip_reshape=skip_reshape)
