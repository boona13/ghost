"""
Ghost compat: comfy.latent_formats — all latent format classes.

Pure data classes, zero dependencies. Copied from ComfyUI source.
"""


class LatentFormat:
    scale_factor = 1.0
    latent_channels = 4
    latent_dimensions = 2
    latent_rgb_factors = None
    latent_rgb_factors_bias = None
    taesd_decoder_name = None
    spacial_downscale_ratio = 8

    def process_in(self, latent):
        return latent * self.scale_factor

    def process_out(self, latent):
        return latent / self.scale_factor


class SD15(LatentFormat):
    scale_factor = 0.18215
    latent_channels = 4
    latent_rgb_factors = [
        [0.3512, 0.2297, 0.3227],
        [0.3250, 0.4974, 0.2350],
        [-0.2829, 0.1391, 0.2421],
        [-0.2120, -0.2616, -0.7177],
    ]
    taesd_decoder_name = "taesd_decoder"


class SDXL(LatentFormat):
    scale_factor = 0.13025
    latent_channels = 4
    latent_rgb_factors = [
        [0.3920, 0.4054, 0.4549],
        [-0.2634, -0.0196, 0.0653],
        [0.0568, 0.1687, -0.0755],
        [-0.3112, -0.2359, -0.2076],
    ]
    taesd_decoder_name = "taesdxl_decoder"


class SDXL_Playground_2_5(LatentFormat):
    scale_factor = 0.5
    latent_channels = 4

    def process_in(self, latent):
        latents_mean = [
            -1.6574, 1.886, -1.383, 2.5155
        ]
        latents_std = [
            8.4927, 5.9022, 6.5498, 5.2299
        ]
        import torch
        mean = torch.tensor(latents_mean, device=latent.device, dtype=latent.dtype).view(1, 4, 1, 1)
        std = torch.tensor(latents_std, device=latent.device, dtype=latent.dtype).view(1, 4, 1, 1)
        return (latent - mean) / std

    def process_out(self, latent):
        latents_mean = [
            -1.6574, 1.886, -1.383, 2.5155
        ]
        latents_std = [
            8.4927, 5.9022, 6.5498, 5.2299
        ]
        import torch
        mean = torch.tensor(latents_mean, device=latent.device, dtype=latent.dtype).view(1, 4, 1, 1)
        std = torch.tensor(latents_std, device=latent.device, dtype=latent.dtype).view(1, 4, 1, 1)
        return latent * std + mean


class SD_X4(LatentFormat):
    scale_factor = 0.08333
    latent_channels = 4


class SC_Prior(LatentFormat):
    latent_channels = 16
    scale_factor = 1.0
    spacial_downscale_ratio = 42


class SC_B(LatentFormat):
    latent_channels = 4
    scale_factor = 1.0 / 0.43


class SD3(LatentFormat):
    latent_channels = 16
    scale_factor = 1.5305
    spacial_downscale_ratio = 8
    latent_rgb_factors = [
        [-0.0645, 0.0177, 0.1052],
        [0.0028, 0.0312, 0.0650],
        [0.1848, 0.0762, 0.0360],
        [0.0944, 0.0360, 0.0889],
        [0.0897, 0.0506, -0.0364],
        [-0.0020, 0.1203, 0.0284],
        [0.0855, 0.0118, 0.0283],
        [-0.0539, 0.0658, 0.1047],
        [-0.0057, 0.0116, 0.0700],
        [-0.0412, 0.0281, -0.0039],
        [0.1106, 0.1171, 0.1220],
        [-0.0248, 0.0682, -0.0481],
        [0.0815, 0.0846, 0.1207],
        [-0.0120, -0.0055, -0.0867],
        [-0.0749, -0.0634, -0.0456],
        [-0.1418, -0.1457, -0.1259],
    ]
    taesd_decoder_name = "taesd3_decoder"

    def process_in(self, latent):
        return (latent - 0.0609) * self.scale_factor

    def process_out(self, latent):
        return latent / self.scale_factor + 0.0609


class StableAudio1(LatentFormat):
    latent_channels = 64
    scale_factor = 1.0


class Flux(LatentFormat):
    latent_channels = 16
    scale_factor = 0.3611
    spacial_downscale_ratio = 8
    latent_rgb_factors = [
        [-0.0404, 0.0159, 0.0609],
        [0.0043, 0.0298, 0.0850],
        [0.1080, 0.0590, 0.0324],
        [0.0602, 0.0325, 0.0649],
        [0.0658, 0.0316, -0.0117],
        [0.0195, 0.0874, 0.0271],
        [0.0482, 0.0160, 0.0233],
        [-0.0307, 0.0440, 0.0750],
        [-0.0210, -0.0025, 0.0530],
        [-0.0324, 0.0215, 0.0010],
        [0.0892, 0.0756, 0.0940],
        [-0.0202, 0.0444, -0.0330],
        [0.0568, 0.0521, 0.0857],
        [-0.0092, -0.0024, -0.0500],
        [-0.0361, -0.0362, -0.0371],
        [-0.0948, -0.0870, -0.0773],
    ]
    taesd_decoder_name = "taef1_decoder"

    def process_in(self, latent):
        return (latent - 0.1159) * self.scale_factor

    def process_out(self, latent):
        return latent / self.scale_factor + 0.1159


class Flux2(LatentFormat):
    latent_channels = 128
    scale_factor = 1.0


class Mochi(LatentFormat):
    latent_channels = 12
    latent_dimensions = 3
    scale_factor = 1.0
    spacial_downscale_ratio = 8

    def process_in(self, latent):
        import torch
        mean = torch.tensor([0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                             0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                            device=latent.device, dtype=latent.dtype).view(1, 12, *([1] * (len(latent.shape) - 2)))
        std = torch.tensor([1.0] * 12,
                           device=latent.device, dtype=latent.dtype).view(1, 12, *([1] * (len(latent.shape) - 2)))
        return (latent - mean) / std

    def process_out(self, latent):
        return latent


class LTXV(LatentFormat):
    latent_channels = 128
    latent_dimensions = 3
    scale_factor = 1.0
    spacial_downscale_ratio = 32


class HunyuanVideo(LatentFormat):
    latent_channels = 16
    latent_dimensions = 3
    scale_factor = 0.476986
    spacial_downscale_ratio = 8


class Cosmos1CV8x8x8(LatentFormat):
    latent_channels = 16
    latent_dimensions = 3
    scale_factor = 1.0
    spacial_downscale_ratio = 8


class Wan21(LatentFormat):
    latent_channels = 16
    latent_dimensions = 3
    scale_factor = 1.0
    spacial_downscale_ratio = 8

    def process_in(self, latent):
        import torch
        mean = torch.tensor(
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
             0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            device=latent.device, dtype=latent.dtype
        ).view(1, 16, *([1] * (len(latent.shape) - 2)))
        std = torch.tensor(
            [1.0] * 16,
            device=latent.device, dtype=latent.dtype
        ).view(1, 16, *([1] * (len(latent.shape) - 2)))
        return (latent - mean) / std

    def process_out(self, latent):
        return latent


class Wan22(Wan21):
    latent_channels = 48


class HunyuanVideo15(LatentFormat):
    latent_channels = 32
    latent_dimensions = 3
    scale_factor = 1.03682
    spacial_downscale_ratio = 8


class ACEAudio(LatentFormat):
    latent_channels = 8
    scale_factor = 1.0


class ChromaRadiance(LatentFormat):
    latent_channels = 3
    scale_factor = 1.0
    spacial_downscale_ratio = 1
