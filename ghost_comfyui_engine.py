"""
ComfyUI Workflow Engine for Ghost — run community workflows natively.

Three-tier node resolution:
  1. Native (diffusers-based, ~13 core nodes, zero comfyui dependency)
  2. ComfyUI built-in (from installed 'comfy' package or local ComfyUI)
  3. Custom (auto-installed from ComfyUI-Manager registry on demand)

If ALL nodes in a workflow are covered by native implementations, the engine
runs without any ComfyUI dependency.  If even one node requires ComfyUI,
the engine switches entirely to ComfyUI mode for type compatibility.

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
NODE_MAP_PATH = COMFYUI_CACHE / "extension-node-map.json"
NODE_MAP_URL = (
    "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager"
    "/main/extension-node-map.json"
)
MODEL_LIST_URL = (
    "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager"
    "/main/model-list.json"
)
MODEL_LIST_CACHE = COMFYUI_CACHE / "model-list.json"
_MODEL_LIST_MAX_AGE = 86400 * 7  # refresh weekly

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
        f"Model not found and no download source: {filename}\n"
        f"Searched locally + ComfyUI-Manager registry + HuggingFace.\n"
        f"Place the file manually in: {fallback_dir}/"
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
    """Fetch and cache ComfyUI-Manager's model-list.json."""
    global _model_list_data
    if _model_list_data is not None:
        return _model_list_data

    if (MODEL_LIST_CACHE.exists()
            and time.time() - MODEL_LIST_CACHE.stat().st_mtime < _MODEL_LIST_MAX_AGE):
        try:
            data = json.loads(MODEL_LIST_CACHE.read_text())
            _model_list_data = data.get("models", data) if isinstance(data, dict) else data
            return _model_list_data
        except Exception:
            pass

    import urllib.request
    log.info("Fetching ComfyUI model registry from %s", MODEL_LIST_URL)
    try:
        req = urllib.request.Request(MODEL_LIST_URL, headers={"User-Agent": "Ghost/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        MODEL_LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MODEL_LIST_CACHE.write_bytes(raw)
        data = json.loads(raw)
        _model_list_data = data.get("models", data) if isinstance(data, dict) else data
        log.info("Model registry loaded: %d entries", len(_model_list_data))
        return _model_list_data
    except Exception as e:
        log.warning("Failed to fetch model list: %s", e)
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
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "generate"

    def generate(self, width=512, height=512, batch_size=1, **kw):
        import torch
        latent = torch.zeros(int(batch_size), 4, int(height) // 8, int(width) // 8)
        return ({"samples": latent},)


NATIVE_NODES["EmptyLatentImage"] = NativeEmptyLatentImage


class NativeLoadImage:
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


# ═══════════════════════════════════════════════════════════════════════
#  NODE RESOLVER — three-tier: native → comfyui → auto-install
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
    """Download/cache the ComfyUI-Manager extension-node-map."""
    if NODE_MAP_PATH.exists():
        age_hours = (time.time() - NODE_MAP_PATH.stat().st_mtime) / 3600
        if age_hours < 24:
            try:
                return json.loads(NODE_MAP_PATH.read_text())
            except Exception:
                pass

    log.info("Fetching ComfyUI extension-node-map...")
    try:
        import requests
        resp = requests.get(NODE_MAP_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        NODE_MAP_PATH.write_text(json.dumps(data, indent=2))
        return data
    except Exception as e:
        log.warning("Failed to fetch extension-node-map: %s", e)
        if NODE_MAP_PATH.exists():
            return json.loads(NODE_MAP_PATH.read_text())
        return {}


def _find_package_for_node(class_type: str) -> str | None:
    """Look up which git repo provides a given node class_type.

    extension-node-map.json format:
      {repo_url: [["NodeA", "NodeB"], {"title_aux": "..."}]}
    The value is a 2-element list: [node_names, metadata].
    """
    ext_map = _fetch_extension_node_map()
    for repo_url, entry in ext_map.items():
        if isinstance(entry, list) and len(entry) >= 1:
            node_names = entry[0] if isinstance(entry[0], list) else entry
            if class_type in node_names:
                return repo_url
        elif isinstance(entry, dict):
            nodes = entry.get("nodenames", entry.get("nodes", []))
            if class_type in nodes:
                return repo_url
    return None


def _install_comfyui_package(repo_url: str) -> bool:
    """Clone a ComfyUI custom node repo and install its dependencies.

    ComfyUI custom nodes are plain directories with __init__.py and
    NODE_CLASS_MAPPINGS — not pip packages. This mirrors how
    ComfyUI-Manager installs: git clone, then pip install -r requirements.txt.
    """
    log.info("Auto-installing custom node package: %s", repo_url)
    CUSTOM_NODES_DIR.mkdir(parents=True, exist_ok=True)

    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    dest = CUSTOM_NODES_DIR / repo_name

    try:
        if dest.exists():
            log.info("Custom node dir already exists: %s — pulling latest", dest)
            result = subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                log.warning("git pull failed for %s: %s", dest, result.stderr[:300])
        else:
            log.info("Cloning %s → %s", repo_url, dest)
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(dest)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                log.error("git clone failed for %s: %s", repo_url, result.stderr[:500])
                return False

        req_file = dest / "requirements.txt"
        if req_file.exists():
            log.info("Installing dependencies from %s", req_file)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file),
                 "--quiet", "--no-warn-script-location"],
                capture_output=True, text=True, timeout=300,
            )

        global _comfyui_nodes
        _comfyui_nodes = None
        return True
    except Exception as e:
        log.error("Install error for %s: %s", repo_url, e)
        return False


def resolve_all_nodes(required_types: set[str], auto_install: bool = True
                      ) -> tuple[str, dict[str, type]]:
    """Resolve all required node class_types to Python classes.

    Returns (mode, {class_type: class}):
      mode = "native" if all resolved natively, else "comfyui"
    """
    if all(t in NATIVE_NODES for t in required_types):
        return "native", {t: NATIVE_NODES[t] for t in required_types}

    if not _check_comfyui_available():
        native_have = {t for t in required_types if t in NATIVE_NODES}
        missing = required_types - native_have
        log.info(
            "Workflow needs non-native nodes: %s — "
            "install ComfyUI for full support (pip install comfyui)",
            missing,
        )
        if not auto_install:
            raise RuntimeError(
                f"Unsupported node types (ComfyUI not installed): {missing}\n"
                f"Install: pip install comfyui"
            )
        log.info("Attempting to install ComfyUI...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "comfyui", "--quiet"],
            capture_output=True, timeout=600,
        )
        global _comfyui_available
        _comfyui_available = None
        if not _check_comfyui_available():
            raise RuntimeError(
                f"Could not install ComfyUI. Missing nodes: {missing}\n"
                f"Manual install: pip install comfyui"
            )

    comfy_nodes = _load_comfyui_nodes()
    resolved: dict[str, type] = {}
    still_missing: set[str] = set()

    for t in required_types:
        if t in comfy_nodes:
            resolved[t] = comfy_nodes[t]
        elif t in NATIVE_NODES:
            resolved[t] = NATIVE_NODES[t]
        else:
            still_missing.add(t)

    if still_missing and auto_install:
        for t in list(still_missing):
            repo = _find_package_for_node(t)
            if repo:
                if _install_comfyui_package(repo):
                    comfy_nodes = _load_comfyui_nodes()
                    if t in comfy_nodes:
                        resolved[t] = comfy_nodes[t]
                        still_missing.discard(t)

    if still_missing:
        raise RuntimeError(
            f"Could not resolve node types: {still_missing}\n"
            "These may require custom ComfyUI nodes not yet in the registry."
        )

    mode = "native" if all(t in NATIVE_NODES for t in required_types) else "comfyui"
    return mode, resolved


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
                clean = {k: v for k, v in resolved_inputs.items()
                         if not k.startswith("_")}
                log.error("Node %s (%s) call failed: %s\nInputs: %s",
                          nid, class_type, e, list(clean.keys()))
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
        """Resolve node references [node_id, slot] to actual values."""
        resolved: dict[str, Any] = {}

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
        f'{I3}"description": "{desc_esc} Models: {models_str}.",',
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
