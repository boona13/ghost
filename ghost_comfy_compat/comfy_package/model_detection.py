"""
Ghost compat: comfy.model_detection — model architecture detection stubs.
"""


def count_blocks(state_dict_keys, prefix_string):
    """Count the number of blocks with a given prefix in state dict keys."""
    count = 0
    while True:
        c = False
        for k in state_dict_keys:
            if k.startswith(prefix_string.format(count)):
                c = True
                break
        if c:
            count += 1
        else:
            break
    return count


def detect_unet_config(state_dict, key_prefix, dtype=None):
    """Detect the configuration of a UNet model from its state dict."""
    return {}


def model_config_from_unet_config(unet_config, state_dict=None):
    return None


def model_config_from_unet(state_dict, unet_key_prefix, dtype=None):
    return None


def unet_config_from_diffusers_unet(state_dict, dtype=None):
    return {}


def convert_diffusers_mmdit(state_dict, output_prefix=""):
    return state_dict
