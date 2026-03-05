"""
Ghost compat: comfy.clip_vision — ClipVisionModel stub.

IPAdapter and other custom nodes import this to check clip vision model types
and call load/encode methods. The class stubs allow import-time registration;
actual inference requires the full ComfyUI runtime.
"""


class Output:
    """Container for CLIP vision encoder outputs."""
    def __init__(self, *args, **kwargs):
        self.last_hidden_state = None
        self.image_embeds = None
        self.penultimate_hidden_states = None


def clip_preprocess(image, size=224):
    """Preprocess image for CLIP vision — resize and normalize.
    
    Returns a tensor compatible with CLIP vision models.
    Tries torchvision first, falls back to manual resize+normalize.
    """
    import torch
    import torch.nn.functional as F

    if isinstance(image, torch.Tensor):
        if image.ndim == 3:
            image = image.unsqueeze(0)
        if image.shape[-1] in (3, 4):
            image = image.permute(0, 3, 1, 2)
        image = F.interpolate(image[:, :3], size=(size, size), mode="bicubic", align_corners=False)
        mean = torch.tensor([0.48145466, 0.4578275, 0.40821073], device=image.device).view(1, 3, 1, 1)
        std = torch.tensor([0.26862954, 0.26130258, 0.27577711], device=image.device).view(1, 3, 1, 1)
        image = (image - mean) / std
        return image
    raise NotImplementedError("clip_preprocess requires a torch.Tensor input")


class ClipVisionModel:
    """Stub for comfy.clip_vision.ClipVisionModel."""
    def __init__(self, *args, **kwargs):
        self.model = None
        self.patcher = None
        self.dtype = None
        self.device = None

    def encode_image(self, image):
        raise NotImplementedError("ClipVisionModel.encode_image requires full ComfyUI runtime")

    def get_sd(self):
        return {}

    def load_model(self):
        return self


def load(ckpt_path):
    raise NotImplementedError("comfy.clip_vision.load requires full ComfyUI runtime")


def load_clipvision_from_sd(sd, prefix="", convert_keys=True):
    raise NotImplementedError("comfy.clip_vision.load_clipvision_from_sd requires full ComfyUI runtime")
