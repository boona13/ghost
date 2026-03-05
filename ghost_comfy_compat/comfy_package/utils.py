"""
Ghost compat: comfy.utils — real implementations of the most-used utilities.

Provides: common_upscale, ProgressBar, load_torch_file, save_torch_file,
reshape_mask, state_dict_prefix_replace, calculate_parameters, tiled_scale,
bislerp, lanczos, string_to_seed, PROGRESS_BAR_ENABLED, and more.
"""

import logging
import math
import struct
import zlib

log = logging.getLogger("ghost.comfy_compat.utils")

PROGRESS_BAR_ENABLED = True
PROGRESS_BAR_HOOK = None


def string_to_seed(data: str) -> int:
    crc = zlib.crc32(data.encode("utf-8"))
    return crc & 0xFFFFFFFF


def calculate_parameters(sd: dict, prefix: str = "") -> int:
    total = 0
    for k, v in sd.items():
        if k.startswith(prefix):
            total += v.numel()
    return total


def weight_dtype(sd: dict, prefix: str = ""):
    import torch
    dtypes: dict = {}
    for k, v in sd.items():
        if k.startswith(prefix) and isinstance(v, torch.Tensor):
            dt = v.dtype
            dtypes[dt] = dtypes.get(dt, 0) + v.numel()
    if not dtypes:
        return None
    return max(dtypes, key=dtypes.get)


def state_dict_prefix_replace(state_dict: dict, replace_prefix: dict,
                              filter_keys: bool = False) -> dict:
    out = {}
    for k, v in state_dict.items():
        replaced = False
        for prefix_from, prefix_to in replace_prefix.items():
            if k.startswith(prefix_from):
                out[prefix_to + k[len(prefix_from):]] = v
                replaced = True
                break
        if not replaced and not filter_keys:
            out[k] = v
    return out


def clip_text_transformers_convert(sd: dict, prefix_from: str, prefix_to: str) -> dict:
    res = {}
    for k, v in sd.items():
        if k.startswith(prefix_from):
            new_k = prefix_to + k[len(prefix_from):]
            new_k = new_k.replace("mlp.fc1", "mlp.c_fc").replace("mlp.fc2", "mlp.c_proj")
            new_k = new_k.replace(".self_attn.", ".attn.")
            new_k = new_k.replace("layer_norm1", "ln_1").replace("layer_norm2", "ln_2")
            res[new_k] = v
        else:
            res[k] = v
    return res


def common_upscale(samples, width: int, height: int,
                   upscale_method: str = "nearest-exact", crop: str = "disabled"):
    import torch
    import torch.nn.functional as F

    if crop == "center":
        _, _, h, w = samples.shape
        ratio_h = h / height
        ratio_w = w / width
        if ratio_h > ratio_w:
            new_h = int(height * ratio_w)
            offset = (h - new_h) // 2
            samples = samples[:, :, offset:offset + new_h, :]
        elif ratio_w > ratio_h:
            new_w = int(width * ratio_h)
            offset = (w - new_w) // 2
            samples = samples[:, :, :, offset:offset + new_w]

    method_map = {
        "nearest-exact": "nearest-exact",
        "nearest": "nearest",
        "bilinear": "bilinear",
        "bicubic": "bicubic",
        "area": "area",
        "bislerp": "bilinear",
        "lanczos": "bicubic",
    }

    if upscale_method == "bislerp":
        return bislerp(samples, width, height)
    if upscale_method == "lanczos":
        return lanczos(samples, width, height)

    mode = method_map.get(upscale_method, "nearest-exact")
    align = None
    if mode in ("bilinear", "bicubic"):
        align = False

    return F.interpolate(samples, size=(height, width), mode=mode, align_corners=align)


def reshape_mask(mask, shape):
    import torch
    import torch.nn.functional as F

    if len(mask.shape) == 2:
        mask = mask.unsqueeze(0)
    if len(mask.shape) == 3:
        mask = mask.unsqueeze(1)

    target_h, target_w = shape[-2], shape[-1]
    _, _, h, w = mask.shape
    if h != target_h or w != target_w:
        mask = F.interpolate(mask.float(), size=(target_h, target_w), mode="bilinear", align_corners=False)
    return mask


def bislerp(samples, width: int, height: int):
    import torch
    import torch.nn.functional as F

    if samples.shape[-1] == width and samples.shape[-2] == height:
        return samples

    result = F.interpolate(samples.float(), size=(height, width), mode="bilinear", align_corners=False)
    return result.to(samples.dtype)


def lanczos(samples, width: int, height: int):
    try:
        from PIL import Image
        import numpy as np
        import torch

        result = []
        for i in range(samples.shape[0]):
            for c in range(samples.shape[1]):
                channel = samples[i, c].cpu().numpy()
                pil_img = Image.fromarray(channel, mode="F")
                resized = pil_img.resize((width, height), Image.LANCZOS)
                result.append(torch.from_numpy(np.array(resized)))

            result_channels = torch.stack(result[-samples.shape[1]:])
        batch_results = []
        for i in range(samples.shape[0]):
            start = i * samples.shape[1]
            batch_results.append(torch.stack(result[start:start + samples.shape[1]]))

        return torch.stack(batch_results).to(samples.device, dtype=samples.dtype)
    except ImportError:
        return bislerp(samples, width, height)


def get_tiled_scale_steps(width: int, height: int, tile_x: int, tile_y: int,
                          overlap: int) -> int:
    cols = max(1, math.ceil((width - overlap) / (tile_x - overlap)))
    rows = max(1, math.ceil((height - overlap) / (tile_y - overlap)))
    return cols * rows


def tiled_scale(samples, function, tile_x: int = 64, tile_y: int = 64,
                overlap: int = 8, upscale_amount: int = 4, out_channels: int = 3,
                output_device="cpu", pbar=None):
    import torch

    _, channels, height, width = samples.shape
    out_h = height * upscale_amount
    out_w = width * upscale_amount
    output = torch.zeros((samples.shape[0], out_channels, out_h, out_w),
                         device=output_device, dtype=samples.dtype)
    out_div = torch.zeros_like(output)

    for y in range(0, height, tile_y - overlap):
        for x in range(0, width, tile_x - overlap):
            x_end = min(x + tile_x, width)
            y_end = min(y + tile_y, height)
            x_start = max(0, x_end - tile_x)
            y_start = max(0, y_end - tile_y)

            tile = samples[:, :, y_start:y_end, x_start:x_end]
            processed = function(tile)

            oy_start = y_start * upscale_amount
            oy_end = y_end * upscale_amount
            ox_start = x_start * upscale_amount
            ox_end = x_end * upscale_amount

            mask = torch.ones_like(processed)
            output[:, :, oy_start:oy_end, ox_start:ox_end] += processed
            out_div[:, :, oy_start:oy_end, ox_start:ox_end] += mask

            if pbar is not None:
                pbar.update(1)

    output = output / out_div.clamp(min=1e-8)
    return output


def set_attr(obj, attr: str, value):
    parts = attr.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    setattr(obj, parts[-1], value)


def get_attr(obj, attr: str):
    parts = attr.split(".")
    for p in parts:
        obj = getattr(obj, p)
    return obj


def copy_to_param(model, key: str, value):
    import torch
    parts = key.split(".")
    obj = model
    for p in parts[:-1]:
        obj = getattr(obj, p)
    prev = getattr(obj, parts[-1])
    if isinstance(prev, torch.nn.Parameter):
        setattr(obj, parts[-1], torch.nn.Parameter(value.to(prev.device, dtype=prev.dtype),
                                                     requires_grad=prev.requires_grad))
    else:
        setattr(obj, parts[-1], value.to(prev.device, dtype=prev.dtype))


def load_torch_file(ckpt, safe_load: bool = False, device=None,
                    return_metadata: bool = False):
    import torch

    ckpt = str(ckpt)
    metadata = None

    if ckpt.endswith(".safetensors") or ckpt.endswith(".sft"):
        try:
            from safetensors.torch import load_file
            sd = load_file(ckpt, device=str(device) if device else "cpu")
            if return_metadata:
                try:
                    from safetensors import safe_open
                    with safe_open(ckpt, framework="pt") as f:
                        metadata = f.metadata()
                except Exception:
                    metadata = {}
        except ImportError:
            sd = torch.load(ckpt, map_location=device or "cpu", weights_only=True)
    else:
        sd = torch.load(ckpt, map_location=device or "cpu", weights_only=safe_load)

    if return_metadata:
        return sd, metadata or {}
    return sd


def save_torch_file(sd: dict, ckpt: str, metadata: dict | None = None):
    try:
        from safetensors.torch import save_file
        save_file(sd, ckpt, metadata=metadata)
    except ImportError:
        import torch
        torch.save(sd, ckpt)


def safetensors_header(path: str, max_size: int = 100_000_000) -> dict:
    import json as _json
    with open(path, "rb") as f:
        header_size = struct.unpack("<Q", f.read(8))[0]
        if header_size > max_size:
            return {}
        header_raw = f.read(header_size)
        return _json.loads(header_raw)


class ProgressBar:
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self._tqdm = None
        try:
            from tqdm import tqdm
            self._tqdm = tqdm(total=total, desc="Processing", leave=False)
        except ImportError:
            pass

    def update(self, value: int = 1):
        self.current += value
        if self._tqdm:
            self._tqdm.update(value)

    def update_absolute(self, value: int, total: int | None = None, preview=None):
        if total is not None:
            self.total = total
        diff = value - self.current
        if diff > 0:
            self.update(diff)
        self.current = value


UNET_MAP_BASIC = {}
UNET_MAP_RESNET = {}
UNET_MAP_ATTENTIONS = {}
TRANSFORMER_BLOCKS = {}
