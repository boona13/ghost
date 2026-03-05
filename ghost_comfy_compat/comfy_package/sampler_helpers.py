"""Ghost compat: comfy.sampler_helpers — stubs."""


def prepare_mask(noise_mask, shape, device):
    import torch
    import torch.nn.functional as F
    if noise_mask is None:
        return None
    if len(noise_mask.shape) == 2:
        noise_mask = noise_mask.unsqueeze(0)
    if len(noise_mask.shape) == 3:
        noise_mask = noise_mask.unsqueeze(1)
    if noise_mask.shape[-2:] != shape[-2:]:
        noise_mask = F.interpolate(noise_mask.float(), size=shape[-2:],
                                   mode="bilinear", align_corners=False)
    noise_mask = noise_mask.round()
    return noise_mask.to(device)


def get_models_from_cond(cond, model_type):
    return []


def convert_cond(cond):
    return cond
