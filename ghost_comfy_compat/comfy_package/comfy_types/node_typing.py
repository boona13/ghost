"""Ghost compat: comfy.comfy_types.node_typing — IO class stub."""


class _IOType(str):
    """IO type descriptor — behaves like a string for compatibility."""
    def __new__(cls, value="*"):
        return super().__new__(cls, value)


class IO:
    STRING = _IOType("STRING")
    INT = _IOType("INT")
    FLOAT = _IOType("FLOAT")
    BOOLEAN = _IOType("BOOLEAN")
    IMAGE = _IOType("IMAGE")
    MASK = _IOType("MASK")
    LATENT = _IOType("LATENT")
    MODEL = _IOType("MODEL")
    CLIP = _IOType("CLIP")
    VAE = _IOType("VAE")
    CONDITIONING = _IOType("CONDITIONING")
    CONTROL_NET = _IOType("CONTROL_NET")
    NOISE = _IOType("NOISE")
    SAMPLER = _IOType("SAMPLER")
    SIGMAS = _IOType("SIGMAS")
    GUIDER = _IOType("GUIDER")
    AUDIO = _IOType("AUDIO")
    VIDEO = _IOType("VIDEO")
    ANY = _IOType("*")
    NUMBER = _IOType("NUMBER")
    COMBO = _IOType("COMBO")
