"""
Ghost compat: comfy.sd — enums and class stubs for model types.

CLIPType/TEModel enums are real. CLIP/VAE are stubs sufficient for
isinstance checks and type annotations. Load functions raise NotImplementedError.
"""

from enum import Enum


class CLIPType(Enum):
    STABLE_DIFFUSION = 1
    STABLE_CASCADE = 2
    SD3 = 3
    STABLE_AUDIO = 4
    HUNYUAN_DIT = 5
    FLUX = 6
    MOCHI = 7
    LTXV = 8
    HUNYUAN_VIDEO = 9
    PIXART = 10
    WAN = 11
    LUMINA2 = 12
    COSMOS = 13
    ACE = 14


class TEModel(Enum):
    CLIP_L = 1
    CLIP_G = 2
    T5_XXL = 3
    T5_XL = 4
    T5_BASE = 5
    LLAMA3_8 = 6
    GEMMA2_2B = 7
    HYDIT1_CLIP = 8


class CLIP:
    """Stub CLIP wrapper — enough for isinstance/type checks at import time."""
    def __init__(self, *args, **kwargs):
        self.cond_stage_model = None
        self.tokenizer = None
        self.patcher = None
        self.layer_idx = None

    def clone(self):
        return CLIP()

    def load_model(self):
        return self

    def encode_from_tokens(self, tokens, return_pooled=False, return_dict=False):
        raise NotImplementedError("CLIP.encode_from_tokens requires full ComfyUI runtime")

    def tokenize(self, text, return_word_ids=False):
        raise NotImplementedError("CLIP.tokenize requires full ComfyUI runtime")

    def get_sd(self):
        return {}


class VAE:
    """Stub VAE wrapper — enough for isinstance/type checks at import time."""
    def __init__(self, *args, **kwargs):
        self.first_stage_model = None
        self.patcher = None
        self.memory_used_encode = lambda *a, **k: 0
        self.memory_used_decode = lambda *a, **k: 0

    def clone(self):
        return VAE()

    def decode(self, samples_in):
        raise NotImplementedError("VAE.decode requires full ComfyUI runtime")

    def encode(self, pixel_samples):
        raise NotImplementedError("VAE.encode requires full ComfyUI runtime")

    def decode_tiled(self, samples, tile_x=64, tile_y=64, overlap=16):
        raise NotImplementedError("VAE.decode_tiled requires full ComfyUI runtime")

    def encode_tiled(self, pixel_samples, tile_x=512, tile_y=512, overlap=64):
        raise NotImplementedError("VAE.encode_tiled requires full ComfyUI runtime")

    def get_sd(self):
        return {}


def load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True,
                                  output_clipvision=False, embedding_directory=None,
                                  output_model=True):
    raise NotImplementedError(
        "comfy.sd.load_checkpoint_guess_config requires full ComfyUI runtime. "
        "Ghost's native engine handles checkpoint loading via diffusers."
    )


def load_state_dict_guess_config(sd, output_vae=True, output_clip=True,
                                  output_clipvision=False, embedding_directory=None,
                                  output_model=True):
    raise NotImplementedError("comfy.sd.load_state_dict_guess_config requires full ComfyUI runtime")


def load_diffusion_model(unet_path, model_options=None):
    raise NotImplementedError("comfy.sd.load_diffusion_model requires full ComfyUI runtime")


def load_diffusion_model_state_dict(sd, model_options=None):
    raise NotImplementedError("comfy.sd.load_diffusion_model_state_dict requires full ComfyUI runtime")


def load_lora_for_models(model, clip, lora, strength_model, strength_clip, filename=""):
    raise NotImplementedError("comfy.sd.load_lora_for_models requires full ComfyUI runtime")


def load_clip(ckpt_paths, embedding_directory=None, clip_type=CLIPType.STABLE_DIFFUSION,
              model_options=None):
    raise NotImplementedError("comfy.sd.load_clip requires full ComfyUI runtime")


def load_style_model(ckpt_path):
    raise NotImplementedError("comfy.sd.load_style_model requires full ComfyUI runtime")


def load_gligen(ckpt_path):
    raise NotImplementedError("comfy.sd.load_gligen requires full ComfyUI runtime")
