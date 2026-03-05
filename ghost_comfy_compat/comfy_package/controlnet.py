"""Ghost compat: comfy.controlnet — stubs for controlnet base classes.

Provides ControlBase and subclasses that Advanced-ControlNet, AnimateDiff,
and other custom nodes reference at import time.
"""

from enum import Enum


class StrengthType(Enum):
    CONSTANT = "constant"
    LINEAR_UP = "linear_up"


def broadcast_image_to(tensor, target_batch_size, batched_number):
    """Repeat tensor along batch dim to match target size."""
    import torch
    current = tensor.shape[0]
    if current == 1:
        return tensor.repeat(target_batch_size, *([1] * (len(tensor.shape) - 1)))
    per_batch = current // batched_number if batched_number > 0 else current
    if per_batch < target_batch_size // batched_number:
        tensor = tensor.repeat(target_batch_size // current, *([1] * (len(tensor.shape) - 1)))
    return tensor


class ControlBase:
    """Base class for all ControlNet-like conditioning objects."""
    def __init__(self, device=None):
        self.cond_hint_original = None
        self.cond_hint = None
        self.strength = 1.0
        self.timestep_percent_range = (0.0, 1.0)
        self.latent_format = None
        self.vae = None
        self.global_average_pooling = False
        self.device = device
        self.previous_controlnet = None
        self.extra_args = {}
        self.extra_conds = []
        self.compression_ratio = 8

    def set_cond_hint(self, cond_hint, strength=1.0, timestep_percent_range=(0.0, 1.0), vae=None):
        self.cond_hint_original = cond_hint
        self.strength = strength
        self.timestep_percent_range = timestep_percent_range
        self.vae = vae
        return self

    def set_previous_controlnet(self, controlnet):
        self.previous_controlnet = controlnet
        return self

    def cleanup(self):
        self.cond_hint = None

    def copy(self):
        c = self.__class__()
        c.cond_hint_original = self.cond_hint_original
        c.strength = self.strength
        c.timestep_percent_range = self.timestep_percent_range
        c.global_average_pooling = self.global_average_pooling
        c.device = self.device
        c.previous_controlnet = self.previous_controlnet
        return c

    def get_models(self):
        return []

    def pre_run(self, model, percent_to_timestep_function):
        pass

    def get_control(self, *args, **kwargs):
        return {}

    def get_control_expand(self, *args, **kwargs):
        return self.get_control(*args, **kwargs)


class ControlNet(ControlBase):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.control_model = None
        self.control_model_wrapped = None

    def copy(self):
        c = ControlNet()
        c.cond_hint_original = self.cond_hint_original
        c.strength = self.strength
        c.timestep_percent_range = self.timestep_percent_range
        c.device = self.device
        c.previous_controlnet = self.previous_controlnet
        return c


class ControlLora(ControlNet):
    pass


class ControlNetSD35(ControlNet):
    pass


class ControlNetFlux(ControlNet):
    pass


class T2IAdapter(ControlBase):
    pass


def load_controlnet(ckpt_path, model=None):
    raise NotImplementedError("comfy.controlnet.load_controlnet requires full ComfyUI runtime")
