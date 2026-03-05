"""Ghost compat: comfy.sample — sampling entry point stub."""


def sample(*args, **kwargs):
    raise NotImplementedError("comfy.sample.sample requires full ComfyUI runtime")


def sample_custom(*args, **kwargs):
    raise NotImplementedError("comfy.sample.sample_custom requires full ComfyUI runtime")


def prepare_noise(latent_image, seed, noise_inds=None):
    import torch
    generator = torch.manual_seed(seed)
    return torch.randn(latent_image.size(), dtype=latent_image.dtype,
                       layout=latent_image.layout, generator=generator,
                       device="cpu")
