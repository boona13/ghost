"""
Ghost compat: comfy.model_patcher — ModelPatcher with patch registration.

The patch registration methods (clone, add_patches, set_model_*) are real
dict-based implementations. The actual model loading/patching is stubbed.
"""

import copy
import logging

from ghost_comfy_compat.comfy_package.patcher_extension import PatcherInjection

log = logging.getLogger("ghost.comfy_compat.model_patcher")


class ModelPatcher:
    def __init__(self, model=None, load_device=None, offload_device=None,
                 size: int = 0, weight_inplace_update: bool = False):
        self.model = model
        self.load_device = load_device
        self.offload_device = offload_device
        self.size = size
        self.weight_inplace_update = weight_inplace_update

        self.patches: dict = {}
        self.backup: dict = {}
        self.object_patches: dict = {}
        self.model_options: dict = {"transformer_options": {}}
        self.model_keys = set()
        self.patches_uuid = set()
        self.parent = None
        self.current_device = offload_device
        self.is_patched = False

    def clone(self):
        n = ModelPatcher.__new__(ModelPatcher)
        n.model = self.model
        n.load_device = self.load_device
        n.offload_device = self.offload_device
        n.size = self.size
        n.weight_inplace_update = self.weight_inplace_update
        n.patches = {}
        for k, v in self.patches.items():
            n.patches[k] = list(v)
        n.backup = {}
        n.object_patches = dict(self.object_patches)
        n.model_options = copy.deepcopy(self.model_options)
        n.model_keys = set(self.model_keys)
        n.patches_uuid = set(self.patches_uuid)
        n.parent = self
        n.current_device = self.current_device
        n.is_patched = False
        return n

    def is_clone(self, other) -> bool:
        if self is other:
            return True
        if self.model is other.model:
            return True
        return False

    def add_patches(self, patches: dict, strength_patch: float = 1.0,
                    strength_model: float = 1.0) -> list:
        applied = []
        for key, v in patches.items():
            if key in self.model_keys or True:
                current = self.patches.get(key, [])
                current.append((strength_patch, v, strength_model))
                self.patches[key] = current
                applied.append(key)
        return applied

    def get_key_patches(self, filter_prefix: str | None = None) -> dict:
        model_sd = self.model_state_dict(filter_prefix)
        result = {}
        for key in model_sd:
            if key in self.patches:
                result[key] = self.patches[key]
        return result

    def model_state_dict(self, filter_prefix: str | None = None) -> dict:
        if self.model is None:
            return {}
        try:
            sd = self.model.state_dict()
            if filter_prefix:
                sd = {k: v for k, v in sd.items() if k.startswith(filter_prefix)}
            return sd
        except Exception:
            return {}

    def model_dtype(self):
        if self.model is not None:
            try:
                p = next(self.model.parameters())
                return p.dtype
            except (StopIteration, AttributeError):
                pass
        try:
            import torch
            return torch.float32
        except ImportError:
            return None

    def model_size(self) -> int:
        if self.model is None:
            return self.size
        try:
            from comfy.model_management import module_size
            return module_size(self.model)
        except (ImportError, AttributeError):
            return self.size

    def set_model_patch(self, patch, name: str):
        to = self.model_options["transformer_options"]
        if "patches" not in to:
            to["patches"] = {}
        to["patches"][name] = to["patches"].get(name, []) + [patch]

    def set_model_patch_replace(self, patch, name: str, block_name: str,
                                number: int, transformer_index=None):
        to = self.model_options["transformer_options"]
        if "patches_replace" not in to:
            to["patches_replace"] = {}
        if name not in to["patches_replace"]:
            to["patches_replace"][name] = {}

        key = (block_name, number)
        if transformer_index is not None:
            key = (block_name, number, transformer_index)
        to["patches_replace"][name][key] = patch

    def set_model_attn1_patch(self, patch):
        self.set_model_patch(patch, "attn1_patch")

    def set_model_attn2_patch(self, patch):
        self.set_model_patch(patch, "attn2_patch")

    def set_model_attn1_replace(self, patch, block_name, number, transformer_index=None):
        self.set_model_patch_replace(patch, "attn1", block_name, number, transformer_index)

    def set_model_attn2_replace(self, patch, block_name, number, transformer_index=None):
        self.set_model_patch_replace(patch, "attn2", block_name, number, transformer_index)

    def set_model_attn1_output_patch(self, patch):
        self.set_model_patch(patch, "attn1_output_patch")

    def set_model_attn2_output_patch(self, patch):
        self.set_model_patch(patch, "attn2_output_patch")

    def set_model_sampler_cfg_function(self, sampler_cfg_function, disable_cfg1_optimization=False):
        if disable_cfg1_optimization:
            self.model_options["disable_cfg1_optimization"] = True
        self.model_options["sampler_cfg_function"] = sampler_cfg_function

    def set_model_sampler_post_cfg_function(self, post_cfg_function, disable_cfg1_optimization=False):
        self.model_options.setdefault("sampler_post_cfg_function", []).append(post_cfg_function)
        if disable_cfg1_optimization:
            self.model_options["disable_cfg1_optimization"] = True

    def set_model_unet_function_wrapper(self, unet_wrapper_function):
        self.model_options["model_function_wrapper"] = unet_wrapper_function

    def add_object_patch(self, name: str, obj):
        self.object_patches[name] = obj

    def get_model_object(self, name: str):
        if name in self.object_patches:
            return self.object_patches[name]
        if self.model is not None:
            return getattr(self.model, name, None)
        return None

    def patch_model(self, device_to=None, lowvram_model_memory=0, load_weights=True, force_patch_weights=False):
        log.debug("ModelPatcher.patch_model called (compat stub)")
        self.is_patched = True
        return self.model

    def unpatch_model(self, device_to=None, unpatch_weights=True):
        log.debug("ModelPatcher.unpatch_model called (compat stub)")
        self.is_patched = False

    def load(self, device_to=None, lowvram_model_memory=0, force_patch_weights=False, full_load=False):
        log.debug("ModelPatcher.load called (compat stub)")


CoreModelPatcher = ModelPatcher
