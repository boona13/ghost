"""Ghost compat: comfy.cldm.cldm — ControlNet model class stub."""

import torch.nn as nn


class ControlNet(nn.Module):
    """Stub for the actual ControlNet CLDM model architecture."""
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.input_hint_block = nn.Identity()
        self.input_blocks = nn.ModuleList()
        self.zero_convs = nn.ModuleList()
        self.middle_block = nn.Identity()
        self.middle_block_out = nn.Identity()

    def forward(self, x, hint, timesteps, context, y=None, **kwargs):
        raise NotImplementedError("ControlNet CLDM forward requires full ComfyUI runtime")
