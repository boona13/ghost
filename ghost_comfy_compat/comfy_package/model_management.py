"""
Ghost compat: comfy.model_management — real device detection and memory queries.
"""

import logging
import os
import platform
from enum import Enum

log = logging.getLogger("ghost.comfy_compat.model_management")


class VRAMState(Enum):
    DISABLED = 0
    NO_VRAM = 1
    LOW_VRAM = 2
    NORMAL_VRAM = 3
    HIGH_VRAM = 4
    SHARED = 5


class CPUState(Enum):
    GPU = 0
    CPU = 1
    MPS = 2
    XPU = 3
    DIRECTML = 4


class InterruptProcessingException(Exception):
    pass


_interrupt_flag = False
processing_interrupted = False

vram_state = VRAMState.NORMAL_VRAM
cpu_state = CPUState.CPU
total_vram = 0
XFORMERS_IS_AVAILABLE = False
XFORMERS_ENABLED_VAE = False
ENABLE_PYTORCH_ATTENTION = True

try:
    import torch
    OOM_EXCEPTION = torch.cuda.OutOfMemoryError if hasattr(torch.cuda, "OutOfMemoryError") else RuntimeError
except ImportError:
    OOM_EXCEPTION = RuntimeError


def _detect_device():
    global cpu_state, total_vram, XFORMERS_IS_AVAILABLE
    try:
        import torch
        if torch.cuda.is_available():
            cpu_state = CPUState.GPU
            try:
                total_vram = torch.cuda.get_device_properties(0).total_mem / (1024 ** 2)
            except Exception:
                total_vram = 0
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            cpu_state = CPUState.MPS
        else:
            cpu_state = CPUState.CPU
    except ImportError:
        cpu_state = CPUState.CPU

    try:
        import xformers  # noqa: F401
        import xformers.ops  # noqa: F401
        XFORMERS_IS_AVAILABLE = True
    except ImportError:
        XFORMERS_IS_AVAILABLE = False


_detect_device()


def get_torch_device():
    try:
        import torch
        if cpu_state == CPUState.GPU:
            return torch.device("cuda")
        if cpu_state == CPUState.MPS:
            return torch.device("mps")
        return torch.device("cpu")
    except ImportError:
        class _FakeDevice:
            type = "cpu"
            def __str__(self): return "cpu"
            def __repr__(self): return "device(type='cpu')"
        return _FakeDevice()


def unet_offload_device():
    try:
        import torch
        return torch.device("cpu")
    except ImportError:
        return get_torch_device()


def intermediate_device():
    try:
        import torch
        return torch.device("cpu")
    except ImportError:
        return get_torch_device()


def vae_offload_device():
    try:
        import torch
        return torch.device("cpu")
    except ImportError:
        return get_torch_device()


def vae_device():
    return get_torch_device()


def text_encoder_device():
    return get_torch_device()


def text_encoder_offload_device():
    try:
        import torch
        return torch.device("cpu")
    except ImportError:
        return get_torch_device()


def text_encoder_dtype(device=None):
    if should_use_fp16(device):
        try:
            import torch
            return torch.float16
        except ImportError:
            pass
    try:
        import torch
        return torch.float32
    except ImportError:
        return None


def get_free_memory(dev=None, torch_free_too: bool = False):
    try:
        import torch
        if dev is None:
            dev = get_torch_device()
        if hasattr(dev, "type") and dev.type == "cuda":
            free, total = torch.cuda.mem_get_info(dev)
            if torch_free_too:
                return free, torch.cuda.memory_reserved(dev) - torch.cuda.memory_allocated(dev)
            return free
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.available
        except ImportError:
            return 8 * 1024 * 1024 * 1024
    except ImportError:
        return 8 * 1024 * 1024 * 1024


def get_total_memory(dev=None, torch_total_too: bool = False):
    try:
        import torch
        if dev is None:
            dev = get_torch_device()
        if hasattr(dev, "type") and dev.type == "cuda":
            _, total = torch.cuda.mem_get_info(dev)
            return total
        try:
            import psutil
            return psutil.virtual_memory().total
        except ImportError:
            return 16 * 1024 * 1024 * 1024
    except ImportError:
        return 16 * 1024 * 1024 * 1024


def soft_empty_cache(force: bool = False):
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except (ImportError, AttributeError):
        pass


def unload_all_models():
    soft_empty_cache(force=True)


def load_models_gpu(models, memory_required=0, force_patch_weights=False, minimum_memory_required=None, force_full_load=False):
    pass


def free_memory(memory_required, device, keep_loaded=None):
    soft_empty_cache()


def xformers_enabled():
    return XFORMERS_IS_AVAILABLE


def xformers_enabled_vae():
    return XFORMERS_ENABLED_VAE


def pytorch_attention_enabled():
    return True


def pytorch_attention_flash_attention():
    return False


def should_use_fp16(device=None, model_params: int = 0, prioritize_performance: bool = True, manual_cast: bool = False):
    try:
        import torch
        if device is None:
            device = get_torch_device()
        if hasattr(device, "type"):
            if device.type == "cpu":
                return False
            if device.type == "mps":
                return True
            if device.type == "cuda":
                props = torch.cuda.get_device_properties(device)
                if props.major >= 7:
                    return True
                if props.major >= 6:
                    return True
        return False
    except (ImportError, RuntimeError):
        return False


def should_use_bf16(device=None, model_params: int = 0, prioritize_performance: bool = True, manual_cast: bool = False):
    try:
        import torch
        if device is None:
            device = get_torch_device()
        if hasattr(device, "type") and device.type == "cuda":
            props = torch.cuda.get_device_properties(device)
            if props.major >= 8:
                return True
        return False
    except (ImportError, RuntimeError):
        return False


def is_device_cpu(device) -> bool:
    return hasattr(device, "type") and device.type == "cpu"


def is_device_mps(device) -> bool:
    return hasattr(device, "type") and device.type == "mps"


def is_device_cuda(device) -> bool:
    return hasattr(device, "type") and device.type == "cuda"


def unet_dtype(device=None, model_params: int = 0, supported_dtypes=None):
    try:
        import torch
        if should_use_fp16(device, model_params):
            return torch.float16
        return torch.float32
    except ImportError:
        return None


def vae_dtype(device=None, allowed_dtypes=None):
    try:
        import torch
        if should_use_bf16(device):
            return torch.bfloat16
        return torch.float32
    except ImportError:
        return None


def cast_to_device(tensor, device, dtype, copy: bool = False):
    if copy:
        return tensor.clone().to(device, dtype=dtype)
    return tensor.to(device, dtype=dtype)


def module_size(module) -> int:
    total = 0
    for p in module.parameters():
        total += p.numel() * p.element_size()
    for b in module.buffers():
        total += b.numel() * b.element_size()
    return total


def dtype_size(dtype) -> int:
    try:
        import torch
        return torch.tensor([], dtype=dtype).element_size()
    except (ImportError, RuntimeError):
        return 4


def supports_cast(device, dtype) -> bool:
    try:
        import torch
        t = torch.zeros(1, dtype=dtype, device=device)
        return True
    except Exception:
        return False


def interrupt_current_processing(value: bool = True):
    global _interrupt_flag, processing_interrupted
    _interrupt_flag = value
    processing_interrupted = value


def throw_exception_if_processing_interrupted():
    if _interrupt_flag:
        raise InterruptProcessingException()


def unet_manual_cast(weight_dtype, inference_device, supported_dtypes=None):
    return None


def force_channels_last():
    return False


def device_supports_non_blocking(device):
    return False
