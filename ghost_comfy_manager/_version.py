"""
Minimal StrictVersion — adapted from ComfyUI-Manager's manager_util.py.

Pure-Python version comparison that handles pre-release tags.
"""


class StrictVersion:
    def __init__(self, version_string: str):
        self.version_string = str(version_string)
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.pre_release = None
        self._parse()

    def _parse(self):
        parts = self.version_string.split(".")
        if not parts:
            raise ValueError("Version string must not be empty")
        self.major = int(parts[0])
        self.minor = int(parts[1]) if len(parts) > 1 else 0
        self.patch = int(parts[2]) if len(parts) > 2 else 0
        if len(parts) > 3:
            self.pre_release = parts[3]

    def __str__(self):
        v = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            v += f"-{self.pre_release}"
        return v

    def _key(self):
        return (self.major, self.minor, self.patch, self.pre_release)

    def __eq__(self, other):
        return self._key() == other._key()

    def __lt__(self, other):
        if (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch):
            return self._pre_cmp(self.pre_release, other.pre_release) < 0
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    def __ne__(self, other):
        return not self == other

    @staticmethod
    def _pre_cmp(a, b):
        if a == b:
            return 0
        if a is None:
            return 1
        if b is None:
            return -1
        return -1 if a < b else 1
