"""
Ghost compat: comfy.conds — conditioning data classes.
"""


class CONDRegular:
    def __init__(self, cond):
        self.cond = cond

    def can_concat_to(self, other):
        if self.cond.shape != other.cond.shape:
            return False
        return True

    def concat_to(self, others):
        import torch
        conds = [self.cond] + [x.cond for x in others]
        return torch.cat(conds)

    def process_cond(self, **kwargs):
        return self


class CONDNoiseShape(CONDRegular):
    pass


class CONDCrossAttn(CONDRegular):
    pass


class CONDConstant(CONDRegular):
    pass
