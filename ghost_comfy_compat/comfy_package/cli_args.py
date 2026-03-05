"""
Ghost compat: comfy.cli_args — args Namespace with sensible defaults.
"""

import argparse
from enum import Enum


class LatentPreviewMethod(Enum):
    NoPreviews = "none"
    Auto = "auto"
    Latent2RGB = "latent2rgb"
    TAESD = "taesd"


class PerformanceFeature(Enum):
    fp8_attention = "fp8_attention"
    fp16_accumulation = "fp16_accumulation"


args = argparse.Namespace(
    cpu=False,
    gpu_only=False,
    highvram=False,
    normalvram=True,
    lowvram=False,
    novram=False,
    fp16_unet=False,
    fp16_vae=False,
    bf16_unet=False,
    bf16_vae=False,
    fp32_unet=False,
    fp32_vae=False,
    force_fp16=False,
    force_fp32=False,
    disable_xformers=False,
    use_pytorch_cross_attention=True,
    use_split_cross_attention=False,
    use_quad_cross_attention=False,
    preview_method=LatentPreviewMethod.NoPreviews,
    disable_smart_memory=False,
    disable_metadata=False,
    output_directory=None,
    input_directory=None,
    temp_directory=None,
    deterministic=False,
    dont_print_server=True,
    quick_test_for_ci=False,
    windows_standalone_build=False,
    disable_auto_launch=True,
    multi_user=False,
    listen="127.0.0.1",
    port=8188,
    enable_cors_header=None,
    max_upload_size=100,
    extra_model_paths_config=None,
    cuda_device=None,
    cuda_malloc=False,
    fast=set(),
    mmap_torch_files=False,
    disable_mmap=False,
)
