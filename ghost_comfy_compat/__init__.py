"""
Ghost ComfyUI Compatibility Layer.

Injects a comprehensive set of comfy-compatible modules into sys.modules
so that custom node repos can be imported without a real ComfyUI install.

Usage:
    from ghost_comfy_compat import ensure_comfy_compat
    ensure_comfy_compat()  # idempotent, safe to call multiple times
"""

import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path

log = logging.getLogger("ghost.comfy_compat")

_injected = False

GHOST_HOME = Path.home() / ".ghost"
MODELS_DIR = GHOST_HOME / "models"
OUTPUT_DIR = GHOST_HOME / "media" / "image"
INPUT_DIR = GHOST_HOME / "media" / "input"
TEMP_DIR = GHOST_HOME / "comfyui" / "temp"


def _comfy_api_io_attrs() -> dict:
    """Attributes for comfy_api.*.io stubs (ComfyNode, Schema, etc.)."""

    class _ComfyNode:
        RETURN_TYPES = ()
        FUNCTION = "execute"
        CATEGORY = "default"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {}, "optional": {}}

        def execute(self, **kwargs):
            return ()

    class _Schema:
        def __init__(self, *args, **kwargs):
            pass

    return {
        "ComfyNode": _ComfyNode,
        "Schema": _Schema,
        "NodeInput": type("NodeInput", (), {}),
        "NodeOutput": type("NodeOutput", (), {}),
        "STRING": "STRING",
        "INT": "INT",
        "FLOAT": "FLOAT",
        "BOOLEAN": "BOOLEAN",
        "IMAGE": "IMAGE",
        "MASK": "MASK",
        "LATENT": "LATENT",
        "MODEL": "MODEL",
        "CLIP": "CLIP",
        "VAE": "VAE",
        "CONDITIONING": "CONDITIONING",
        "ANY": "*",
    }


def _make_stub_module(name: str, attrs: dict | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__package__ = name.rsplit(".", 1)[0] if "." in name else name
    mod.__path__ = []
    mod.__file__ = f"<ghost_comfy_compat:{name}>"
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    return mod


def ensure_comfy_compat() -> bool:
    """Inject comfy compat modules into sys.modules if real ComfyUI is absent.

    Returns True if compat layer was injected, False if real ComfyUI exists.
    Idempotent — safe to call multiple times.
    """
    global _injected
    if _injected:
        return True

    if "comfy" in sys.modules and hasattr(sys.modules["comfy"], "__comfy_compat__"):
        _injected = True
        return True

    try:
        spec = importlib.util.find_spec("comfy")
        if spec is not None and spec.origin and "ghost_comfy_compat" not in (spec.origin or ""):
            log.debug("Real ComfyUI found at %s, skipping compat injection", spec.origin)
            return False
    except (ModuleNotFoundError, ValueError):
        pass

    log.info("Injecting comfy compatibility layer (no real ComfyUI detected)")

    for d in [OUTPUT_DIR, INPUT_DIR, TEMP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    _inject_folder_paths()
    _inject_comfy_package()
    _inject_nodes_module()
    _inject_server_module()
    _inject_node_helpers()
    _inject_execution_modules()
    _inject_comfy_extras()

    _injected = True
    log.info("Comfy compat layer injected — %d modules registered",
             sum(1 for k in sys.modules if k.startswith(("comfy", "folder_paths", "nodes", "server", "node_helpers", "execution", "comfy_execution", "comfy_extras"))))
    return True


def _inject_folder_paths():
    from ghost_comfy_compat import folder_paths as fp_mod
    sys.modules["folder_paths"] = fp_mod


def _inject_comfy_package():
    compat_dir = Path(__file__).parent / "comfy_package"

    comfy = _make_stub_module("comfy")
    comfy.__comfy_compat__ = True
    comfy.__path__ = [str(compat_dir)]
    sys.modules["comfy"] = comfy

    submodules = [
        "comfy.utils",
        "comfy.model_management",
        "comfy.samplers",
        "comfy.latent_formats",
        "comfy.sd",
        "comfy.model_patcher",
        "comfy.model_base",
        "comfy.model_sampling",
        "comfy.cli_args",
        "comfy.controlnet",
        "comfy.clip_vision",
        "comfy.ops",
        "comfy.conds",
        "comfy.model_detection",
        "comfy.hooks",
        "comfy.sample",
        "comfy.sampler_helpers",
        "comfy.lora",
        "comfy.patcher_extension",
    ]
    for mod_name in submodules:
        short = mod_name.split(".")[-1]
        file_path = compat_dir / f"{short}.py"
        if file_path.exists():
            spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                setattr(comfy, short, mod)
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    log.warning("Failed to load compat module %s: %s", mod_name, e)
        else:
            stub = _make_stub_module(mod_name)
            sys.modules[mod_name] = stub
            setattr(comfy, short, stub)

    _inject_comfy_sub_packages(comfy, compat_dir)


def _inject_comfy_sub_packages(comfy, compat_dir: Path):
    sub_packages = {
        "comfy.k_diffusion": compat_dir / "k_diffusion",
        "comfy.ldm": compat_dir / "ldm",
        "comfy.ldm.modules": compat_dir / "ldm" / "modules",
        "comfy.ldm.modules.diffusionmodules": compat_dir / "ldm" / "modules" / "diffusionmodules",
        "comfy.ldm.flux": compat_dir / "ldm" / "flux",
        "comfy.ldm.wan": compat_dir / "ldm" / "wan",
        "comfy.comfy_types": compat_dir / "comfy_types",
        "comfy.cldm": compat_dir / "cldm",
    }
    for pkg_name, pkg_path in sub_packages.items():
        init_file = pkg_path / "__init__.py"
        if init_file.exists():
            spec = importlib.util.spec_from_file_location(
                pkg_name, str(init_file),
                submodule_search_locations=[str(pkg_path)])
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[pkg_name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    log.warning("Failed to load compat sub-package %s: %s", pkg_name, e)
                    sys.modules[pkg_name] = _make_stub_module(pkg_name)
        else:
            sys.modules[pkg_name] = _make_stub_module(pkg_name)

        # Wire sub-package as attribute on its immediate parent module
        parts = pkg_name.split(".")
        if len(parts) > 1:
            parent_name = ".".join(parts[:-1])
            child_attr = parts[-1]
            parent_mod = sys.modules.get(parent_name)
            if parent_mod is not None:
                setattr(parent_mod, child_attr, sys.modules[pkg_name])

    _load_sub_package_modules(compat_dir)


def _load_sub_package_modules(compat_dir: Path):
    deep_modules = {
        "comfy.k_diffusion.sampling": compat_dir / "k_diffusion" / "sampling.py",
        "comfy.k_diffusion.utils": compat_dir / "k_diffusion" / "utils.py",
        "comfy.ldm.modules.attention": compat_dir / "ldm" / "modules" / "attention.py",
        "comfy.ldm.modules.diffusionmodules.openaimodel": compat_dir / "ldm" / "modules" / "diffusionmodules" / "openaimodel.py",
        "comfy.ldm.modules.diffusionmodules.util": compat_dir / "ldm" / "modules" / "diffusionmodules" / "util.py",
        "comfy.ldm.util": compat_dir / "ldm" / "util.py",
        "comfy.ldm.flux.math": compat_dir / "ldm" / "flux" / "math.py",
        "comfy.ldm.wan.model": compat_dir / "ldm" / "wan" / "model.py",
        "comfy.comfy_types.node_typing": compat_dir / "comfy_types" / "node_typing.py",
        "comfy.cldm.cldm": compat_dir / "cldm" / "cldm.py",
    }
    for mod_name, file_path in deep_modules.items():
        if file_path.exists():
            spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    log.warning("Failed to load deep compat module %s: %s", mod_name, e)
                    sys.modules[mod_name] = _make_stub_module(mod_name)
        else:
            sys.modules[mod_name] = _make_stub_module(mod_name)

        parts = mod_name.split(".")
        if len(parts) > 1:
            parent_name = ".".join(parts[:-1])
            child_attr = parts[-1]
            parent_mod = sys.modules.get(parent_name)
            if parent_mod is not None:
                setattr(parent_mod, child_attr, sys.modules[mod_name])


def _inject_nodes_module():
    from ghost_comfy_compat import nodes_module
    sys.modules["nodes"] = nodes_module


def _inject_server_module():
    from ghost_comfy_compat import server_module
    sys.modules["server"] = server_module


def _inject_node_helpers():
    from ghost_comfy_compat import node_helpers_module
    sys.modules["node_helpers"] = node_helpers_module


def _inject_execution_modules():
    from ghost_comfy_compat import execution_module
    sys.modules["execution"] = execution_module

    from ghost_comfy_compat import comfy_execution_module as ce
    sys.modules["comfy_execution"] = ce
    sys.modules["comfy_execution.graph_utils"] = ce
    sys.modules["comfy_execution.graph"] = ce


def _inject_comfy_extras():
    """Install an import hook that auto-creates stubs for any comfy_extras.* import."""

    _CATCH_ALL_PREFIXES = (
        "comfy_extras",
        "comfy_extras.",
        "comfy_api",
        "comfy_api.",
        "latent_preview",
        "latent_preview.",
    )

    class _ComfyCatchAllImporter:
        """Auto-stub importer for comfy_extras.* and comfy_api.* imports."""

        def find_module(self, fullname, path=None):
            if any(fullname == p.rstrip(".") or fullname.startswith(p)
                   for p in _CATCH_ALL_PREFIXES):
                return self
            return None

        def load_module(self, fullname):
            if fullname in sys.modules:
                return sys.modules[fullname]
            mod = _make_stub_module(fullname, {"NODE_CLASS_MAPPINGS": {}})
            sys.modules[fullname] = mod
            return mod

        def find_spec(self, fullname, path=None, target=None):
            if any(fullname == p.rstrip(".") or fullname.startswith(p)
                   for p in _CATCH_ALL_PREFIXES):
                from importlib.machinery import ModuleSpec
                return ModuleSpec(fullname, self)
            return None

        def create_module(self, spec):
            attrs = {"NODE_CLASS_MAPPINGS": {}}
            if "io" in spec.name:
                attrs.update(_comfy_api_io_attrs())
            if spec.name.endswith(".latest") or spec.name == "comfy_api.latest":
                attrs["io"] = type("io_stub", (), _comfy_api_io_attrs())()
                attrs["ComfyExtension"] = type("ComfyExtension", (), {
                    "__init__": lambda self, *a, **k: None,
                    "register_nodes": lambda self: None,
                })
            if "latent_preview" in spec.name:
                attrs["LatentPreviewer"] = type("LatentPreviewer", (), {
                    "__init__": lambda self, *a, **k: None,
                    "decode_latent_to_preview": lambda self, *a, **k: None,
                })
                attrs["TAESD"] = type("TAESD", (), {})
                attrs["get_previewer"] = lambda *a, **k: None
            if "nodes_hooks" in spec.name:
                _hook_node_base = type("_HookNodeBase", (), {
                    "RETURN_TYPES": ("HOOKS",),
                    "FUNCTION": "create_hook",
                    "CATEGORY": "advanced/hooks",
                    "create_hook": lambda self, **kw: (None,),
                    "INPUT_TYPES": classmethod(lambda cls: {"required": {}, "optional": {}}),
                })
                for _hname in ("CreateHookModelAsLora", "CreateHookLora", "CreateHookModelAsLoraMulti",
                               "SetHookKeyframes", "CreateHookKeyframe", "CreateHookKeyframesInterpolated",
                               "CreateHookKeyframesFromFloats", "SetModelHooksOnCond",
                               "ConditioningTimestepsRange"):
                    attrs[_hname] = type(_hname, (_hook_node_base,), {})
            if "nodes_model_advanced" in spec.name:
                _base = type("_ModelSamplingBase", (), {
                    "__init__": lambda self, *a, **k: None,
                    "RETURN_TYPES": ("MODEL",),
                    "FUNCTION": "patch",
                    "CATEGORY": "advanced/model",
                })
                for _name in ("ModelSamplingDiscrete", "ModelSamplingContinuousEDM",
                              "ModelSamplingContinuousV", "ModelSamplingStableCascade",
                              "ModelSamplingSD3", "ModelSamplingAuraFlow",
                              "ModelSamplingFlux", "RescaleCFG", "LCM"):
                    attrs[_name] = type(_name, (_base,), {})
            return _make_stub_module(spec.name, attrs)

        def exec_module(self, module):
            sys.modules[module.__name__] = module

    if not any(isinstance(f, _ComfyCatchAllImporter) for f in sys.meta_path):
        sys.meta_path.insert(0, _ComfyCatchAllImporter())
