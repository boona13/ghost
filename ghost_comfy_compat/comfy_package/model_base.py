"""
Ghost compat: comfy.model_base — ModelType enum and base model stubs.

Provides all model type classes that custom nodes (AnimateDiff-Evolved,
IPAdapter, etc.) reference at import time for isinstance checks and
INPUT_TYPES declarations.
"""

from enum import Enum


class ModelType(Enum):
    EPS = 1
    V_PREDICTION = 2
    V_PREDICTION_EDM = 3
    STABLE_CASCADE = 4
    EDM = 5
    FLOW = 6
    V_PREDICTION_CONTINUOUS = 7
    FLUX = 8
    VELOCITY = 9


class BaseModel:
    def __init__(self, *args, **kwargs):
        self.model_type = ModelType.EPS
        self.model_config = None
        self.latent_format = None
        self.manual_cast_dtype = None
        self.model_sampling = None
        self.adm_channels = 0
        self.inpaint_model = False
        self.model = None
        self.diffusion_model = None

    def apply_model(self, *args, **kwargs):
        raise NotImplementedError("BaseModel.apply_model requires full ComfyUI runtime")

    def process_latent_in(self, latent):
        return latent

    def process_latent_out(self, latent):
        return latent


class BASE(BaseModel):
    pass


class SD15(BaseModel):
    pass


class SD20(BaseModel):
    pass


class SD21UNCLIP(BaseModel):
    pass


class SDXLRefiner(BaseModel):
    pass


class SDXL(BaseModel):
    pass


class SVD_img2vid(BaseModel):
    pass


class Stable_Zero123(BaseModel):
    pass


class SD_X4Upscaler(BaseModel):
    pass


class StableCascade_C(BaseModel):
    pass


class StableCascade_B(BaseModel):
    pass


class SV3D_u(BaseModel):
    pass


class SV3D_p(BaseModel):
    pass


class Flux(BaseModel):
    pass


class GenmoMochi(BaseModel):
    pass


class LTXV(BaseModel):
    pass


class HunyuanVideo(BaseModel):
    pass


class CosmosVideo(BaseModel):
    pass


class WAN21(BaseModel):
    pass


# Re-export comfy.model_sampling so `from comfy.model_base import model_sampling` works
try:
    from ghost_comfy_compat.comfy_package import model_sampling
except ImportError:
    import types as _types
    model_sampling = _types.ModuleType("comfy.model_sampling")
