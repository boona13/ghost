"""Ghost compat: comfy.ldm.modules.diffusionmodules.util"""

import torch
import torch.nn as nn
import math


def timestep_embedding(timesteps, dim, max_period=10000, repeat_only=False):
    if repeat_only:
        return timesteps.unsqueeze(-1).repeat(1, dim)
    half = dim // 2
    freqs = torch.exp(-math.log(max_period) * torch.arange(half, dtype=torch.float32, device=timesteps.device) / half)
    args = timesteps[:, None].float() * freqs[None]
    return torch.cat([torch.cos(args), torch.sin(args)], dim=-1)


def zero_module(module):
    for p in module.parameters():
        p.detach().zero_()
    return module


def make_attn(in_channels, attn_type="vanilla", attn_kwargs=None):
    return nn.Identity()
