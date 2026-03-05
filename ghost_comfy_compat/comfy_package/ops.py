"""
Ghost compat: comfy.ops — operation wrappers for dtype/device casting.

Provides the disable_weight_init and manual_cast classes that many custom
nodes reference for model operation wrappers. These are thin wrappers
around standard torch.nn modules.
"""

import torch
import torch.nn as nn


class disable_weight_init:
    """Namespace of nn.Module subclasses that skip weight initialization."""
    class Linear(nn.Linear):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class Conv1d(nn.Conv1d):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class Conv2d(nn.Conv2d):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class Conv3d(nn.Conv3d):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class GroupNorm(nn.GroupNorm):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class LayerNorm(nn.LayerNorm):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class Embedding(nn.Embedding):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class ConvTranspose2d(nn.ConvTranspose2d):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None

    class ConvTranspose1d(nn.ConvTranspose1d):
        comfy_cast_weights = False
        def reset_parameters(self):
            return None


class manual_cast(disable_weight_init):
    """Same as disable_weight_init but with manual dtype casting on forward."""

    class Linear(disable_weight_init.Linear):
        comfy_cast_weights = True
        def forward(self, input):
            weight = self.weight.to(input.dtype)
            bias = self.bias.to(input.dtype) if self.bias is not None else None
            return torch.nn.functional.linear(input, weight, bias)

    class Conv2d(disable_weight_init.Conv2d):
        comfy_cast_weights = True
        def forward(self, input):
            weight = self.weight.to(input.dtype)
            bias = self.bias.to(input.dtype) if self.bias is not None else None
            return self._conv_forward(input, weight, bias)

    class Conv1d(disable_weight_init.Conv1d):
        comfy_cast_weights = True

    class Conv3d(disable_weight_init.Conv3d):
        comfy_cast_weights = True

    class GroupNorm(disable_weight_init.GroupNorm):
        comfy_cast_weights = True

    class LayerNorm(disable_weight_init.LayerNorm):
        comfy_cast_weights = True

    class Embedding(disable_weight_init.Embedding):
        comfy_cast_weights = True

    class ConvTranspose2d(disable_weight_init.ConvTranspose2d):
        comfy_cast_weights = True

    class ConvTranspose1d(disable_weight_init.ConvTranspose1d):
        comfy_cast_weights = True


cast_bias_weight = manual_cast
