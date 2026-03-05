"""
CatVTON Pipeline — Virtual Try-On via Concatenation.

Adapted from https://github.com/Zheng-Chong/CatVTON (ICLR 2025).
Uses SD 1.5 Inpainting as base with custom attention processors.
Garment transfer via spatial concatenation in latent space.
"""

import inspect
import os
from typing import Union

import numpy as np
import PIL
import torch
import tqdm
from diffusers import AutoencoderKL, DDIMScheduler, UNet2DConditionModel
from diffusers.utils.torch_utils import randn_tensor
from huggingface_hub import snapshot_download
from PIL import Image

from .attn_processor import AttnProcessor2_0, SkipAttnProcessor


def _init_adapter(unet, cross_attn_cls=SkipAttnProcessor):
    cross_attn_dim = unet.config.cross_attention_dim
    attn_procs = {}
    for name in unet.attn_processors.keys():
        cross_attention_dim = None if name.endswith("attn1.processor") else cross_attn_dim
        if name.startswith("mid_block"):
            hidden_size = unet.config.block_out_channels[-1]
        elif name.startswith("up_blocks"):
            block_id = int(name[len("up_blocks.")])
            hidden_size = list(reversed(unet.config.block_out_channels))[block_id]
        elif name.startswith("down_blocks"):
            block_id = int(name[len("down_blocks.")])
            hidden_size = unet.config.block_out_channels[block_id]
        if cross_attention_dim is None:
            attn_procs[name] = AttnProcessor2_0(
                hidden_size=hidden_size, cross_attention_dim=cross_attention_dim
            )
        else:
            attn_procs[name] = cross_attn_cls(
                hidden_size=hidden_size, cross_attention_dim=cross_attention_dim
            )
    unet.set_attn_processor(attn_procs)
    return torch.nn.ModuleList(unet.attn_processors.values())


def _get_trainable_module(unet, name="attention"):
    if name == "attention":
        blocks = torch.nn.ModuleList()
        for n, _ in unet.named_modules():
            if "attn1" in n:
                blocks.append(_)
        return blocks
    return unet


def _compute_vae_encodings(image, vae):
    pixel_values = image.to(memory_format=torch.contiguous_format).float()
    pixel_values = pixel_values.to(vae.device, dtype=vae.dtype)
    with torch.no_grad():
        latents = vae.encode(pixel_values).latent_dist.sample()
        latents = latents * vae.config.scaling_factor
    return latents


def _prepare_image(image):
    if isinstance(image, torch.Tensor):
        if image.ndim == 3:
            image = image.unsqueeze(0)
        return image.to(dtype=torch.float32)
    if isinstance(image, (PIL.Image.Image, np.ndarray)):
        image = [image]
    if isinstance(image, list) and isinstance(image[0], PIL.Image.Image):
        image = [np.array(i.convert("RGB"))[None, :] for i in image]
        image = np.concatenate(image, axis=0)
    elif isinstance(image, list) and isinstance(image[0], np.ndarray):
        image = np.concatenate([i[None, :] for i in image], axis=0)
    image = image.transpose(0, 3, 1, 2)
    return torch.from_numpy(image).to(dtype=torch.float32) / 127.5 - 1.0


def _prepare_mask_image(mask_image):
    if isinstance(mask_image, torch.Tensor):
        if mask_image.ndim == 2:
            mask_image = mask_image.unsqueeze(0).unsqueeze(0)
        elif mask_image.ndim == 3 and mask_image.shape[0] == 1:
            mask_image = mask_image.unsqueeze(0)
        elif mask_image.ndim == 3:
            mask_image = mask_image.unsqueeze(1)
        mask_image[mask_image < 0.5] = 0
        mask_image[mask_image >= 0.5] = 1
    else:
        if isinstance(mask_image, (PIL.Image.Image, np.ndarray)):
            mask_image = [mask_image]
        if isinstance(mask_image, list) and isinstance(mask_image[0], PIL.Image.Image):
            mask_image = np.concatenate(
                [np.array(m.convert("L"))[None, None, :] for m in mask_image], axis=0
            )
            mask_image = mask_image.astype(np.float32) / 255.0
        elif isinstance(mask_image, list) and isinstance(mask_image[0], np.ndarray):
            mask_image = np.concatenate([m[None, None, :] for m in mask_image], axis=0)
        mask_image[mask_image < 0.5] = 0
        mask_image[mask_image >= 0.5] = 1
        mask_image = torch.from_numpy(mask_image)
    return mask_image


def _resize_and_crop(image, size):
    w, h = image.size
    tw, th = size
    if w / h < tw / th:
        new_w, new_h = w, w * th // tw
    else:
        new_h, new_w = h, h * tw // th
    image = image.crop(
        ((w - new_w) // 2, (h - new_h) // 2, (w + new_w) // 2, (h + new_h) // 2)
    )
    return image.resize(size, Image.LANCZOS)


def _resize_and_padding(image, size):
    w, h = image.size
    tw, th = size
    if w / h < tw / th:
        new_h, new_w = th, w * th // h
    else:
        new_w, new_h = tw, h * tw // w
    image = image.resize((new_w, new_h), Image.LANCZOS)
    padded = Image.new("RGB", size, (255, 255, 255))
    padded.paste(image, ((tw - new_w) // 2, (th - new_h) // 2))
    return padded


class CatVTONPipeline:
    """CatVTON virtual try-on pipeline using SD 1.5 Inpainting + custom attention."""

    def __init__(self, base_ckpt, attn_ckpt, attn_ckpt_version="mix",
                 weight_dtype=torch.float32, device="cuda",
                 skip_safety_check=True, use_tf32=True):
        from accelerate import load_checkpoint_in_model

        self.device = device
        self.weight_dtype = weight_dtype
        self.skip_safety_check = skip_safety_check

        self.noise_scheduler = DDIMScheduler.from_pretrained(base_ckpt, subfolder="scheduler")
        self.vae = AutoencoderKL.from_pretrained(
            "stabilityai/sd-vae-ft-mse"
        ).to(device, dtype=weight_dtype)
        self.unet = UNet2DConditionModel.from_pretrained(
            base_ckpt, subfolder="unet"
        ).to(device, dtype=weight_dtype)

        _init_adapter(self.unet, cross_attn_cls=SkipAttnProcessor)
        self.attn_modules = _get_trainable_attention(self.unet)

        sub_folder = {
            "mix": "mix-48k-1024",
            "vitonhd": "vitonhd-16k-512",
            "dresscode": "dresscode-16k-512",
        }.get(attn_ckpt_version, "mix-48k-1024")

        if os.path.exists(attn_ckpt):
            ckpt_path = attn_ckpt
        else:
            ckpt_path = snapshot_download(repo_id=attn_ckpt)
        load_checkpoint_in_model(
            self.attn_modules,
            os.path.join(ckpt_path, sub_folder, "attention")
        )

        if use_tf32 and device == "cuda":
            torch.set_float32_matmul_precision("high")
            torch.backends.cuda.matmul.allow_tf32 = True

        try:
            self.unet.enable_attention_slicing(slice_size="auto")
        except Exception:
            pass
        try:
            self.vae.enable_slicing()
        except Exception:
            pass

    def __call__(self, image, condition_image, mask,
                 num_inference_steps=50, guidance_scale=2.5,
                 height=1024, width=768, generator=None, eta=1.0, **kwargs):
        concat_dim = -2

        image, condition_image, mask = self._check_inputs(
            image, condition_image, mask, width, height
        )
        image = _prepare_image(image).to(self.device, dtype=self.weight_dtype)
        condition_image = _prepare_image(condition_image).to(self.device, dtype=self.weight_dtype)
        mask = _prepare_mask_image(mask).to(self.device, dtype=self.weight_dtype)

        masked_image = image * (mask < 0.5)
        masked_latent = _compute_vae_encodings(masked_image, self.vae)
        condition_latent = _compute_vae_encodings(condition_image, self.vae)
        mask_latent = torch.nn.functional.interpolate(
            mask, size=masked_latent.shape[-2:], mode="nearest"
        )
        del image, mask, condition_image

        masked_latent_concat = torch.cat([masked_latent, condition_latent], dim=concat_dim)
        mask_latent_concat = torch.cat([mask_latent, torch.zeros_like(mask_latent)], dim=concat_dim)

        latents = randn_tensor(
            masked_latent_concat.shape,
            generator=generator,
            device=masked_latent_concat.device,
            dtype=self.weight_dtype,
        )

        self.noise_scheduler.set_timesteps(num_inference_steps, device=self.device)
        timesteps = self.noise_scheduler.timesteps
        latents = latents * self.noise_scheduler.init_noise_sigma

        do_cfg = guidance_scale > 1.0
        if do_cfg:
            masked_latent_concat = torch.cat([
                torch.cat([masked_latent, torch.zeros_like(condition_latent)], dim=concat_dim),
                masked_latent_concat,
            ])
            mask_latent_concat = torch.cat([mask_latent_concat] * 2)

        extra_step_kwargs = self._prepare_extra_step_kwargs(generator, eta)
        num_warmup = len(timesteps) - num_inference_steps * self.noise_scheduler.order

        with tqdm.tqdm(total=num_inference_steps) as pbar:
            for i, t in enumerate(timesteps):
                latent_input = torch.cat([latents] * 2) if do_cfg else latents
                latent_input = self.noise_scheduler.scale_model_input(latent_input, t)
                inpaint_input = torch.cat(
                    [latent_input, mask_latent_concat, masked_latent_concat], dim=1
                )
                noise_pred = self.unet(
                    inpaint_input, t.to(self.device),
                    encoder_hidden_states=None,
                    return_dict=False,
                )[0]

                if do_cfg:
                    uncond, cond = noise_pred.chunk(2)
                    noise_pred = uncond + guidance_scale * (cond - uncond)

                latents = self.noise_scheduler.step(
                    noise_pred, t, latents, **extra_step_kwargs
                ).prev_sample

                if i == len(timesteps) - 1 or (
                    (i + 1) > num_warmup and (i + 1) % self.noise_scheduler.order == 0
                ):
                    pbar.update()

                if self.device == "mps" and i % 5 == 4:
                    torch.mps.empty_cache()

        latents = latents.split(latents.shape[concat_dim] // 2, dim=concat_dim)[0]
        latents = 1 / self.vae.config.scaling_factor * latents
        decoded = self.vae.decode(latents.to(self.device, dtype=self.weight_dtype)).sample
        decoded = (decoded / 2 + 0.5).clamp(0, 1)
        decoded = decoded.cpu().permute(0, 2, 3, 1).float().numpy()

        images = (decoded * 255).round().astype("uint8")
        return [Image.fromarray(img) for img in images]

    def _check_inputs(self, image, condition_image, mask, width, height):
        if all(isinstance(x, torch.Tensor) for x in [image, condition_image, mask]):
            return image, condition_image, mask
        assert image.size == mask.size, "Image and mask must have the same size"
        image = _resize_and_crop(image, (width, height))
        mask = _resize_and_crop(mask, (width, height))
        condition_image = _resize_and_padding(condition_image, (width, height))
        return image, condition_image, mask

    def _prepare_extra_step_kwargs(self, generator, eta):
        extra = {}
        sig = inspect.signature(self.noise_scheduler.step)
        if "eta" in sig.parameters:
            extra["eta"] = eta
        if "generator" in sig.parameters:
            extra["generator"] = generator
        return extra


def _get_trainable_attention(unet):
    """Collect all attn1 sub-modules (matches CatVTON checkpoint layout)."""
    blocks = torch.nn.ModuleList()
    for name, module in unet.named_modules():
        if "attn1" in name:
            blocks.append(module)
    return blocks
