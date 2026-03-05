"""Ghost compat: comfy.k_diffusion.utils — stubs."""


def append_dims(x, target_dims):
    """Append dimensions to the end of a tensor."""
    dims_to_append = target_dims - x.ndim
    if dims_to_append < 0:
        raise ValueError(f"input has {x.ndim} dims but target_dims is {target_dims}")
    return x[(...,) + (None,) * dims_to_append]


class FolderOfImages:
    pass
