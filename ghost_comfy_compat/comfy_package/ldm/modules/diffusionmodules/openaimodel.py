"""Ghost compat: comfy.ldm.modules.diffusionmodules.openaimodel — UNet stubs."""

import torch
import torch.nn as nn

try:
    from ghost_comfy_compat.comfy_package.ldm.modules.attention import SpatialTransformer
except ImportError:
    SpatialTransformer = type("SpatialTransformer", (nn.Module,), {})


class TimestepBlock(nn.Module):
    def forward(self, x, emb):
        return x


class TimestepEmbedSequential(nn.Sequential, TimestepBlock):
    def forward(self, x, emb=None, context=None, transformer_options={}, output_shape=None, time_context=None, num_video_frames=None, image_only_indicator=None):
        for layer in self:
            if isinstance(layer, TimestepBlock):
                x = layer(x, emb)
            else:
                x = layer(x)
        return x


class Downsample(nn.Module):
    def __init__(self, channels, use_conv=False, dims=2, out_channels=None, padding=1, dtype=None, device=None, operations=None):
        super().__init__()
        self.channels = channels
        self.out_channels = out_channels or channels
        self.use_conv = use_conv
    def forward(self, x):
        return x


class Upsample(nn.Module):
    def __init__(self, channels, use_conv=False, dims=2, out_channels=None, dtype=None, device=None, operations=None):
        super().__init__()
        self.channels = channels
        self.out_channels = out_channels or channels
    def forward(self, x):
        return x


class VideoResBlock(TimestepBlock):
    def __init__(self, *args, **kwargs):
        super().__init__()


class ResBlock(TimestepBlock):
    def __init__(self, channels=None, emb_channels=None, dropout=0, out_channels=None, *args, **kwargs):
        super().__init__()
        self.channels = channels
        self.emb_channels = emb_channels
        self.out_channels = out_channels or channels


class UNetModel(nn.Module):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.input_blocks = nn.ModuleList()
        self.middle_block = TimestepEmbedSequential()
        self.output_blocks = nn.ModuleList()
        self.out = nn.Identity()
        self.model_channels = kwargs.get("model_channels", 320)

    def forward(self, x, timesteps=None, context=None, y=None, control=None, transformer_options={}, **kwargs):
        raise NotImplementedError("UNetModel.forward requires full ComfyUI runtime")
