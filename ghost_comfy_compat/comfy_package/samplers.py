"""
Ghost compat: comfy.samplers — sampler/scheduler name lists and class stubs.

The name lists are used at import time in INPUT_TYPES for dropdown menus.
The actual sampling functions are stubs — Ghost's native engine handles sampling.
"""

KSAMPLER_NAMES = [
    "euler", "euler_cfg_pp", "euler_ancestral", "euler_ancestral_cfg_pp",
    "heun", "heunpp2", "dpm_2", "dpm_2_ancestral",
    "lms", "dpm_fast", "dpm_adaptive",
    "dpmpp_2s_ancestral", "dpmpp_2s_ancestral_cfg_pp",
    "dpmpp_sde", "dpmpp_sde_gpu",
    "dpmpp_2m", "dpmpp_2m_cfg_pp",
    "dpmpp_2m_sde", "dpmpp_2m_sde_gpu",
    "dpmpp_3m_sde", "dpmpp_3m_sde_gpu",
    "ddpm", "lcm", "ipndm", "ipndm_v2", "deis",
    "res_momentumpc",
]

SAMPLER_NAMES = KSAMPLER_NAMES + ["ddim", "uni_pc", "uni_pc_bh2"]

SCHEDULER_NAMES = [
    "normal", "karras", "exponential", "sgm_uniform",
    "simple", "ddim_uniform", "beta", "linear_quadratic", "kl_optimal",
]


class Sampler:
    """Base sampler class stub."""
    SAMPLERS = KSAMPLER_NAMES
    SCHEDULERS = SCHEDULER_NAMES

    def sample(self, *args, **kwargs):
        raise NotImplementedError("Sampler.sample requires full ComfyUI runtime")

    def max_denoise(self, model_wrap, sigmas):
        return True


class KSAMPLER(Sampler):
    """K-diffusion sampler stub."""
    def __init__(self, sampler_function=None, extra_options=None, inpaint_options=None):
        self.sampler_function = sampler_function
        self.extra_options = extra_options or {}
        self.inpaint_options = inpaint_options or {}


class CFGGuider:
    """Classifier-free guidance stub."""
    def __init__(self, model_patcher=None):
        self.model_patcher = model_patcher
        self.conds = {}
        self.cfg = 1.0

    def set_conds(self, positive=None, negative=None):
        if positive is not None:
            self.conds["positive"] = positive
        if negative is not None:
            self.conds["negative"] = negative

    def set_cfg(self, cfg):
        self.cfg = cfg

    def sample(self, *args, **kwargs):
        raise NotImplementedError("CFGGuider.sample requires full ComfyUI runtime")

    def __call__(self, *args, **kwargs):
        return self.sample(*args, **kwargs)


class KSampler:
    """ComfyUI KSampler class — provides SAMPLERS/SCHEDULERS for INPUT_TYPES dropdowns."""
    SAMPLERS = KSAMPLER_NAMES
    SCHEDULERS = SCHEDULER_NAMES

    def __init__(self, model, steps, device, sampler=None, scheduler=None,
                 denoise=None, model_options=None):
        self.model = model
        self.steps = steps
        self.device = device
        self.sampler_name = sampler
        self.scheduler = scheduler
        self.denoise = denoise

    def sample(self, noise, positive, negative, cfg, latent_image=None,
               start_step=None, last_step=None, force_full_denoise=False,
               denoise_mask=None, sigmas=None, callback=None, disable_pbar=False,
               seed=None):
        raise NotImplementedError("KSampler.sample requires full ComfyUI runtime")


def sampler_object(name: str):
    return KSAMPLER()


def ksampler(sampler_name: str, extra_options=None, inpaint_options=None):
    return KSAMPLER(extra_options=extra_options, inpaint_options=inpaint_options)


def sample(*args, **kwargs):
    raise NotImplementedError("comfy.samplers.sample requires full ComfyUI runtime")


def sampling_function(model, x, timestep, uncond, cond, cond_scale, model_options=None, seed=None):
    raise NotImplementedError("sampling_function requires full ComfyUI runtime")


def calculate_sigmas(model_sampling, scheduler_name, steps):
    raise NotImplementedError("calculate_sigmas requires full ComfyUI runtime")


def resolve_areas_and_cond_masks(conditions, h, w, device):
    return conditions
