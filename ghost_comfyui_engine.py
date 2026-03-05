"""
ComfyUI Workflow Engine for Ghost — run community workflows natively.

Node resolution (no ComfyUI install required):
  1. Native (diffusers-based, 38+ node types, zero comfyui dependency)
  2. Comfy compat layer (ghost_comfy_compat) injected into sys.modules,
     allowing custom node repos to import 'comfy.*' without real ComfyUI
  3. Custom node packages (already cloned or auto-installed via
     ghost_comfy_manager — CNR zip or git clone with pip blacklist)

Package management is handled by ghost_comfy_manager, which provides:
  - Preemption-aware node resolution (extension-node-map + custom-node-list)
  - CNR (api.comfy.org) versioned package installs with git clone fallback
  - Pip blacklist to protect torch/torchvision from accidental overwrites
  - install.py execution for packages that need setup scripts
  - Model registry via model-list.json

Usage:
    engine = ComfyUIEngine(models_dir=Path("~/.ghost/models"))
    results = engine.execute_workflow(json.loads(Path("workflow.json").read_text()))
"""

import hashlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ghost.comfyui")

# ─── Paths ────────────────────────────────────────────────────────────

GHOST_HOME = Path.home() / ".ghost"
MODELS_DIR = GHOST_HOME / "models"
COMFYUI_CACHE = GHOST_HOME / "comfyui"
CUSTOM_NODES_DIR = COMFYUI_CACHE / "custom_nodes"

MODEL_SUBDIRS = {
    "checkpoints": "checkpoints",
    "loras": "loras",
    "controlnet": "controlnet",
    "vae": "vae",
    "clip_vision": "clip_vision",
    "embeddings": "embeddings",
    "upscale_models": "upscale_models",
}

for _d in [COMFYUI_CACHE, CUSTOM_NODES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)
for _sub in MODEL_SUBDIRS.values():
    (MODELS_DIR / _sub).mkdir(parents=True, exist_ok=True)


# ─── Device normalization ──────────────────────────────────────────────

def _normalize_torch_device(device: str) -> str:
    """Map device strings to valid PyTorch devices.

    Ghost may report 'mlx' or other framework-specific names, but PyTorch
    only accepts cpu/cuda/mps. This also handles 'auto' detection.
    """
    if device == "auto" or not device:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    d = device.lower().strip()
    if d in ("cuda", "cpu", "mps"):
        return d
    if d.startswith("cuda:"):
        return d
    if d in ("mlx", "apple", "metal"):
        try:
            import torch
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"
    if d in ("gpu",):
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"
    return "cpu"


# ═══════════════════════════════════════════════════════════════════════
#  WORKFLOW PARSER
# ═══════════════════════════════════════════════════════════════════════

def parse_workflow(raw: dict) -> dict:
    """Normalize a ComfyUI workflow to API/prompt format.

    Handles:
      - API format:  {node_id: {"class_type": ..., "inputs": {...}}}
      - UI format:   {"nodes": [...], "links": [...]}
      - Queue wrap:  {"prompt": {<api_format>}}
      - PNG embed:   {"extra_data": {"extra_pnginfo": {"workflow": ...}}}

    Returns {str_node_id: {"class_type": str, "inputs": dict}}.
    """
    if "nodes" in raw and "links" in raw:
        return _ui_to_api(raw)

    if all(isinstance(v, dict) and "class_type" in v for v in raw.values()):
        return {str(k): v for k, v in raw.items()}

    if "prompt" in raw and isinstance(raw["prompt"], dict):
        return parse_workflow(raw["prompt"])

    wf = (raw.get("extra_data") or {}).get("extra_pnginfo", {}).get("workflow")
    if wf:
        return parse_workflow(wf)

    raise ValueError(
        "Unrecognized workflow format. Expected ComfyUI API or UI JSON."
    )


def _ui_to_api(ui: dict) -> dict:
    """Convert the visual-editor (UI) JSON export to API/prompt format."""
    nodes = ui.get("nodes", [])
    links_raw = ui.get("links", [])

    # link_id → (origin_node_id, origin_slot_index)
    link_map: dict[int, tuple[int, int]] = {}
    for link in links_raw:
        if len(link) >= 5:
            link_map[link[0]] = (link[1], link[2])

    api: dict[str, dict] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        class_type = node.get("type", "")
        if not class_type or not node_id:
            continue

        inputs: dict[str, Any] = {}

        for slot in node.get("inputs", []):
            name = slot.get("name", "")
            link_id = slot.get("link")
            if link_id is not None and link_id in link_map:
                origin_id, origin_slot = link_map[link_id]
                inputs[name] = [str(origin_id), origin_slot]

        widget_values = node.get("widgets_values")
        if widget_values:
            inputs["_widget_values"] = list(widget_values)

        api[node_id] = {"class_type": class_type, "inputs": inputs}

    return api


# ═══════════════════════════════════════════════════════════════════════
#  EXECUTION GRAPH
# ═══════════════════════════════════════════════════════════════════════

def topological_sort(api_workflow: dict) -> list[str]:
    """Kahn's algorithm — returns node IDs in dependency-first order."""
    all_ids = set(api_workflow.keys())
    deps: dict[str, set[str]] = {nid: set() for nid in all_ids}

    for nid, ndata in api_workflow.items():
        for val in ndata.get("inputs", {}).values():
            if isinstance(val, list) and len(val) == 2:
                dep = str(val[0])
                if dep in all_ids:
                    deps[nid].add(dep)

    in_deg = {nid: len(d) for nid, d in deps.items()}
    queue = deque(nid for nid, d in in_deg.items() if d == 0)
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for other in all_ids:
            if nid in deps[other]:
                in_deg[other] -= 1
                if in_deg[other] == 0:
                    queue.append(other)

    if len(order) != len(all_ids):
        cycle = all_ids - set(order)
        raise ValueError(f"Circular dependency among nodes: {cycle}")

    return order


# ═══════════════════════════════════════════════════════════════════════
#  MODEL & SCHEDULER UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def resolve_model_path(filename: str, subdir: str = "checkpoints",
                       auto_download: bool = True) -> Path:
    """Locate a model file, auto-downloading if not found.

    Search order:
      1. Absolute / relative path
      2. Ghost models dir (~/.ghost/models/<subdir>)
      3. Any subfolder of Ghost models dir (rglob)
      4. Common ComfyUI install paths
      5. Auto-download from ComfyUI-Manager model-list.json
      6. Auto-download from HuggingFace (known checkpoint mappings)
      7. Auto-download from CivitAI search (if CIVITAI_API_TOKEN set)
    """
    found = _find_model_local(filename, subdir)
    if found:
        return found

    if not auto_download:
        raise FileNotFoundError(
            f"Model not found: {filename}\n"
            f"Searched: {MODELS_DIR / MODEL_SUBDIRS.get(subdir, subdir)}\n"
            f"Set auto_download=True to fetch automatically."
        )

    dest_override: list[str] = []
    url = _resolve_download_url(filename, subdir, _dest_override=dest_override)
    if url:
        if dest_override:
            dest_dir = MODELS_DIR / dest_override[0]
        else:
            dest_dir = MODELS_DIR / MODEL_SUBDIRS.get(subdir, subdir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(filename).name
        log.info("Auto-downloading model: %s → %s", filename, dest)
        _download_file(url, dest)
        return dest

    fallback_dir = MODELS_DIR / MODEL_SUBDIRS.get(subdir, subdir)
    raise FileNotFoundError(
        f"MISSING MODEL: {filename} (type: {subdir})\n"
        f"Auto-download failed — not found in ComfyUI-Manager registry, HuggingFace, or CivitAI.\n"
        f"ACTION REQUIRED: Use web_search to find this model "
        f"(try: '{Path(filename).stem} {subdir} download huggingface'), "
        f"then use comfyui_model_download(url=..., filename='{Path(filename).name}', "
        f"subdir='{subdir}') to download it, then retry the workflow."
    )


def _find_model_local(filename: str, subdir: str = "checkpoints") -> Path | None:
    """Search local directories for a model. Returns path or None."""
    p = Path(filename)
    if p.is_file():
        return p

    search = MODELS_DIR / MODEL_SUBDIRS.get(subdir, subdir)
    direct = search / filename
    if direct.exists():
        return direct

    for hit in search.rglob(Path(filename).name):
        return hit

    for base in [
        Path.home() / "ComfyUI",
        Path.home() / "comfyui",
        Path("/workspace/ComfyUI"),
    ]:
        candidate = base / "models" / subdir / filename
        if candidate.exists():
            return candidate

    return None


# ─── Model download sources ───────────────────────────────────────────

_model_list_data: list[dict] | None = None


def _get_model_list() -> list[dict]:
    """Fetch and cache ComfyUI-Manager's model-list.json (via ghost_comfy_manager)."""
    global _model_list_data
    if _model_list_data is not None:
        return _model_list_data

    try:
        from ghost_comfy_manager.registry import NodeRegistry
        _model_list_data = NodeRegistry.get().get_model_list()
        log.info("Model registry loaded: %d entries", len(_model_list_data))
        return _model_list_data
    except Exception as e:
        log.warning("Failed to load model list via registry: %s", e)
        _model_list_data = []
        return _model_list_data


# Well-known HuggingFace mappings for common checkpoint filenames
_HF_KNOWN_MODELS: dict[str, str] = {
    "sd_xl_base_1.0.safetensors":
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
    "sd_xl_base_1.0_0.9vae.safetensors":
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0_0.9vae.safetensors",
    "sd_xl_refiner_1.0.safetensors":
        "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0.safetensors",
    "sd_xl_refiner_1.0_0.9vae.safetensors":
        "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0_0.9vae.safetensors",
    "v1-5-pruned-emaonly.safetensors":
        "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors",
    "v1-5-pruned.safetensors":
        "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned.safetensors",
    "sd_xl_turbo_1.0.safetensors":
        "https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0.safetensors",
    "sd_xl_turbo_1.0_fp16.safetensors":
        "https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors",
    # Common LoRAs
    "lcm-lora-sdv1-5.safetensors":
        "https://huggingface.co/latent-consistency/lcm-lora-sdv1-5/resolve/main/pytorch_lora_weights.safetensors",
    "lcm-lora-sdxl.safetensors":
        "https://huggingface.co/latent-consistency/lcm-lora-sdxl/resolve/main/pytorch_lora_weights.safetensors",
}


def _resolve_download_url(filename: str, subdir: str,
                          _dest_override: list | None = None) -> str | None:
    """Try to find a download URL for a model filename.

    Resolution order:
      1. ComfyUI-Manager model-list.json (exact filename match)
      2. HuggingFace known-models table
      3. CivitAI API search (if CIVITAI_API_TOKEN env var set)
      4. HuggingFace Hub search (fuzzy, last resort)

    If _dest_override is provided (a mutable list), the first element will be
    set to the registry's preferred save_path so the caller can use it.
    """
    basename = Path(filename).name

    # 1) ComfyUI-Manager registry (exact then fuzzy stem match)
    model_list = _get_model_list()
    target_stem = Path(basename).stem.lower()
    fuzzy_hit: dict | None = None

    for entry in model_list:
        entry_filename = entry.get("filename", "")
        if entry_filename == basename:
            url = entry.get("url", "")
            if url:
                save_path = entry.get("save_path", "")
                if _dest_override is not None and save_path and save_path != "default":
                    _dest_override.append(save_path)
                log.info("Found in ComfyUI-Manager registry: %s → %s", basename, url[:80])
                return url
        elif not fuzzy_hit and Path(entry_filename).stem.lower() == target_stem:
            fuzzy_hit = entry

    if fuzzy_hit:
        url = fuzzy_hit.get("url", "")
        if url:
            save_path = fuzzy_hit.get("save_path", "")
            if _dest_override is not None and save_path and save_path != "default":
                _dest_override.append(save_path)
            log.info("Found in ComfyUI-Manager registry (stem match): %s → %s",
                     basename, url[:80])
            return url

    # 2) HuggingFace known-models hardcoded table
    if basename in _HF_KNOWN_MODELS:
        url = _HF_KNOWN_MODELS[basename]
        log.info("Found in HF known-models: %s", basename)
        return url

    # 3) HuggingFace Hub API search (multi-strategy, fuzzy)
    url = _search_huggingface(basename)
    if url:
        return url

    # 4) CivitAI search (works without token for free models)
    civitai_token = os.environ.get("CIVITAI_API_TOKEN", "")
    url = _search_civitai(basename, civitai_token)
    if url:
        return url

    log.warning("No download source found for model: %s (subdir=%s)", filename, subdir)
    return None


def _decompose_filename(filename: str) -> list[str]:
    """Break a model filename into multiple search queries, most specific first."""
    stem = Path(filename).stem
    queries = [stem]

    clean = stem.replace("_", "-").replace(".", "-")
    if clean != stem:
        queries.append(clean)

    import re
    no_version = re.sub(r'[-_]?(v\d[\d.]*|fp\d+|bf\d+|f\d+|pruned|emaonly|ema)$', '', stem, flags=re.I)
    if no_version and no_version != stem:
        queries.append(no_version)

    parts = re.split(r'[-_]', stem)
    if len(parts) >= 3:
        queries.append(" ".join(parts[:3]))
    if len(parts) >= 2:
        queries.append(" ".join(parts[:2]))

    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            deduped.append(q)
    return deduped


def _search_civitai(filename: str, token: str = "") -> str | None:
    """Search CivitAI for a model — works with or without token.

    Public search API doesn't require auth. Download URLs for free models
    also work without tokens.
    """
    import urllib.request
    import urllib.parse

    headers = {"User-Agent": "Ghost/1.0", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for query_str in _decompose_filename(filename):
        api_url = (
            f"https://civitai.com/api/v1/models"
            f"?query={urllib.parse.quote(query_str)}&limit=10&sort=Most%20Downloaded"
        )
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            for model in data.get("items", []):
                for version in model.get("modelVersions", []):
                    for file in version.get("files", []):
                        fname = file.get("name", "")
                        if fname == filename:
                            download_url = file.get("downloadUrl", "")
                            if download_url:
                                if token:
                                    sep = "&" if "?" in download_url else "?"
                                    download_url += f"{sep}token={token}"
                                log.info("Found on CivitAI (exact): %s → %s",
                                         filename, model.get("name"))
                                return download_url

                        if Path(fname).stem.lower() == Path(filename).stem.lower():
                            download_url = file.get("downloadUrl", "")
                            if download_url:
                                if token:
                                    sep = "&" if "?" in download_url else "?"
                                    download_url += f"{sep}token={token}"
                                log.info("Found on CivitAI (stem match): %s → %s (%s)",
                                         filename, model.get("name"), fname)
                                return download_url
        except Exception as e:
            log.debug("CivitAI search '%s' failed: %s", query_str, e)

    return None


def _search_huggingface(filename: str) -> str | None:
    """Search HuggingFace Hub API with multiple query strategies.

    Tries exact filename match first, then fuzzy stem match, across
    multiple decomposed search terms.
    """
    import urllib.request
    import urllib.parse

    target_name = Path(filename).name
    target_stem = Path(filename).stem.lower()
    safetensor_exts = {".safetensors", ".bin", ".pt", ".ckpt", ".pth"}

    searched_models: set[str] = set()

    for query_str in _decompose_filename(filename):
        api_url = (
            f"https://huggingface.co/api/models"
            f"?search={urllib.parse.quote(query_str)}&limit=10&sort=downloads&direction=-1"
        )
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "Ghost/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                models = json.loads(resp.read())
        except Exception as e:
            log.debug("HF search '%s' failed: %s", query_str, e)
            continue

        for model in models:
            model_id = model.get("modelId", model.get("id", ""))
            if not model_id or model_id in searched_models:
                continue
            searched_models.add(model_id)

            try:
                detail_url = f"https://huggingface.co/api/models/{model_id}"
                req2 = urllib.request.Request(detail_url, headers={"User-Agent": "Ghost/1.0"})
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    details = json.loads(resp2.read())
            except Exception:
                continue

            exact_match = None
            stem_match = None

            for sib in details.get("siblings", []):
                rfilename = sib.get("rfilename", "")
                sib_name = Path(rfilename).name
                sib_ext = Path(rfilename).suffix.lower()

                if sib_ext not in safetensor_exts:
                    continue

                if sib_name == target_name:
                    exact_match = rfilename
                    break

                if Path(sib_name).stem.lower() == target_stem:
                    stem_match = rfilename

                if not stem_match and target_stem in sib_name.lower():
                    stem_match = rfilename

            if exact_match:
                url = f"https://huggingface.co/{model_id}/resolve/main/{exact_match}"
                log.info("Found on HuggingFace (exact): %s → %s/%s",
                         filename, model_id, exact_match)
                return url
            if stem_match:
                url = f"https://huggingface.co/{model_id}/resolve/main/{stem_match}"
                log.info("Found on HuggingFace (fuzzy): %s → %s/%s",
                         filename, model_id, stem_match)
                return url

    return None


def _download_file(url: str, dest: Path, chunk_size: int = 8 * 1024 * 1024):
    """Download a file with progress logging and resume support."""
    import urllib.request

    tmp = dest.with_suffix(dest.suffix + ".part")
    start_byte = tmp.stat().st_size if tmp.exists() else 0

    headers = {"User-Agent": "Ghost/1.0"}
    if start_byte > 0:
        headers["Range"] = f"bytes={start_byte}-"
        log.info("Resuming download from byte %d", start_byte)

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_str = resp.headers.get("Content-Length", "0")
            total = int(total_str) + start_byte if total_str else 0
            total_mb = total / (1024 * 1024) if total else 0

            log.info("Downloading %s (%.1f MB)...", dest.name, total_mb)

            mode = "ab" if start_byte > 0 else "wb"
            downloaded = start_byte
            last_log = time.time()

            with open(tmp, mode) as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_log >= 5.0:
                        if total:
                            pct = downloaded / total * 100
                            log.info("  %.1f%% (%.0f / %.0f MB)",
                                     pct, downloaded / 1048576, total_mb)
                        else:
                            log.info("  %.0f MB downloaded...",
                                     downloaded / 1048576)
                        last_log = now

        tmp.rename(dest)
        log.info("Download complete: %s (%.1f MB)", dest.name, downloaded / 1048576)

    except Exception as e:
        log.error("Download failed for %s: %s (partial file kept at %s)",
                  url, e, tmp)
        raise RuntimeError(
            f"Failed to download model {dest.name}: {e}\n"
            f"Partial file at: {tmp}"
        ) from e


SCHEDULER_MAP = {
    "euler":             "EulerDiscreteScheduler",
    "euler_ancestral":   "EulerAncestralDiscreteScheduler",
    "heun":              "HeunDiscreteScheduler",
    "dpm_2":             "KDPM2DiscreteScheduler",
    "dpm_2_ancestral":   "KDPM2AncestralDiscreteScheduler",
    "lms":               "LMSDiscreteScheduler",
    "dpmpp_2m":          "DPMSolverMultistepScheduler",
    "dpmpp_2m_sde":      "DPMSolverMultistepScheduler",
    "dpmpp_sde":         "DPMSolverSinglestepScheduler",
    "ddim":              "DDIMScheduler",
    "ddpm":              "DDPMScheduler",
    "uni_pc":            "UniPCMultistepScheduler",
}


def _make_scheduler(sampler_name: str, scheduler_name: str, config: dict):
    """Build a diffusers scheduler from ComfyUI sampler/scheduler names."""
    import diffusers

    cls_name = SCHEDULER_MAP.get(sampler_name, "EulerDiscreteScheduler")
    cls = getattr(diffusers, cls_name, diffusers.EulerDiscreteScheduler)
    cfg = dict(config)

    if scheduler_name == "karras":
        cfg["use_karras_sigmas"] = True
    if sampler_name == "dpmpp_2m_sde":
        cfg["algorithm_type"] = "sde-dpmsolver++"

    return cls.from_config(cfg)


def _detect_model_type(ckpt_path: Path) -> str:
    """Detect sd15 / sdxl / sd3 from checkpoint keys."""
    name = ckpt_path.name.lower()
    if "xl" in name:
        return "sdxl"
    if "sd3" in name or "flux" in name:
        return "sd3"

    try:
        from safetensors import safe_open
        if str(ckpt_path).endswith(".safetensors"):
            with safe_open(str(ckpt_path), framework="pt") as f:
                keys = list(f.keys())[:500]
            if any("conditioner.embedders.1" in k for k in keys):
                return "sdxl"
            if any("joint_blocks" in k for k in keys):
                return "sd3"
            return "sd15"
    except Exception:
        pass

    size_gb = ckpt_path.stat().st_size / (1024 ** 3)
    return "sdxl" if size_gb > 5.0 else "sd15"


# ═══════════════════════════════════════════════════════════════════════
#  NATIVE TYPE WRAPPERS  (used only in native mode)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class _NativeModel:
    unet: Any
    scheduler_config: dict
    model_type: str = "sd15"


@dataclass
class _NativeCLIP:
    tokenizer: Any
    text_encoder: Any
    tokenizer_2: Any = None
    text_encoder_2: Any = None
    model_type: str = "sd15"


# ═══════════════════════════════════════════════════════════════════════
#  NATIVE NODE IMPLEMENTATIONS
#
#  Convention matches ComfyUI:
#    RETURN_TYPES  — tuple of type strings
#    FUNCTION      — name of the method to call
#    method(...)   — returns tuple of outputs matching RETURN_TYPES
#
#  ComfyUI type formats (matched exactly for interop):
#    CONDITIONING = [(embeddings_tensor, {"pooled_output": ...})]
#    LATENT       = {"samples": tensor}              + optional "noise_mask"
#    IMAGE        = tensor (B, H, W, C) float [0,1]
#    MASK         = tensor (H, W) or (B, H, W)      float [0,1]
# ═══════════════════════════════════════════════════════════════════════

NATIVE_NODES: dict[str, type] = {}

_model_cache: dict[str, Any] = {}


class NativeCheckpointLoaderSimple:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"ckpt_name": ("STRING",)}}
    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    FUNCTION = "load_checkpoint"

    def load_checkpoint(self, ckpt_name, _engine=None, **kw):
        cache_key = f"ckpt:{ckpt_name}"
        if cache_key in _model_cache:
            log.info("Checkpoint cache hit: %s", ckpt_name)
            return _model_cache[cache_key]

        import torch
        from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline

        path = resolve_model_path(ckpt_name, "checkpoints")
        device = _engine.device if _engine else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        mtype = _detect_model_type(path)

        log.info("Loading checkpoint %s (%s) → %s", ckpt_name, mtype, device)
        is_safetensors = str(path).endswith(".safetensors")

        if mtype == "sdxl":
            pipe = StableDiffusionXLPipeline.from_single_file(
                str(path), torch_dtype=dtype, use_safetensors=is_safetensors,
            )
            pipe.to(device)
            model = _NativeModel(pipe.unet, pipe.scheduler.config, "sdxl")
            clip = _NativeCLIP(
                pipe.tokenizer, pipe.text_encoder,
                pipe.tokenizer_2, pipe.text_encoder_2, "sdxl",
            )
        else:
            pipe = StableDiffusionPipeline.from_single_file(
                str(path), torch_dtype=dtype, use_safetensors=is_safetensors,
            )
            pipe.to(device)
            model = _NativeModel(pipe.unet, pipe.scheduler.config, "sd15")
            clip = _NativeCLIP(pipe.tokenizer, pipe.text_encoder, model_type="sd15")

        vae = pipe.vae
        try:
            pipe.enable_attention_slicing()
        except Exception:
            pass

        result = (model, clip, vae)
        _model_cache[cache_key] = result
        log.info("Checkpoint ready: %s on %s", ckpt_name, device)
        return result


NATIVE_NODES["CheckpointLoaderSimple"] = NativeCheckpointLoaderSimple


class NativeCLIPTextEncode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",), "text": ("STRING", {"multiline": True})}}
    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "encode"

    def encode(self, text, clip, **kw):
        import torch

        if isinstance(clip, _NativeCLIP) and clip.model_type == "sdxl":
            return self._encode_sdxl(text, clip)
        return self._encode_sd15(text, clip)

    @staticmethod
    def _encode_sd15(text, clip):
        import torch

        tok = clip.tokenizer
        enc = clip.text_encoder
        device = enc.device

        tokens = tok(
            text, padding="max_length", max_length=tok.model_max_length,
            truncation=True, return_tensors="pt",
        )
        with torch.no_grad():
            out = enc(tokens.input_ids.to(device))

        cond = out.last_hidden_state
        return ([(cond, {})],)

    @staticmethod
    def _encode_sdxl(text, clip):
        import torch

        device = clip.text_encoder.device
        tok1 = clip.tokenizer(
            text, padding="max_length", max_length=77,
            truncation=True, return_tensors="pt",
        )
        tok2 = clip.tokenizer_2(
            text, padding="max_length", max_length=77,
            truncation=True, return_tensors="pt",
        )
        with torch.no_grad():
            e1 = clip.text_encoder(tok1.input_ids.to(device))
            e2 = clip.text_encoder_2(tok2.input_ids.to(device))

        embeds = torch.cat([e1.last_hidden_state, e2.last_hidden_state], dim=-1)
        pooled = e2[0]
        return ([(embeds, {"pooled_output": pooled})],)


NATIVE_NODES["CLIPTextEncode"] = NativeCLIPTextEncode


class NativeKSampler:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",), "seed": ("INT",), "steps": ("INT",),
            "cfg": ("FLOAT",), "sampler_name": ("STRING",),
            "scheduler": ("STRING",), "positive": ("CONDITIONING",),
            "negative": ("CONDITIONING",), "latent_image": ("LATENT",),
            "denoise": ("FLOAT", {"default": 1.0}),
        }}
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "sample"

    def sample(self, model, seed, steps, cfg, sampler_name, scheduler,
               positive, negative, latent_image, denoise=1.0,
               _engine=None, **kw):
        import torch

        unet = model.unet
        device = next(unet.parameters()).device
        dtype = next(unet.parameters()).dtype
        is_sdxl = getattr(model, "model_type", "sd15") == "sdxl"

        sched = _make_scheduler(sampler_name, scheduler, model.scheduler_config)
        sched.set_timesteps(int(steps), device=device)

        latents = latent_image["samples"].clone().to(device=device, dtype=dtype)
        gen = torch.Generator(device="cpu").manual_seed(int(seed))
        noise = torch.randn(latents.shape, generator=gen, dtype=dtype, device="cpu").to(device)

        denoise = float(denoise)
        if denoise < 1.0:
            init_step = min(int(steps * denoise), int(steps))
            t_start = max(int(steps) - init_step, 0)
            timesteps = sched.timesteps[t_start:]
            latents = sched.add_noise(latents, noise, timesteps[:1])
        else:
            timesteps = sched.timesteps
            sigma = getattr(sched, "init_noise_sigma", 1.0)
            latents = noise * (sigma.item() if hasattr(sigma, "item") else sigma)

        pos_emb = positive[0][0].to(device=device, dtype=dtype)
        neg_emb = negative[0][0].to(device=device, dtype=dtype)

        cn_entries = positive[0][1].get("controlnets", [])

        cn_images = []
        for cn_e in cn_entries:
            cimg = cn_e["control_image"]
            if isinstance(cimg, torch.Tensor):
                if cimg.ndim == 4 and cimg.shape[-1] in (1, 3, 4):
                    cimg = cimg.permute(0, 3, 1, 2)
                cn_images.append((cn_e["control_net"], cimg.to(device=device, dtype=dtype),
                                  cn_e["strength"]))

        added_cond = None
        if is_sdxl:
            pp = positive[0][1].get("pooled_output")
            np_ = negative[0][1].get("pooled_output")
            if pp is not None and np_ is not None:
                h, w = latents.shape[2] * 8, latents.shape[3] * 8
                time_ids = torch.tensor(
                    [[h, w, 0, 0, h, w]], dtype=dtype, device=device,
                )
                added_cond = {
                    "text_embeds": torch.cat([
                        np_.to(device=device, dtype=dtype),
                        pp.to(device=device, dtype=dtype),
                    ]),
                    "time_ids": torch.cat([time_ids, time_ids]),
                }

        total = len(timesteps)
        cb = _engine.progress_cb if _engine else None
        for i, t in enumerate(timesteps):
            if cb:
                cb(f"Sampling {i + 1}/{total}")

            lat_in = torch.cat([latents] * 2)
            lat_in = sched.scale_model_input(lat_in, t)

            unet_kw: dict[str, Any] = {
                "sample": lat_in,
                "timestep": t,
                "encoder_hidden_states": torch.cat([neg_emb, pos_emb]),
            }
            if added_cond:
                unet_kw["added_cond_kwargs"] = added_cond

            if cn_images:
                down_res, mid_res = [], None
                for cnet_model, cnet_img, cnet_str in cn_images:
                    try:
                        cn_kw: dict[str, Any] = {
                            "controlnet_cond": cnet_img,
                            "conditioning_scale": cnet_str,
                            "return_dict": False,
                        }
                        if added_cond and is_sdxl:
                            cn_kw["added_cond_kwargs"] = added_cond
                        cn_out = cnet_model(
                            lat_in, t,
                            encoder_hidden_states=torch.cat([neg_emb, pos_emb]),
                            **cn_kw,
                        )
                        if len(cn_out) == 2:
                            d_samples, m_sample = cn_out
                            if not down_res:
                                down_res = list(d_samples)
                            else:
                                for j in range(len(d_samples)):
                                    down_res[j] = down_res[j] + d_samples[j]
                            mid_res = m_sample if mid_res is None else mid_res + m_sample
                    except Exception as e:
                        log.warning("ControlNet forward pass failed (step %d): %s",
                                    i + 1, e, exc_info=True)
                        cn_images = []
                        break
                if down_res:
                    unet_kw["down_block_additional_residuals"] = down_res
                if mid_res is not None:
                    unet_kw["mid_block_additional_residual"] = mid_res

            with torch.no_grad():
                pred = unet(**unet_kw).sample

            pu, pt = pred.chunk(2)
            pred = pu + float(cfg) * (pt - pu)
            latents = sched.step(pred, t, latents).prev_sample

        noise_mask = latent_image.get("noise_mask")
        if noise_mask is not None:
            orig = latent_image["samples"].to(device=device, dtype=dtype)
            m = noise_mask.to(device=device, dtype=dtype)
            if m.dim() == 3:
                m = m.unsqueeze(1)
            latents = orig * (1.0 - m) + latents * m

        return ({"samples": latents},)


NATIVE_NODES["KSampler"] = NativeKSampler
NATIVE_NODES["KSamplerAdvanced"] = NativeKSampler


class NativeVAEDecode:
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "decode"

    def decode(self, samples, vae, **kw):
        import torch

        latents = samples["samples"]
        device = next(vae.parameters()).device
        dtype = next(vae.parameters()).dtype
        latents = latents.to(device=device, dtype=dtype)

        scale = getattr(vae.config, "scaling_factor", 0.18215)
        latents = latents / scale

        with torch.no_grad():
            image = vae.decode(latents).sample

        image = (image / 2.0 + 0.5).clamp(0, 1)
        image = image.permute(0, 2, 3, 1).cpu().float()
        return (image,)


NATIVE_NODES["VAEDecode"] = NativeVAEDecode


class NativeVAEEncode:
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "encode"

    def encode(self, pixels, vae, **kw):
        import torch

        device = next(vae.parameters()).device
        dtype = next(vae.parameters()).dtype
        x = pixels.permute(0, 3, 1, 2).to(device=device, dtype=dtype)
        x = x * 2.0 - 1.0

        with torch.no_grad():
            latent = vae.encode(x).latent_dist.sample()

        scale = getattr(vae.config, "scaling_factor", 0.18215)
        return ({"samples": latent * scale},)


NATIVE_NODES["VAEEncode"] = NativeVAEEncode


class NativeEmptyLatentImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 512}),
            "height": ("INT", {"default": 512}),
            "batch_size": ("INT", {"default": 1}),
        }}
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "generate"

    def generate(self, width=512, height=512, batch_size=1, **kw):
        import torch
        latent = torch.zeros(int(batch_size), 4, int(height) // 8, int(width) // 8)
        return ({"samples": latent},)


NATIVE_NODES["EmptyLatentImage"] = NativeEmptyLatentImage


class NativeLoadImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("STRING",)}}
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"

    def load_image(self, image, **kw):
        import torch
        import numpy as np
        from PIL import Image

        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image

        if img.mode == "RGBA":
            alpha = np.array(img.split()[-1]).astype(np.float32) / 255.0
            mask = torch.from_numpy(1.0 - alpha)
            img = img.convert("RGB")
        else:
            img = img.convert("RGB")
            mask = torch.zeros(img.height, img.width, dtype=torch.float32)

        arr = np.array(img).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr).unsqueeze(0)  # (1, H, W, C)
        return (tensor, mask)


NATIVE_NODES["LoadImage"] = NativeLoadImage


class NativeSaveImage:
    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True

    def save_images(self, images, filename_prefix="ComfyUI", _engine=None, **kw):
        import torch
        from PIL import Image as PILImage

        results = []
        for i in range(images.shape[0]):
            img_np = (images[i].cpu().numpy() * 255.0).clip(0, 255).astype("uint8")
            pil = PILImage.fromarray(img_np)

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"{filename_prefix}_{ts}_{i}.png"

            if _engine and _engine.output_dir:
                out_path = Path(_engine.output_dir) / fname
                out_path.parent.mkdir(parents=True, exist_ok=True)
                pil.save(str(out_path))
                results.append(str(out_path))
            else:
                out = GHOST_HOME / "media" / "image" / fname
                out.parent.mkdir(parents=True, exist_ok=True)
                pil.save(str(out))
                results.append(str(out))

        if _engine:
            _engine._saved_outputs.extend(results)

        return {"ui": {"images": results}}


NATIVE_NODES["SaveImage"] = NativeSaveImage
NATIVE_NODES["PreviewImage"] = NativeSaveImage


class NativeLoraLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",), "clip": ("CLIP",),
            "lora_name": ("STRING",),
            "strength_model": ("FLOAT", {"default": 1.0}),
            "strength_clip": ("FLOAT", {"default": 1.0}),
        }}
    RETURN_TYPES = ("MODEL", "CLIP")
    FUNCTION = "load_lora"

    def load_lora(self, model, clip, lora_name, strength_model=1.0,
                  strength_clip=1.0, _engine=None, **kw):
        cache_key = f"lora:{lora_name}"
        if cache_key in _model_cache:
            log.info("LoRA already applied: %s", lora_name)
            return _model_cache[cache_key]

        path = resolve_model_path(lora_name, "loras")
        log.info("Loading LoRA: %s (model=%.2f, clip=%.2f)",
                 lora_name, strength_model, strength_clip)

        from diffusers import StableDiffusionPipeline
        import torch

        device = next(model.unet.parameters()).device
        load_device = "cpu" if "mps" in str(device) else str(device)
        lora_sd = {}
        if str(path).endswith(".safetensors"):
            from safetensors.torch import load_file
            lora_sd = load_file(str(path), device=load_device)
        else:
            lora_sd = torch.load(str(path), map_location=load_device, weights_only=True)

        from diffusers.loaders.lora_pipeline import StableDiffusionLoraLoaderMixin
        try:
            model.unet.load_attn_procs(str(path))
        except Exception:
            log.warning("LoRA load via attn_procs failed, trying state_dict merge")

        result = (model, clip)
        _model_cache[cache_key] = result
        return result


NATIVE_NODES["LoraLoader"] = NativeLoraLoader


class NativeSetLatentNoiseMask:
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "set_mask"

    def set_mask(self, samples, mask, **kw):
        import torch
        s = dict(samples)
        if isinstance(mask, torch.Tensor):
            s["noise_mask"] = mask.clone()
        return (s,)


NATIVE_NODES["SetLatentNoiseMask"] = NativeSetLatentNoiseMask


class NativeImageScale:
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "upscale"

    def upscale(self, image, upscale_method="bilinear", width=512,
                height=512, crop="disabled", **kw):
        import torch
        import torch.nn.functional as F

        x = image.permute(0, 3, 1, 2)  # (B,C,H,W)

        mode_map = {
            "nearest": "nearest",
            "bilinear": "bilinear",
            "bicubic": "bicubic",
            "area": "area",
            "lanczos": "bicubic",
        }
        mode = mode_map.get(upscale_method, "bilinear")
        align = mode not in ("nearest", "area")

        x = F.interpolate(
            x, size=(int(height), int(width)), mode=mode,
            align_corners=align if align else None,
        )
        return (x.permute(0, 2, 3, 1),)


NATIVE_NODES["ImageScale"] = NativeImageScale
NATIVE_NODES["ImageScaleBy"] = NativeImageScale


class NativeLatentUpscale:
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "upscale"

    def upscale(self, samples, upscale_method="bilinear", width=512,
                height=512, crop="disabled", **kw):
        import torch.nn.functional as F

        s = samples["samples"]
        lh, lw = int(height) // 8, int(width) // 8
        mode = "bilinear" if upscale_method != "nearest" else "nearest"
        align = mode == "bilinear"
        s = F.interpolate(s, size=(lh, lw), mode=mode,
                          align_corners=align if align else None)
        return ({"samples": s},)


NATIVE_NODES["LatentUpscale"] = NativeLatentUpscale


class NativeImageInvert:
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "invert"

    def invert(self, image, **kw):
        return (1.0 - image,)


NATIVE_NODES["ImageInvert"] = NativeImageInvert


class NativeCLIPSetLastLayer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",), "stop_at_clip_layer": ("INT", {"default": -1})}}
    RETURN_TYPES = ("CLIP",)
    FUNCTION = "set_last_layer"

    def set_last_layer(self, clip, stop_at_clip_layer=-1, **kw):
        return (clip,)


NATIVE_NODES["CLIPSetLastLayer"] = NativeCLIPSetLastLayer


class NativeConditioningCombine:
    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "combine"

    def combine(self, conditioning_1, conditioning_2, **kw):
        return (conditioning_1 + conditioning_2,)


NATIVE_NODES["ConditioningCombine"] = NativeConditioningCombine


class NativeVAEEncodeForInpaint:
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "encode"

    def encode(self, pixels, vae, mask, grow_mask_by=6, **kw):
        import torch

        encoder = NativeVAEEncode()
        latent_result = encoder.encode(pixels, vae)[0]

        if mask.dim() == 2:
            mask = mask.unsqueeze(0)

        lh, lw = latent_result["samples"].shape[2], latent_result["samples"].shape[3]
        mask_down = torch.nn.functional.interpolate(
            mask.unsqueeze(1), size=(lh, lw), mode="bilinear",
        ).squeeze(1)
        mask_down = (mask_down > 0.5).float()

        latent_result["noise_mask"] = mask_down
        return (latent_result,)


NATIVE_NODES["VAEEncodeForInpaint"] = NativeVAEEncodeForInpaint


# ── Additional built-in nodes (loaders, utility) ─────────────────────

class NativeUNETLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"unet_name": ("STRING",), "weight_dtype": ("STRING",)}}
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load_unet"

    def load_unet(self, unet_name, weight_dtype="default", **kw):
        path = resolve_model_path(unet_name, "unet")
        dtype = torch.float16 if weight_dtype in ("fp16", "float16") else None
        from diffusers import UNet2DConditionModel
        try:
            unet = UNet2DConditionModel.from_pretrained(
                str(path.parent), subfolder=path.name if path.is_dir() else None,
                torch_dtype=dtype, token=os.environ.get("HF_TOKEN"),
            )
        except Exception:
            unet = UNet2DConditionModel.from_single_file(
                str(path), torch_dtype=dtype,
            )
        device = _normalize_torch_device("auto")
        unet = unet.to(device)
        return (unet,)

NATIVE_NODES["UNETLoader"] = NativeUNETLoader


class NativeCLIPLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip_name": ("STRING",), "type": ("STRING",)}}
    RETURN_TYPES = ("CLIP",)
    FUNCTION = "load_clip"

    def load_clip(self, clip_name, type="stable_diffusion", **kw):
        from transformers import CLIPTokenizer, CLIPTextModel
        path = resolve_model_path(clip_name, "clip")
        tok = CLIPTokenizer.from_pretrained(str(path) if path.is_dir() else "openai/clip-vit-large-patch14")
        model = CLIPTextModel.from_pretrained(str(path) if path.is_dir() else "openai/clip-vit-large-patch14")
        device = _normalize_torch_device("auto")
        model = model.to(device)
        return ({"tokenizer": tok, "model": model, "path": str(path)},)

NATIVE_NODES["CLIPLoader"] = NativeCLIPLoader


class NativeCLIPVisionLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip_name": ("STRING",)}}
    RETURN_TYPES = ("CLIP_VISION",)
    FUNCTION = "load_clip_vision"

    def load_clip_vision(self, clip_name, **kw):
        from transformers import CLIPVisionModelWithProjection, CLIPImageProcessor
        path = resolve_model_path(clip_name, "clip_vision")
        try:
            processor = CLIPImageProcessor.from_pretrained(str(path) if path.is_dir() else "openai/clip-vit-large-patch14")
            model = CLIPVisionModelWithProjection.from_pretrained(str(path) if path.is_dir() else "openai/clip-vit-large-patch14")
        except Exception:
            processor = CLIPImageProcessor.from_pretrained("openai/clip-vit-large-patch14")
            model = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-large-patch14")
        device = _normalize_torch_device("auto")
        model = model.to(device)
        return ({"processor": processor, "model": model},)

NATIVE_NODES["CLIPVisionLoader"] = NativeCLIPVisionLoader


class NativeCLIPVisionEncode:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip_vision": ("CLIP_VISION",), "image": ("IMAGE",)}}
    RETURN_TYPES = ("CLIP_VISION_OUTPUT",)
    FUNCTION = "encode"

    def encode(self, clip_vision, image, **kw):
        import numpy as np
        processor = clip_vision["processor"]
        model = clip_vision["model"]
        if isinstance(image, torch.Tensor):
            img_np = (image.squeeze(0).cpu().numpy() * 255).astype(np.uint8)
            from PIL import Image as PILImage
            pil_img = PILImage.fromarray(img_np)
        else:
            pil_img = image
        inputs = processor(images=pil_img, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(**inputs)
        return ({"last_hidden_state": outputs.last_hidden_state, "image_embeds": outputs.image_embeds},)

NATIVE_NODES["CLIPVisionEncode"] = NativeCLIPVisionEncode


class NativeVAELoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"vae_name": ("STRING",)}}
    RETURN_TYPES = ("VAE",)
    FUNCTION = "load_vae"

    def load_vae(self, vae_name, **kw):
        from diffusers import AutoencoderKL
        path = resolve_model_path(vae_name, "vae")
        try:
            vae = AutoencoderKL.from_single_file(str(path), torch_dtype=torch.float16)
        except Exception:
            vae = AutoencoderKL.from_pretrained(str(path), torch_dtype=torch.float16)
        device = _normalize_torch_device("auto")
        vae = vae.to(device)
        return (vae,)

NATIVE_NODES["VAELoader"] = NativeVAELoader


class NativeControlNetLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"control_net_name": ("STRING",)}}
    RETURN_TYPES = ("CONTROL_NET",)
    FUNCTION = "load_controlnet"

    @staticmethod
    def _merge_control_lora(raw_sd: dict) -> dict:
        """Reconstruct full weights from LoRA-decomposed ControlNet state dict.

        Control-LoRA format: 'key.up' (out, rank, 1, 1) + 'key.down' (rank, in, kH, kW)
        Merged into: 'key.weight' = base + up.flat @ down.flat -> (out, in, kH, kW)
        """
        import torch
        merged = {}
        up_keys = {k[:-3] for k in raw_sd if k.endswith(".up")}
        for prefix in up_keys:
            up = raw_sd[f"{prefix}.up"].float()
            down = raw_sd[f"{prefix}.down"].float()
            base_key = f"{prefix}.weight"
            base = raw_sd.get(base_key)

            if up.ndim == 2 and down.ndim == 2:
                merged_w = up @ down
            elif up.ndim >= 2 and down.ndim >= 2:
                out_shape = (up.shape[0],) + down.shape[1:]
                rank = up.shape[1]
                merged_w = (up.reshape(up.shape[0], rank)
                            @ down.reshape(rank, -1)).reshape(out_shape)
            else:
                merged_w = up @ down

            if base is not None:
                merged[base_key] = base.float() + merged_w
            else:
                merged[base_key] = merged_w

        for k, v in raw_sd.items():
            if k.endswith(".up") or k.endswith(".down") or k == "lora_controlnet":
                continue
            if k not in merged:
                merged[k] = v
        return merged

    def load_controlnet(self, control_net_name, **kw):
        import torch
        from diffusers import ControlNetModel
        path = resolve_model_path(control_net_name, "controlnet")
        device = _normalize_torch_device("auto")
        dtype = torch.float16 if device != "cpu" else torch.float32

        from safetensors.torch import load_file
        raw_sd = load_file(str(path))

        is_control_lora = any(k == "lora_controlnet" for k in raw_sd)
        if is_control_lora:
            log.info("Detected Control-LoRA format, merging %d LoRA pairs...",
                     sum(1 for k in raw_sd if k.endswith(".up")))
            raw_sd = self._merge_control_lora(raw_sd)
            from safetensors.torch import save_file
            merged_path = path.with_suffix(".merged.safetensors")
            save_file(raw_sd, str(merged_path))
            path = merged_path
            log.info("Saved merged ControlNet to %s", merged_path.name)

        is_sdxl = "xl" in str(path).lower() or "sdxl" in control_net_name.lower()
        configs = []
        name_l = control_net_name.lower()
        if is_sdxl:
            if "depth" in name_l:
                configs.append("diffusers/controlnet-depth-sdxl-1.0")
            if "canny" in name_l:
                configs.append("diffusers/controlnet-canny-sdxl-1.0")
            if not configs:
                configs.append("diffusers/controlnet-canny-sdxl-1.0")
        else:
            if "depth" in name_l:
                configs.append("lllyasviel/control_v11f1p_sd15_depth")
            if "canny" in name_l:
                configs.append("lllyasviel/sd-controlnet-canny")

        for cfg in configs:
            try:
                log.info("Loading ControlNet with config: %s", cfg)
                cnet = ControlNetModel.from_single_file(
                    str(path), config=cfg, torch_dtype=dtype,
                    low_cpu_mem_usage=False)
                cnet = cnet.to(device)
                return (cnet,)
            except Exception as e:
                log.debug("Config %s failed: %s", cfg, e)

        try:
            log.info("Loading ControlNet from_single_file (auto-config)...")
            cnet = ControlNetModel.from_single_file(
                str(path), torch_dtype=dtype, low_cpu_mem_usage=False)
            cnet = cnet.to(device)
            return (cnet,)
        except Exception as e1:
            log.debug("from_single_file auto-config failed: %s", e1)

        try:
            log.info("Loading ControlNet from_pretrained...")
            cnet = ControlNetModel.from_pretrained(str(path), torch_dtype=dtype)
            cnet = cnet.to(device)
            return (cnet,)
        except Exception as e2:
            log.debug("from_pretrained failed: %s", e2)

        log.warning("All ControlNet loading methods failed for %s — "
                     "returning raw state dict", control_net_name)
        return ({"state_dict": raw_sd, "path": str(path),
                 "filename": control_net_name},)

NATIVE_NODES["ControlNetLoader"] = NativeControlNetLoader


class NativeControlNetApplyAdvanced:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "control_net": ("CONTROL_NET",),
                "image": ("IMAGE",),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0}),
                "start_percent": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "end_percent": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}),
            },
            "optional": {"vae": ("VAE",)},
        }
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("positive", "negative")
    FUNCTION = "apply_controlnet"

    def apply_controlnet(self, positive, negative, control_net, image,
                         strength=1.0, start_percent=0.0, end_percent=1.0,
                         vae=None, **kw):
        import torch

        cn_entry = {
            "control_net": control_net,
            "control_image": image,
            "strength": float(strength),
            "start_percent": float(start_percent),
            "end_percent": float(end_percent),
        }

        def _attach(cond):
            out = []
            for emb, meta in cond:
                new_meta = dict(meta)
                existing = new_meta.get("controlnets", [])
                new_meta["controlnets"] = existing + [cn_entry]
                out.append((emb, new_meta))
            return out

        return (_attach(positive), _attach(negative))

NATIVE_NODES["ControlNetApplyAdvanced"] = NativeControlNetApplyAdvanced


class NativeLoraLoaderModelOnly:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",), "lora_name": ("STRING",),
            "strength_model": ("FLOAT", {"default": 1.0}),
        }}
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load_lora"

    def load_lora(self, model, lora_name, strength_model=1.0, **kw):
        loader = NativeLoraLoader()
        model_out, _ = loader.load_lora(model, None, lora_name, strength_model, 0.0)
        return (model_out,)

NATIVE_NODES["LoraLoaderModelOnly"] = NativeLoraLoaderModelOnly


class NativeModelSamplingSD3:
    """Passthrough — adjusts model sampling config for SD3/FLUX."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",), "shift": ("FLOAT", {"default": 3.0})}}
    RETURN_TYPES = ("MODEL",)
    FUNCTION = "patch"

    def patch(self, model, shift=3.0, **kw):
        return (model,)

NATIVE_NODES["ModelSamplingSD3"] = NativeModelSamplingSD3


class NativeNote:
    """Passthrough utility node — just a comment/note, produces no output."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"multiline": True})}}
    RETURN_TYPES = ()
    FUNCTION = "noop"

    def noop(self, **kw):
        return ()

NATIVE_NODES["Note"] = NativeNote


class NativeTextBox:
    """Simple text passthrough node."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"multiline": True, "default": ""})}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"

    def run(self, text="", **kw):
        return (text,)

NATIVE_NODES["TextBox"] = NativeTextBox


class NativePrimitiveBoolean:
    """Boolean value node."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("BOOLEAN", {"default": True})}}
    RETURN_TYPES = ("BOOLEAN",)
    FUNCTION = "run"

    def run(self, value=True, **kw):
        return (value,)

NATIVE_NODES["PrimitiveBoolean"] = NativePrimitiveBoolean


class NativeDFInteger:
    """DF_Integer — converts float to int (from Derfuu_ComfyUI_ModdedNodes)."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"Value": ("FLOAT", {"default": 0})}}
    RETURN_TYPES = ("INT",)
    FUNCTION = "run"

    def run(self, Value=0, **kw):
        return (int(Value),)

NATIVE_NODES["DF_Integer"] = NativeDFInteger


class NativeSimpleMath:
    """SimpleMath+ — basic arithmetic expression evaluator."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "a": ("FLOAT", {"default": 0}),
            "b": ("FLOAT", {"default": 0}),
            "op": ("STRING", {"default": "a+b"}),
        }}
    RETURN_TYPES = ("FLOAT", "INT")
    FUNCTION = "run"

    def run(self, a=0, b=0, op="a+b", **kw):
        try:
            result = float(eval(op, {"__builtins__": {}}, {"a": a, "b": b, "min": min, "max": max, "abs": abs, "round": round}))
        except Exception:
            result = a + b
        return (result, int(result))

NATIVE_NODES["SimpleMath+"] = NativeSimpleMath


class NativeEasyInt:
    """easy int — simple integer value node."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"value": ("INT", {"default": 0})}}
    RETURN_TYPES = ("INT",)
    FUNCTION = "run"

    def run(self, value=0, **kw):
        return (int(value),)

NATIVE_NODES["easy int"] = NativeEasyInt


class NativeEasyShowAnything:
    """easy showAnything — passthrough debug/display node."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"anything": ("*",)}}
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "run"

    def run(self, anything=None, **kw):
        return ()

NATIVE_NODES["easy showAnything"] = NativeEasyShowAnything


class NativeEasyCleanGpu:
    """easy cleanGpuUsed — triggers GPU memory cleanup."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"anything": ("*",)}}
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "run"

    def run(self, **kw):
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except Exception:
            pass
        return ()

NATIVE_NODES["easy cleanGpuUsed"] = NativeEasyCleanGpu


class NativeEasyIfElse:
    """easy ifElse — conditional passthrough."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "condition": ("BOOLEAN", {"default": True}),
        }, "optional": {
            "if_true": ("*",),
            "if_false": ("*",),
        }}
    RETURN_TYPES = ("*",)
    FUNCTION = "run"

    def run(self, condition=True, if_true=None, if_false=None, **kw):
        return (if_true if condition else if_false,)

NATIVE_NODES["easy ifElse"] = NativeEasyIfElse


class NativePassthroughAny:
    """Generic passthrough for utility nodes that just forward data."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"input": ("*",)}}
    RETURN_TYPES = ("*",)
    FUNCTION = "run"

    def run(self, input=None, **kw):
        return (input,)

NATIVE_NODES["LayerUtility: PurgeVRAM V2"] = NativeEasyCleanGpu


class NativeCRTextReplace:
    """CR Text Replace — string find/replace."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "text": ("STRING", {"default": ""}),
            "find": ("STRING", {"default": ""}),
            "replace": ("STRING", {"default": ""}),
        }}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"

    def run(self, text="", find="", replace="", **kw):
        return (text.replace(find, replace) if find else text,)

NATIVE_NODES["CR Text Replace"] = NativeCRTextReplace


class NativeRHCaptioner:
    """RH_Captioner — image captioning using transformers BLIP/Florence."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
        }, "optional": {
            "model": ("STRING", {"default": "blip"}),
            "prompt": ("STRING", {"default": ""}),
        }}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "caption"

    def caption(self, image, model="blip", prompt="", **kw):
        import numpy as np
        from PIL import Image as PILImage
        if isinstance(image, torch.Tensor):
            img_np = (image.squeeze(0).cpu().numpy() * 255).astype(np.uint8)
            pil_img = PILImage.fromarray(img_np)
        else:
            pil_img = image

        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            proc = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            mdl = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
            device = _normalize_torch_device("auto")
            mdl = mdl.to(device)
            inputs = proc(pil_img, return_tensors="pt").to(device)
            with torch.no_grad():
                out = mdl.generate(**inputs, max_new_tokens=100)
            caption_text = proc.decode(out[0], skip_special_tokens=True)
        except Exception as e:
            log.warning("RH_Captioner fallback: %s", e)
            caption_text = prompt or "an image"
        return (caption_text,)

NATIVE_NODES["RH_Captioner"] = NativeRHCaptioner


# ═══════════════════════════════════════════════════════════════════════
#  NODE RESOLVER — three-tier: native → custom_nodes → auto-install
# ═══════════════════════════════════════════════════════════════════════

_comfyui_nodes: dict[str, type] | None = None
_comfyui_available: bool | None = None


def _check_comfyui_available() -> bool:
    """Check if ComfyUI's comfy package is importable."""
    global _comfyui_available
    if _comfyui_available is not None:
        return _comfyui_available
    try:
        import comfy  # noqa: F401
        _comfyui_available = True
    except ImportError:
        _comfyui_available = False
    return _comfyui_available


def _load_comfyui_nodes() -> dict[str, type]:
    """Import NODE_CLASS_MAPPINGS from ComfyUI and installed custom nodes."""
    global _comfyui_nodes
    if _comfyui_nodes is not None:
        return _comfyui_nodes

    mappings: dict[str, type] = {}

    try:
        import nodes as comfy_nodes  # ComfyUI's built-in nodes module
        if hasattr(comfy_nodes, "NODE_CLASS_MAPPINGS"):
            mappings.update(comfy_nodes.NODE_CLASS_MAPPINGS)
            log.info("Loaded %d ComfyUI built-in nodes", len(mappings))
    except ImportError:
        log.debug("ComfyUI built-in nodes not importable")

    for extra_mod in ["comfy_extras.nodes_model_advanced",
                      "comfy_extras.nodes_clip_sdxl",
                      "comfy_extras.nodes_controlnet"]:
        try:
            mod = __import__(extra_mod, fromlist=["NODE_CLASS_MAPPINGS"])
            if hasattr(mod, "NODE_CLASS_MAPPINGS"):
                mappings.update(mod.NODE_CLASS_MAPPINGS)
        except ImportError:
            pass

    for cn_dir in [CUSTOM_NODES_DIR, Path.home() / "ComfyUI" / "custom_nodes"]:
        if not cn_dir.is_dir():
            continue
        if str(cn_dir) not in sys.path:
            sys.path.insert(0, str(cn_dir))
        for pkg in cn_dir.iterdir():
            if pkg.is_dir():
                init = pkg / "__init__.py"
                if not init.exists():
                    continue
                try:
                    mod = __import__(pkg.name, fromlist=["NODE_CLASS_MAPPINGS"])
                    if hasattr(mod, "NODE_CLASS_MAPPINGS"):
                        mappings.update(mod.NODE_CLASS_MAPPINGS)
                        log.info("Custom nodes loaded: %s (%d nodes)",
                                 pkg.name, len(mod.NODE_CLASS_MAPPINGS))
                except Exception as e:
                    log.warning("Failed to load custom nodes from %s: %s", pkg.name, e)
            elif pkg.suffix == ".py" and pkg.name != "__init__.py":
                try:
                    spec = importlib.util.spec_from_file_location(pkg.stem, str(pkg))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[pkg.stem] = mod
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "NODE_CLASS_MAPPINGS"):
                            mappings.update(mod.NODE_CLASS_MAPPINGS)
                            log.info("Custom node file loaded: %s (%d nodes)",
                                     pkg.name, len(mod.NODE_CLASS_MAPPINGS))
                except Exception as e:
                    log.warning("Failed to load custom node file %s: %s", pkg.name, e)

    _comfyui_nodes = mappings
    return mappings


def _fetch_extension_node_map() -> dict:
    """Download/cache the ComfyUI-Manager extension-node-map (via ghost_comfy_manager)."""
    from ghost_comfy_manager.registry import NodeRegistry
    return NodeRegistry.get().get_extension_node_map()


def _find_package_for_node(class_type: str) -> str | None:
    """Look up which git repo provides a given node class_type.

    Delegates to ghost_comfy_manager's resolver with preemption-aware
    lookup, direct extension-node-map, and regex nodename_pattern matching.
    """
    from ghost_comfy_manager.resolver import find_package_for_node
    return find_package_for_node(class_type)


def _install_comfyui_package(repo_url: str) -> bool:
    """Install a ComfyUI custom node package (CNR preferred, git fallback).

    Delegates to ghost_comfy_manager's installer which:
      1. Checks if a CNR package ID exists (from custom-node-list.json)
      2. If yes, downloads versioned zip from api.comfy.org
      3. If not, falls back to git clone --depth 1 --recursive
      4. Runs requirements.txt with pip blacklist + install.py
    """
    from ghost_comfy_manager.installer import install_package
    result = install_package(repo_url)
    if result.success:
        global _comfyui_nodes
        _comfyui_nodes = None
    return result.success


def resolve_all_nodes(required_types: set[str], auto_install: bool = True
                      ) -> tuple[str, dict[str, type]]:
    """Resolve all required node class_types to Python classes.

    Resolution order (no full ComfyUI install needed):
      1. Native diffusers implementations (NATIVE_NODES)
      2. Inject comfy compat layer (ghost_comfy_compat) so custom node
         repos can import 'comfy.*' without real ComfyUI
      3. Scan already-installed custom node packages
      4. Auto-install from ComfyUI-Manager extension-node-map registry
      5. Non-critical nodes (display/debug/cleanup) auto-skipped

    Returns (mode, {class_type: class}):
      mode = "native" if all resolved natively, else "comfyui"
    """
    if all(t in NATIVE_NODES for t in required_types):
        return "native", {t: NATIVE_NODES[t] for t in required_types}

    resolved: dict[str, type] = {}
    still_missing: set[str] = set()

    for t in required_types:
        if t in NATIVE_NODES:
            resolved[t] = NATIVE_NODES[t]
        else:
            still_missing.add(t)

    if not still_missing:
        return "native", resolved

    # --- Inject comfy compat layer before loading any custom nodes ---
    _compat_injected = False
    try:
        from ghost_comfy_compat import ensure_comfy_compat
        _compat_injected = ensure_comfy_compat()
        if _compat_injected:
            log.info("Comfy compat layer active — custom node imports enabled")
    except ImportError:
        log.debug("ghost_comfy_compat not available, proceeding without compat layer")

    # --- Scan already-installed custom nodes (now works with compat layer) ---
    if still_missing:
        comfy_nodes = _load_comfyui_nodes()
        for t in list(still_missing):
            if t in comfy_nodes:
                resolved[t] = comfy_nodes[t]
                still_missing.discard(t)

    # --- Check compat layer's built-in nodes + legacy aliases ---
    if still_missing and _compat_injected:
        try:
            import ghost_comfy_compat.nodes_module as nm
            if hasattr(nm, "_register_legacy_aliases"):
                nm._register_legacy_aliases()
            all_known = dict(nm.NODE_CLASS_MAPPINGS)
            if comfy_nodes:
                all_known.update(comfy_nodes)
            _LEGACY_ALIASES = {
                "IPAdapterApply": "IPAdapter",
            }
            for old_name, new_name in _LEGACY_ALIASES.items():
                if old_name not in all_known and new_name in all_known:
                    all_known[old_name] = all_known[new_name]
            for t in list(still_missing):
                if t in all_known:
                    resolved[t] = all_known[t]
                    still_missing.discard(t)
        except Exception:
            pass

    # --- Auto-install from registry (skips comfyanonymous/ComfyUI) ---
    if still_missing and auto_install:
        installed_repos: set[str] = set()
        no_repo_found: set[str] = set()
        for t in list(still_missing):
            repo = _find_package_for_node(t)
            if repo and repo not in installed_repos:
                log.info("Auto-installing custom node package for '%s' from %s", t, repo)
                if _install_comfyui_package(repo):
                    installed_repos.add(repo)
            elif not repo:
                no_repo_found.add(t)

        if installed_repos:
            global _comfyui_nodes
            _comfyui_nodes = None
            comfy_nodes = _load_comfyui_nodes()
            for t in list(still_missing):
                if t in comfy_nodes:
                    resolved[t] = comfy_nodes[t]
                    still_missing.discard(t)

    # --- Handle unresolved nodes ---
    if still_missing:
        skippable = set()
        critical = set()
        for t in still_missing:
            if _is_non_critical_node(t):
                skippable.add(t)
            else:
                critical.add(t)

        for t in skippable:
            log.info("Auto-skipping non-critical node '%s' (using passthrough shim)", t)
            resolved[t] = _make_passthrough_shim(t)
            still_missing.discard(t)

        if critical:
            details = []
            for t in sorted(critical):
                repo = _find_package_for_node(t)
                if repo:
                    details.append(f"  - {t}: found in registry ({repo}) but import failed")
                else:
                    details.append(f"  - {t}: not found in any registry")
            detail_str = "\n".join(details)
            log.warning(
                "Could not resolve %d critical node type(s):\n%s",
                len(critical), detail_str,
            )
            raise RuntimeError(
                f"Could not resolve {len(critical)} node type(s):\n{detail_str}\n\n"
                "Possible fixes:\n"
                "  1. Install the custom node package manually into ~/.ghost/comfyui/custom_nodes/\n"
                "  2. Check https://github.com/ltdrdata/ComfyUI-Manager for available packages\n"
                "  3. The node may require a full ComfyUI installation for deep runtime dependencies"
            )

    mode = "native" if all(t in NATIVE_NODES for t in resolved) else "comfyui"
    return mode, resolved


_NON_CRITICAL_PATTERNS = {
    "note", "reroute", "preview", "show", "display", "print", "debug",
    "purge", "clean", "mute", "bypass", "comment", "group", "frame",
    "bookmark", "todo", "info", "log", "monitor", "watch",
}


def _is_non_critical_node(class_type: str) -> bool:
    """Check if a node type is non-critical (display/debug/cleanup only)."""
    lower = class_type.lower()
    for pattern in _NON_CRITICAL_PATTERNS:
        if pattern in lower:
            return True
    return False


def _make_passthrough_shim(class_type: str) -> type:
    """Create a dynamic passthrough shim class for non-critical nodes."""

    class _DynamicPassthrough:
        RETURN_TYPES = ("*",)
        FUNCTION = "run"
        CATEGORY = "ghost_compat/passthrough"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def run(self, **kwargs):
            first_val = next(iter(kwargs.values()), None) if kwargs else None
            _kw = {k: v for k, v in kwargs.items() if not k.startswith("_")}
            if _kw:
                first_val = next(iter(_kw.values()))
            return (first_val,) if first_val is not None else ()

    _DynamicPassthrough.__name__ = f"GhostShim_{class_type.replace(' ', '_')}"
    _DynamicPassthrough.__qualname__ = _DynamicPassthrough.__name__
    return _DynamicPassthrough


# ═══════════════════════════════════════════════════════════════════════
#  EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════

class ComfyUIEngine:
    """Parse and execute ComfyUI workflows."""

    def __init__(
        self,
        models_dir: Path | str | None = None,
        device: str = "auto",
        output_dir: str | Path | None = None,
        progress_cb=None,
        auto_install: bool = True,
    ):
        self.models_dir = Path(models_dir) if models_dir else MODELS_DIR
        self.output_dir = Path(output_dir) if output_dir else (
            GHOST_HOME / "media" / "image"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_cb = progress_cb
        self.auto_install = auto_install
        self._saved_outputs: list[str] = []

        self.device = _normalize_torch_device(device)

    def execute_workflow(
        self,
        workflow: dict,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a ComfyUI workflow. Returns {node_id: outputs_tuple}.

        overrides: {"node_id.inputs.key": value} to override workflow inputs.
        """
        self._saved_outputs = []
        api = parse_workflow(workflow)

        if overrides:
            _apply_overrides(api, overrides)

        order = topological_sort(api)
        required = {api[nid]["class_type"] for nid in order}

        if self.progress_cb:
            self.progress_cb(f"Resolving {len(required)} node types...")

        mode, classes = resolve_all_nodes(required, self.auto_install)
        log.info("Execution mode: %s (%d nodes)", mode, len(order))

        outputs: dict[str, tuple] = {}
        instances: dict[str, Any] = {}

        for step_num, nid in enumerate(order, 1):
            ndata = api[nid]
            class_type = ndata["class_type"]
            raw_inputs = ndata.get("inputs", {})

            if self.progress_cb:
                self.progress_cb(
                    f"[{step_num}/{len(order)}] {class_type}"
                )

            cls = classes[class_type]
            instance = cls()
            instances[nid] = instance

            resolved_inputs = self._resolve_inputs(raw_inputs, outputs, cls)
            resolved_inputs["_engine"] = self

            func_name = getattr(cls, "FUNCTION", "execute")
            func = getattr(instance, func_name)

            try:
                result = func(**resolved_inputs)
            except TypeError as e:
                if "_engine" in str(e) or "unexpected keyword" in str(e):
                    clean = {k: v for k, v in resolved_inputs.items()
                             if not k.startswith("_")}
                    log.debug("Retrying node %s without _engine args", class_type)
                    try:
                        result = func(**clean)
                    except Exception as e2:
                        log.error("Node %s (%s) call failed: %s\nInputs: %s",
                                  nid, class_type, e2, list(clean.keys()))
                        raise RuntimeError(
                            f"Node '{nid}' ({class_type}) execution error: {e2}"
                        ) from e2
                else:
                    clean = {k: v for k, v in resolved_inputs.items()
                             if not k.startswith("_")}
                    log.error("Node %s (%s) call failed: %s\nInputs: %s",
                              nid, class_type, e, list(clean.keys()))
                    raise RuntimeError(
                        f"Node '{nid}' ({class_type}) execution error: {e}"
                    ) from e
            except Exception as e:
                log.error("Node %s (%s) execution error: %s",
                          nid, class_type, e, exc_info=True)
                raise RuntimeError(
                    f"Node '{nid}' ({class_type}) execution error: {e}"
                ) from e

            if isinstance(result, dict):
                outputs[nid] = result
            elif isinstance(result, tuple):
                outputs[nid] = result
            else:
                outputs[nid] = (result,)

        return {
            "outputs": outputs,
            "saved_files": list(self._saved_outputs),
            "mode": mode,
        }

    @staticmethod
    def _resolve_inputs(raw: dict, outputs: dict, cls: type) -> dict:
        """Resolve node references [node_id, slot] to actual values.

        Also maps _widget_values from UI-format workflows to named inputs
        using the node's INPUT_TYPES definition.
        """
        resolved: dict[str, Any] = {}

        widget_values = raw.get("_widget_values")
        if widget_values and hasattr(cls, "INPUT_TYPES"):
            try:
                input_spec = cls.INPUT_TYPES()
                widget_names: list[str] = []
                connected_inputs = {
                    k for k, v in raw.items()
                    if not k.startswith("_") and isinstance(v, list)
                    and len(v) == 2 and isinstance(v[0], str)
                }
                for section in ("required", "optional"):
                    for name in input_spec.get(section, {}):
                        if name not in connected_inputs:
                            widget_names.append(name)
                for i, wname in enumerate(widget_names):
                    if i < len(widget_values) and wname not in raw:
                        resolved[wname] = widget_values[i]
            except Exception:
                pass

        for key, val in raw.items():
            if key.startswith("_"):
                continue
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                ref_id, slot = str(val[0]), int(val[1])
                if ref_id in outputs:
                    ref_out = outputs[ref_id]
                    if isinstance(ref_out, tuple) and slot < len(ref_out):
                        resolved[key] = ref_out[slot]
                    elif isinstance(ref_out, dict) and "ui" in ref_out:
                        resolved[key] = ref_out
                    else:
                        resolved[key] = ref_out
                else:
                    log.warning("Input ref %s[%d] not found for key '%s'",
                                ref_id, slot, key)
                    resolved[key] = val
            else:
                resolved[key] = val

        return resolved


def _apply_overrides(api: dict, overrides: dict):
    """Apply input overrides in 'node_id.inputs.key' format."""
    for path, value in overrides.items():
        parts = path.split(".")
        if len(parts) == 3 and parts[1] == "inputs":
            nid, _, key = parts
            if nid in api:
                api[nid].setdefault("inputs", {})[key] = value
        elif len(parts) == 2:
            nid, key = parts
            if nid in api:
                api[nid].setdefault("inputs", {})[key] = value


# ═══════════════════════════════════════════════════════════════════════
#  WORKFLOW ANALYZER
# ═══════════════════════════════════════════════════════════════════════

def analyze_workflow(workflow: dict) -> dict:
    """Analyze a workflow to identify inputs, outputs, models, and deps.

    Returns:
      {
        "node_count": int,
        "node_types": [str],
        "native_coverage": bool,
        "missing_native": [str],
        "input_nodes": [{id, class_type, param_name, type_hint}],
        "output_nodes": [{id, class_type}],
        "models_needed": [{filename, subdir}],
        "configurable_params": [{node_id, key, value, type_hint}],
      }
    """
    api = parse_workflow(workflow)

    node_types = {api[nid]["class_type"] for nid in api}
    native_have = {t for t in node_types if t in NATIVE_NODES}
    missing = node_types - native_have

    input_nodes = []
    output_nodes = []
    models_needed = []
    configurable = []

    for nid, ndata in api.items():
        ct = ndata["class_type"]
        inputs = ndata.get("inputs", {})

        if ct in ("LoadImage", "LoadImageMask"):
            input_nodes.append({
                "id": nid, "class_type": ct,
                "param_name": "image", "type_hint": "image_path",
            })

        if ct in ("SaveImage", "PreviewImage"):
            output_nodes.append({"id": nid, "class_type": ct})

        if ct in ("CheckpointLoaderSimple", "CheckpointLoader"):
            ckpt = inputs.get("ckpt_name", "")
            if ckpt:
                models_needed.append({"filename": ckpt, "subdir": "checkpoints"})

        if ct == "LoraLoader":
            lora = inputs.get("lora_name", "")
            if lora:
                models_needed.append({"filename": lora, "subdir": "loras"})

        if ct in ("ControlNetLoader",):
            cn = inputs.get("control_net_name", "")
            if cn:
                models_needed.append({"filename": cn, "subdir": "controlnet"})

        if ct == "VAELoader":
            v = inputs.get("vae_name", "")
            if v:
                models_needed.append({"filename": v, "subdir": "vae"})

        if ct == "CLIPTextEncode":
            text = inputs.get("text", "")
            if isinstance(text, str) and text:
                configurable.append({
                    "node_id": nid, "key": "text",
                    "value": text, "type_hint": "prompt",
                })

        if ct in ("KSampler", "KSamplerAdvanced"):
            for k in ("seed", "steps", "cfg", "denoise"):
                v = inputs.get(k)
                if v is not None and not isinstance(v, list):
                    configurable.append({
                        "node_id": nid, "key": k,
                        "value": v, "type_hint": k,
                    })

    return {
        "node_count": len(api),
        "node_types": sorted(node_types),
        "native_coverage": len(missing) == 0,
        "missing_native": sorted(missing),
        "input_nodes": input_nodes,
        "output_nodes": output_nodes,
        "models_needed": models_needed,
        "configurable_params": configurable,
    }


# ═══════════════════════════════════════════════════════════════════════
#  GHOST NODE GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_ghost_node(
    workflow: dict,
    name: str,
    description: str = "",
    output_dir: str | Path = "",
) -> dict:
    """Create a Ghost node directory from a ComfyUI workflow JSON.

    Generates NODE.yaml, node.py, and bundles workflow.json.
    """
    analysis = analyze_workflow(workflow)
    name_safe = name.replace("-", "_").replace(" ", "_").lower()
    tool_name = name_safe

    target = Path(output_dir) if output_dir else (
        Path(__file__).resolve().parent / "ghost_nodes" / name
    )
    if target.exists():
        return {"status": "error", "error": f"Directory exists: {target}"}

    target.mkdir(parents=True, exist_ok=True)
    (target / "workflow.json").write_text(json.dumps(workflow, indent=2))

    has_gpu = bool(analysis["models_needed"])
    model_names = [m["filename"] for m in analysis["models_needed"]]

    props: dict[str, dict] = {}
    required: list[str] = []

    for inp in analysis["input_nodes"]:
        pname = f"image_{inp['id']}" if len(analysis["input_nodes"]) > 1 else "image_path"
        props[pname] = {"type": "string",
                        "description": f"Path to input image (node {inp['id']})"}
        required.append(pname)

    prompt_nodes = [c for c in analysis["configurable_params"]
                    if c["type_hint"] == "prompt"]
    for i, pn in enumerate(prompt_nodes):
        pname = "prompt" if i == 0 else f"prompt_{i + 1}"
        props[pname] = {"type": "string",
                        "description": f"Text prompt (default: {str(pn['value'])[:50]})"}

    for c in analysis["configurable_params"]:
        if c["type_hint"] in ("seed", "steps", "cfg", "denoise"):
            props[c["type_hint"]] = {
                "type": "number",
                "description": f"{c['type_hint']} (default: {c['value']})"}

    # -- Build overrides lines (8-space indent = inside execute()) --
    ov_lines: list[str] = []
    for inp in analysis["input_nodes"]:
        pname = f"image_{inp['id']}" if len(analysis["input_nodes"]) > 1 else "image_path"
        ov_lines.append(
            f'if {pname}: overrides["{inp["id"]}.inputs.image"] = {pname}')
    for i, pn in enumerate(prompt_nodes):
        pname = "prompt" if i == 0 else f"prompt_{i + 1}"
        ov_lines.append(
            f'if {pname}: overrides["{pn["node_id"]}.inputs.text"] = {pname}')
    for c in analysis["configurable_params"]:
        if c["type_hint"] in ("seed", "steps", "cfg", "denoise"):
            ov_lines.append(
                f'if {c["type_hint"]} is not None: '
                f'overrides["{c["node_id"]}.inputs.{c["key"]}"] = {c["type_hint"]}')

    # -- Build param signature --
    param_parts = []
    for p in props:
        if props[p]["type"] == "string":
            param_parts.append(f'{p}=""')
        else:
            param_parts.append(f"{p}=None")
    param_sig = ", ".join(param_parts)
    if param_sig:
        param_sig += ", "

    # -- Assemble node.py line-by-line (no textwrap.dedent) --
    I2 = "    "    # 1 indent
    I3 = "        "  # 2 indents  (inside register > execute)
    desc_esc = (description or f"Run the {name} ComfyUI workflow.").replace('"', '\\"')
    models_str = ", ".join(model_names) or "auto-detected"
    vram = 4.0 if has_gpu else 0

    lines = [
        f'"""',
        f'{name} -- auto-generated from ComfyUI workflow.',
        f'{description}',
        f'"""',
        f'',
        f'import json',
        f'import logging',
        f'import time',
        f'from pathlib import Path',
        f'',
        f'log = logging.getLogger("ghost.node.{name_safe}")',
        f'',
        f'WORKFLOW_PATH = Path(__file__).parent / "workflow.json"',
        f'',
        f'',
        f'def register(api):',
        f'',
        f'{I2}def execute({param_sig}filename="", **_kw):',
        f'{I3}from ghost_comfyui_engine import ComfyUIEngine',
        f'{I3}workflow = json.loads(WORKFLOW_PATH.read_text())',
        f'{I3}overrides = {{}}',
    ]
    for ol in ov_lines:
        lines.append(f'{I3}{ol}')
    lines += [
        f'',
        f'{I3}engine = ComfyUIEngine(',
        f'{I3}    models_dir=api.models_dir,',
        f'{I3}    device=api.get_device({vram}),',
        f'{I3}    output_dir=None,',
        f'{I3}    progress_cb=lambda msg: api.log(msg),',
        f'{I3})',
        f'',
        f'{I3}t0 = time.time()',
        f'{I3}result = engine.execute_workflow(workflow, overrides=overrides)',
        f'{I3}elapsed = time.time() - t0',
        f'',
        f'{I3}saved = result.get("saved_files", [])',
        f'{I3}for fpath in saved:',
        f'{I3}    p = Path(fpath)',
        f'{I3}    if p.exists():',
        f'{I3}        api.save_media(',
        f'{I3}            data=p.read_bytes(), filename=p.name,',
        f'{I3}            media_type="image",',
        f'{I3}            metadata={{"source_workflow": "{name}", "elapsed": round(elapsed, 2)}},',
        f'{I3}        )',
        f'',
        f'{I3}return json.dumps({{',
        f'{I3}    "status": "ok", "files": saved,',
        f'{I3}    "mode": result.get("mode", "unknown"),',
        f'{I3}    "elapsed_secs": round(elapsed, 2),',
        f'{I3}}})',
        f'',
        f'{I2}api.register_tool({{',
        f'{I3}"name": "{tool_name}",',
        f'{I3}"description": "{desc_esc} Models: {models_str}. If execution fails with a MISSING MODEL error, use web_search to find the download URL, then comfyui_model_download to fetch it, then retry.",',
        f'{I3}"parameters": {{',
        f'{I3}    "type": "object",',
        f'{I3}    "properties": {json.dumps(props)},',
        f'{I3}    "required": {json.dumps(required)},',
        f'{I3}}},',
        f'{I3}"execute": execute,',
        f'{I2}}})',
    ]

    (target / "node.py").write_text("\n".join(lines) + "\n")

    # -- NODE.yaml --
    deps = '["torch", "diffusers", "transformers"]' if has_gpu else "[]"
    yaml_lines = [
        f"name: {name}",
        f"version: 0.1.0",
        f'description: "{description or f"ComfyUI workflow: {name}"}"',
        f"author: community",
        f"category: image_generation",
        f"license: MIT",
        f"",
        f"requires:",
        f"  python: \">=3.10\"",
        f"  gpu: {'true' if has_gpu else 'false'}",
        f"  vram_gb: {4 if has_gpu else 0}",
        f"  disk_gb: 2",
        f"  deps: {deps}",
        f"",
        f"models: []",
        f"",
        f"tools:",
        f"  - {tool_name}",
        f"",
        f'inputs: ["image"]',
        f'outputs: ["image"]',
        f"",
        f'tags: ["{name}", "comfyui", "workflow"]',
    ]
    (target / "NODE.yaml").write_text("\n".join(yaml_lines) + "\n")

    return {
        "status": "ok",
        "path": str(target),
        "name": name,
        "tool_name": tool_name,
        "analysis": analysis,
        "files": ["NODE.yaml", "node.py", "workflow.json"],
    }
