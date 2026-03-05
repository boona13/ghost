"""
Ghost compat: comfy.model_sampling — sampling schedule stubs.
"""

import math


class ModelSamplingDiscrete:
    """Base discrete model sampling schedule."""
    def __init__(self, model_config=None):
        self.num_timesteps = 1000
        self.linear_start = 0.00085
        self.linear_end = 0.012

    def timestep(self, sigma):
        return sigma

    def sigma(self, timestep):
        return timestep

    def percent_to_sigma(self, percent):
        return 1.0 - percent


class ModelSamplingContinuousEDM(ModelSamplingDiscrete):
    pass


class ModelSamplingContinuousV(ModelSamplingDiscrete):
    pass


class ModelSamplingFlux(ModelSamplingDiscrete):
    pass


class CONST:
    """Constant velocity sampling schedule (used by Flux/SD3)."""

    def calculate_denoised(self, sigma, model_output, model_input):
        return model_input - model_output * sigma

    def noise_scaling(self, sigma, noise, latent_image, max_denoise=False):
        return sigma * noise + (1.0 - sigma) * latent_image

    def calculate_input(self, sigma, noise):
        return noise

    def timestep(self, sigma):
        return sigma

    def sigma(self, timestep):
        return timestep

    def percent_to_sigma(self, percent):
        return 1.0 - percent


class EPS:
    """Epsilon prediction schedule (SD 1.x / SDXL)."""

    def calculate_denoised(self, sigma, model_output, model_input):
        return model_input - model_output * sigma

    def noise_scaling(self, sigma, noise, latent_image, max_denoise=False):
        if max_denoise:
            return noise * sigma
        return noise * sigma + latent_image

    def calculate_input(self, sigma, noise):
        return noise

    def timestep(self, sigma):
        return sigma

    def sigma(self, timestep):
        return timestep


class V_PREDICTION(EPS):
    """V-prediction schedule."""
    pass


def time_snr_shift(alpha, t):
    if alpha == 1.0:
        return t
    return alpha * t / (1.0 + (alpha - 1.0) * t)
