"""
Ghost compat: folder_paths module.

Full implementation of ComfyUI's folder_paths with real filesystem logic
pointing to ~/.ghost/models/ directory structure.
"""

import os
import time
from pathlib import Path

GHOST_HOME = Path.home() / ".ghost"
MODELS_DIR = GHOST_HOME / "models"

base_path = str(GHOST_HOME / "comfyui")
models_dir = str(MODELS_DIR)
output_directory = str(GHOST_HOME / "media" / "image")
temp_directory = str(GHOST_HOME / "comfyui" / "temp")
input_directory = str(GHOST_HOME / "media" / "input")

supported_pt_extensions = {
    ".ckpt", ".pt", ".bin", ".pth", ".safetensors", ".pkl", ".sft",
}

folder_names_and_paths: dict[str, tuple[list[str], set[str]]] = {
    "checkpoints": ([str(MODELS_DIR / "checkpoints")], supported_pt_extensions),
    "loras": ([str(MODELS_DIR / "loras")], supported_pt_extensions),
    "vae": ([str(MODELS_DIR / "vae")], supported_pt_extensions),
    "clip": ([str(MODELS_DIR / "clip")], supported_pt_extensions),
    "clip_vision": ([str(MODELS_DIR / "clip_vision")], supported_pt_extensions),
    "unet": ([str(MODELS_DIR / "unet")], supported_pt_extensions),
    "diffusion_models": ([str(MODELS_DIR / "unet"), str(MODELS_DIR / "diffusion_models")], supported_pt_extensions),
    "controlnet": ([str(MODELS_DIR / "controlnet")], supported_pt_extensions),
    "embeddings": ([str(MODELS_DIR / "embeddings")], supported_pt_extensions),
    "upscale_models": ([str(MODELS_DIR / "upscale_models")], supported_pt_extensions),
    "style_models": ([str(MODELS_DIR / "style_models")], supported_pt_extensions),
    "gligen": ([str(MODELS_DIR / "gligen")], supported_pt_extensions),
    "hypernetworks": ([str(MODELS_DIR / "hypernetworks")], supported_pt_extensions),
    "photomaker": ([str(MODELS_DIR / "photomaker")], supported_pt_extensions),
    "classifiers": ([str(MODELS_DIR / "classifiers")], supported_pt_extensions),
    "configs": ([str(MODELS_DIR / "configs")], {".yaml", ".json"}),
    "text_encoders": ([str(MODELS_DIR / "text_encoders")], supported_pt_extensions),
    "diffusers": ([str(MODELS_DIR / "diffusers")], set()),
    "vae_approx": ([str(MODELS_DIR / "vae_approx")], supported_pt_extensions),
}

filename_list_cache: dict[str, tuple[list[str], dict[str, float], float]] = {}

_legacy_map = {
    "unet": "diffusion_models",
}


def map_legacy(folder_name: str) -> str:
    return _legacy_map.get(folder_name, folder_name)


def add_model_folder_path(folder_name: str, full_folder_path: str, is_default: bool = False):
    full_folder_path = str(full_folder_path)
    if folder_name in folder_names_and_paths:
        dirs, exts = folder_names_and_paths[folder_name]
        if full_folder_path not in dirs:
            if is_default:
                dirs.insert(0, full_folder_path)
            else:
                dirs.append(full_folder_path)
    else:
        folder_names_and_paths[folder_name] = ([full_folder_path], supported_pt_extensions.copy())
    Path(full_folder_path).mkdir(parents=True, exist_ok=True)


def get_folder_paths(folder_name: str) -> list[str]:
    folder_name = map_legacy(folder_name)
    if folder_name in folder_names_and_paths:
        return list(folder_names_and_paths[folder_name][0])
    return []


def recursive_search(directory: str, excluded_dir_names: set | None = None) -> tuple[list[str], dict[str, float]]:
    if not os.path.isdir(directory):
        return [], {}

    if excluded_dir_names is None:
        excluded_dir_names = {".git", "__pycache__", "node_modules"}

    result: list[str] = []
    dirs: dict[str, float] = {}
    for root, dirnames, filenames in os.walk(directory, followlinks=True, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in excluded_dir_names]
        for f in filenames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, directory)
            result.append(rel)
            try:
                dirs[rel] = os.path.getmtime(full)
            except OSError:
                dirs[rel] = 0
    return result, dirs


def filter_files_extensions(files: list[str], extensions: set[str]) -> list[str]:
    if not extensions:
        return files
    return [f for f in files if any(f.lower().endswith(ext) for ext in extensions)]


def get_filename_list(folder_name: str) -> list[str]:
    folder_name = map_legacy(folder_name)
    if folder_name not in folder_names_and_paths:
        return []

    dirs, extensions = folder_names_and_paths[folder_name]
    if folder_name in filename_list_cache:
        cached_files, cached_dirs_ts, cache_time = filename_list_cache[folder_name]
        if time.time() - cache_time < 30:
            return cached_files

    output_list: list[str] = []
    dirs_ts: dict[str, float] = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        files, ts = recursive_search(d)
        filtered = filter_files_extensions(files, extensions)
        output_list.extend(filtered)
        dirs_ts.update(ts)

    filename_list_cache[folder_name] = (output_list, dirs_ts, time.time())
    return output_list


def get_full_path(folder_name: str, filename: str) -> str | None:
    folder_name = map_legacy(folder_name)
    if folder_name not in folder_names_and_paths:
        return None

    dirs, _ = folder_names_and_paths[folder_name]
    for d in dirs:
        full = os.path.join(d, filename)
        if os.path.isfile(full):
            return full
        for root, _, files in os.walk(d):
            if filename in files:
                return os.path.join(root, filename)
    return None


def get_full_path_or_raise(folder_name: str, filename: str) -> str:
    result = get_full_path(folder_name, filename)
    if result is None:
        raise FileNotFoundError(
            f"Model file '{filename}' not found in {folder_name} directories: "
            f"{get_folder_paths(folder_name)}"
        )
    return result


def get_output_directory() -> str:
    return output_directory


def get_temp_directory() -> str:
    return temp_directory


def get_input_directory() -> str:
    return input_directory


def get_save_image_path(filename_prefix: str, output_dir: str,
                        image_width: int = 0, image_height: int = 0) -> tuple:
    full_output = os.path.join(output_dir, os.path.dirname(filename_prefix))
    os.makedirs(full_output, exist_ok=True)

    base = os.path.basename(filename_prefix)
    if not base:
        base = "ComfyUI"

    counter = 1
    existing = os.listdir(full_output) if os.path.isdir(full_output) else []
    for f in existing:
        if f.startswith(base) and "_" in f:
            try:
                num = int(f.split("_")[-1].split(".")[0])
                counter = max(counter, num + 1)
            except (ValueError, IndexError):
                pass

    return full_output, base, counter, base, full_output


def annotated_filepath(name: str) -> tuple[str, str | None]:
    if name.endswith("[output]"):
        return name[:-9].strip(), output_directory
    if name.endswith("[input]"):
        return name[:-8].strip(), input_directory
    if name.endswith("[temp]"):
        return name[:-7].strip(), temp_directory
    return name, None


def get_annotated_filepath(name: str, default_dir: str | None = None) -> str:
    filename, dir_hint = annotated_filepath(name)
    if dir_hint:
        return os.path.join(dir_hint, filename)
    if default_dir:
        return os.path.join(default_dir, filename)
    return os.path.join(input_directory, filename)


def exists_annotated_filepath(name: str) -> bool:
    return os.path.exists(get_annotated_filepath(name))


for _name, (_dirs, _) in folder_names_and_paths.items():
    for _d in _dirs:
        Path(_d).mkdir(parents=True, exist_ok=True)
