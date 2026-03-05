"""Ghost compat: comfy.hooks — hook/keyframe stubs for AnimateDiff."""


class HookKeyframe:
    def __init__(self, strength=1.0, start_percent=0.0, guarantee_steps=1):
        self.strength = strength
        self.start_percent = start_percent
        self.guarantee_steps = guarantee_steps


class HookKeyframeGroup:
    def __init__(self):
        self.keyframes = []

    def add(self, keyframe):
        self.keyframes.append(keyframe)
        self.keyframes.sort(key=lambda k: k.start_percent)
        return self

    def clone(self):
        c = HookKeyframeGroup()
        c.keyframes = list(self.keyframes)
        return c


class HookGroup:
    def __init__(self):
        self.hooks = []

    def add(self, hook):
        self.hooks.append(hook)
        return self

    def clone(self):
        c = HookGroup()
        c.hooks = list(self.hooks)
        return c

    def __len__(self):
        return len(self.hooks)

    def __iter__(self):
        return iter(self.hooks)


class Hook:
    def __init__(self):
        self.strength = 1.0
        self.hook_keyframe = None

    def clone(self):
        c = Hook()
        c.strength = self.strength
        c.hook_keyframe = self.hook_keyframe
        return c


class WeightHook(Hook):
    pass


class PatchHook(Hook):
    pass
