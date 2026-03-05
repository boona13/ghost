"""
Ghost compat: nodes module.

Provides NODE_CLASS_MAPPINGS populated from Ghost's NATIVE_NODES,
MAX_RESOLUTION, and stub references to core node classes.

When a custom node does `from nodes import CLIPTextEncode`, it gets
Ghost's native implementation — making cross-node references work.
"""

MAX_RESOLUTION = 16384

NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}
EXTENSION_WEB_DIRS: dict = {}
LOADED_MODULE_DIRS: dict = {}


def _populate_from_native_nodes():
    """Pull in Ghost's NATIVE_NODES so custom nodes can reference core nodes.

    Also sets each node class as a module-level attribute so that
    `from nodes import CLIPTextEncode` works directly.
    """
    try:
        from ghost_comfyui_engine import NATIVE_NODES
        import sys
        this_module = sys.modules[__name__]

        NODE_CLASS_MAPPINGS.update(NATIVE_NODES)
        for name, cls in NATIVE_NODES.items():
            NODE_DISPLAY_NAME_MAPPINGS[name] = name
            safe_name = name.replace(" ", "_").replace("+", "Plus").replace(":", "_")
            if not hasattr(this_module, name):
                setattr(this_module, name, cls)
            if safe_name != name and not hasattr(this_module, safe_name):
                setattr(this_module, safe_name, cls)
    except ImportError:
        pass


_populate_from_native_nodes()


class ControlNetApplyAdvanced:
    """Built-in ComfyUI node: apply ControlNet with advanced settings."""
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "control_net": ("CONTROL_NET",),
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                "start_percent": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "end_percent": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001}),
            },
            "optional": {"vae": ("VAE",)},
        }
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("positive", "negative")
    FUNCTION = "apply_controlnet"
    CATEGORY = "conditioning/controlnet"

    def apply_controlnet(self, positive, negative, control_net, image, strength, start_percent, end_percent, vae=None):
        raise NotImplementedError("ControlNetApplyAdvanced requires full ComfyUI runtime")


class ImageUpscaleWithModel:
    """Built-in ComfyUI node: upscale image with an upscale model."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"upscale_model": ("UPSCALE_MODEL",), "image": ("IMAGE",)}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"
    CATEGORY = "image/upscaling"

    def upscale(self, upscale_model, image):
        raise NotImplementedError("ImageUpscaleWithModel requires full ComfyUI runtime")


class UpscaleModelLoader:
    """Built-in ComfyUI node: load an upscale model."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_name": ([], )}}
    RETURN_TYPES = ("UPSCALE_MODEL",)
    FUNCTION = "load_model"
    CATEGORY = "loaders"

    def load_model(self, model_name):
        raise NotImplementedError("UpscaleModelLoader requires full ComfyUI runtime")


class ControlNetLoaderAdvanced:
    """Advanced ControlNet loader (alias for ControlNetLoader)."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"control_net_name": ([], )}}
    RETURN_TYPES = ("CONTROL_NET",)
    FUNCTION = "load_controlnet"
    CATEGORY = "loaders"

    def load_controlnet(self, control_net_name):
        raise NotImplementedError("ControlNetLoaderAdvanced requires full ComfyUI runtime")


class ControlNetLoader:
    """Core ComfyUI node: load a ControlNet model from a file."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"control_net_name": ("STRING",)}}
    RETURN_TYPES = ("CONTROL_NET",)
    FUNCTION = "load_controlnet"
    CATEGORY = "loaders"

    def load_controlnet(self, control_net_name, **kw):
        raise NotImplementedError("ControlNetLoader requires full ComfyUI runtime")


class ImageScaleToTotalPixels:
    """Core ComfyUI node: scale image to a target total pixel count."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "upscale_method": (["nearest-exact", "bilinear", "area", "bicubic", "lanczos"],),
            "megapixels": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0}),
        }}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"
    CATEGORY = "image/upscaling"

    def upscale(self, image, upscale_method="bilinear", megapixels=1.0, **kw):
        import torch
        import torch.nn.functional as F
        if isinstance(image, torch.Tensor):
            if image.ndim == 4:
                _, h, w, c = image.shape
            else:
                h, w = image.shape[-2], image.shape[-1]
            total = megapixels * 1024 * 1024
            scale = (total / (h * w)) ** 0.5
            new_h = max(1, round(h * scale))
            new_w = max(1, round(w * scale))
            if image.ndim == 4:
                img = image.permute(0, 3, 1, 2)
                img = F.interpolate(img, size=(new_h, new_w), mode=upscale_method if upscale_method != "nearest-exact" else "nearest")
                return (img.permute(0, 2, 3, 1),)
            return (F.interpolate(image.unsqueeze(0), size=(new_h, new_w), mode="bilinear").squeeze(0),)
        return (image,)


for _cls in (ControlNetApplyAdvanced, ImageUpscaleWithModel, UpscaleModelLoader,
             ControlNetLoaderAdvanced, ControlNetLoader, ImageScaleToTotalPixels):
    _name = _cls.__name__
    if _name not in NODE_CLASS_MAPPINGS:
        NODE_CLASS_MAPPINGS[_name] = _cls
        NODE_DISPLAY_NAME_MAPPINGS[_name] = _name


def _register_legacy_aliases():
    """Map deprecated node names to their current equivalents."""
    _ALIASES = {
        "IPAdapterApply": "IPAdapter",
    }
    for old_name, new_name in _ALIASES.items():
        if old_name not in NODE_CLASS_MAPPINGS and new_name in NODE_CLASS_MAPPINGS:
            NODE_CLASS_MAPPINGS[old_name] = NODE_CLASS_MAPPINGS[new_name]
            NODE_DISPLAY_NAME_MAPPINGS[old_name] = old_name


def interrupt_processing(value: bool = True):
    try:
        from comfy.model_management import interrupt_current_processing
        interrupt_current_processing(value)
    except ImportError:
        pass


def before_node_execution():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
        throw_exception_if_processing_interrupted()
    except ImportError:
        pass


class _StubKSampler:
    """Stub common_ksampler for nodes that reference it."""
    @staticmethod
    def sample(*args, **kwargs):
        raise NotImplementedError("common_ksampler requires Ghost's native engine")


def common_ksampler(model, seed, steps, cfg, sampler_name, scheduler,
                    positive, negative, latent, denoise=1.0,
                    disable_noise=False, start_step=None, last_step=None,
                    force_full_denoise=False):
    raise NotImplementedError(
        "nodes.common_ksampler requires full ComfyUI runtime. "
        "Ghost's native KSampler handles this."
    )
