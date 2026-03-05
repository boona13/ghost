"""Ghost compat: comfy.patcher_extension — callback/wrapper stubs."""

from enum import Enum


class CallbacksMP(str, Enum):
    ON_LOAD = "on_load"
    ON_CLONE = "on_clone"
    ON_CLEANUP = "on_cleanup"
    ON_PREPARE_STATE = "on_prepare_state"
    ON_APPLY_HOOKS = "on_apply_hooks"
    ON_REGISTER_HOOKS = "on_register_hooks"
    ON_PRE_RUN = "on_pre_run"
    ON_INFERENCE_BEGIN = "on_inference_begin"
    ON_INFERENCE_END = "on_inference_end"


class WrappersMP(str, Enum):
    OUTER_SAMPLE = "outer_sample"
    SAMPLER_SAMPLE = "sampler_sample"
    CALC_COND = "calc_cond"
    APPLY_MODEL = "apply_model"
    DIFFUSION_MODEL = "diffusion_model"


def add_callback(model_options, callback_type, callback):
    callbacks = model_options.setdefault("callbacks", {})
    callbacks.setdefault(callback_type, []).append(callback)


def add_wrapper(model_options, wrapper_type, wrapper):
    wrappers = model_options.setdefault("wrappers", {})
    wrappers.setdefault(wrapper_type, []).append(wrapper)


def add_wrapper_with_key(model_options, wrapper_type, key, wrapper):
    wrappers = model_options.setdefault("wrappers", {})
    wrappers.setdefault(wrapper_type, {})[key] = wrapper


def add_callback_with_key(model_options, callback_type, key, callback):
    callbacks = model_options.setdefault("callbacks", {})
    callbacks.setdefault(callback_type, {})[key] = callback


class PatcherInjection:
    def __init__(self, inject, eject):
        self.inject = inject
        self.eject = eject


class WrapperExecutor:
    """Executor that runs through a chain of wrappers."""
    def __init__(self, *args, **kwargs):
        self.class_obj = None

    def execute(self, *args, **kwargs):
        if self.class_obj:
            return self.class_obj(*args, **kwargs)
        return None

    @classmethod
    def new_executor(cls, func, wrappers=None, *args, **kwargs):
        executor = cls()
        executor.class_obj = func
        return executor
