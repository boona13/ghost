"""Ghost compat: comfy.k_diffusion.sampling — stubs."""


def to_d(x, sigma, denoised):
    return (x - denoised) / sigma.reshape(-1, *([1] * (len(x.shape) - 1)))


def get_ancestral_step(sigma_from, sigma_to, eta=1.0):
    import math
    if not eta:
        return sigma_to, 0.0
    sigma_up = min(sigma_to, eta * (sigma_to ** 2 * (sigma_from ** 2 - sigma_to ** 2) /
                                     sigma_from ** 2) ** 0.5)
    sigma_down = (sigma_to ** 2 - sigma_up ** 2) ** 0.5
    return sigma_down, sigma_up


def default_noise_sampler(x):
    import torch
    def noise_sampler(sigma, sigma_next):
        return torch.randn_like(x)
    return noise_sampler
