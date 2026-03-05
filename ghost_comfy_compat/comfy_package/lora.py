"""Ghost compat: comfy.lora — LoRA loading stubs."""


def model_lora_keys_unet(model, key_map=None):
    if key_map is None:
        key_map = {}
    return key_map


def model_lora_keys_clip(model, key_map=None):
    if key_map is None:
        key_map = {}
    return key_map


def load_lora(lora, to_load):
    return {}
