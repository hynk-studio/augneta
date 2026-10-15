"""Device-independent state codes and six-slot command previews. No device IO.

The legacy eight-slot mock remains in haptics.py for its recorded baseline.
These candidate profiles have never been calibrated on a person's skin.
"""

from dataclasses import asdict, dataclass, fields
import hashlib
import math

from .config import canonical


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


@dataclass(frozen=True)
class CodeSpec:
    directions: int = 6
    levels: int = 2
    max_magnitude: float = 1.5

    def __post_init__(self):
        if type(self.directions) is not int or not 2 <= self.directions <= 8:
            raise ValueError("directions must be an integer from 2 to 8")
        if type(self.levels) is not int or not 1 <= self.levels <= 4:
            raise ValueError("levels must be an integer from 1 to 4")
        if not number(self.max_magnitude, 0.01, 100):
            raise ValueError("invalid magnitude range")

    @property
    def identity(self):
        return "polar-state-" + hashlib.sha256(canonical(asdict(self)).encode()).hexdigest()[:16]

    def code(self, direction, level):
        if type(level) is not int or not 0 <= level <= self.levels:
            raise ValueError("invalid magnitude level")
        if level == 0:
            if direction is not None:
                raise ValueError("zero magnitude carries no direction")
        elif type(direction) is not int or not 0 <= direction < self.directions:
            raise ValueError("invalid direction")
        return {"code_id": self.identity, "direction": direction, "level": level}

    def encode(self, belief):
        # The only external input is causal estimator belief, never a target/action.
        x, y = belief.mean
        if not all(number(v, -1e6, 1e6) for v in (x, y)):
            raise ValueError("invalid belief mean")
        direction = int(math.floor((math.atan2(y, x) % math.tau) /
                                   math.tau * self.directions + 0.5)) % self.directions
        level = min(self.levels, int(math.floor(math.hypot(x, y) /
                                               self.max_magnitude * self.levels + 0.5)))
        return self.code(direction if level else None, level)


@dataclass(frozen=True)
class TactileProfile:
    spec: CodeSpec = CodeSpec()
    patterns: tuple = tuple(tuple(float(i == j) for j in range(6)) for i in range(6))
    gains: tuple = (1.0,) * 6
    intensities: tuple = (0.0, 0.25, 0.5)
    pulse_ms: int = 150
    gap_ms: int = 150

    def __post_init__(self):
        if not isinstance(self.spec, CodeSpec):
            raise ValueError("profile needs a code spec")
        if type(self.patterns) is not tuple or len(self.patterns) != self.spec.directions:
            raise ValueError("one explicit six-slot pattern is required per semantic direction")
        for row in self.patterns:
            if (type(row) is not tuple or len(row) != 6 or
                    not all(number(v, 0, 1) for v in row) or max(row) != 1):
                raise ValueError("patterns need six values in [0,1] and peak 1")
        if len(set(self.patterns)) != len(self.patterns):
            raise ValueError("different meanings cannot silently alias to the same pattern")
        if (type(self.gains) is not tuple or len(self.gains) != 6 or
                not all(number(v, 0.05, 1) for v in self.gains)):
            raise ValueError("six gains in [0.05,1] are required")
        if (type(self.intensities) is not tuple or len(self.intensities) != self.spec.levels + 1 or
                not all(number(v, 0, 1) for v in self.intensities) or self.intensities[0] != 0 or
                any(a >= b for a, b in zip(self.intensities, self.intensities[1:]))):
            raise ValueError("intensities must start at zero and strictly increase")
        if (type(self.pulse_ms) is not int or not 50 <= self.pulse_ms <= 1000 or
                type(self.gap_ms) is not int or not 50 <= self.gap_ms <= 2000):
            raise ValueError("invalid preview pulse/gap (these are not hardware limits)")

    def to_dict(self):
        import json
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != {f.name for f in fields(cls)}:
            raise ValueError("profile fields mismatch")
        spec = data["spec"]
        if not isinstance(spec, dict) or set(spec) != {f.name for f in fields(CodeSpec)}:
            raise ValueError("code spec fields mismatch")
        try:
            return cls(CodeSpec(**spec), tuple(tuple(row) for row in data["patterns"]),
                       tuple(data["gains"]), tuple(data["intensities"]),
                       data["pulse_ms"], data["gap_ms"])
        except TypeError:
            raise ValueError("invalid profile arrays") from None

    @property
    def identity(self):
        return hashlib.sha256(canonical(self.to_dict()).encode()).hexdigest()

    def render(self, code):
        if not isinstance(code, dict) or set(code) != {"code_id", "direction", "level"}:
            raise ValueError("only a semantic state code may be rendered")
        expected = self.spec.code(code["direction"], code["level"])
        if code != expected:
            raise ValueError("code/profile meaning mismatch")
        direction, level = code["direction"], code["level"]
        pattern = (0.0,) * 6 if direction is None else self.patterns[direction]
        values = [p * gain * self.intensities[level] for p, gain in zip(pattern, self.gains)]
        return {"left": values[:3], "right": values[3:], "pulse_ms": self.pulse_ms,
                "gap_ms": self.gap_ms, "profile_sha256": self.identity,
                "output_mode": "command_preview", "hardware_verified": False}

    def matched_preview(self, code):
        command = self.render(code)
        direction, level = code["direction"], code["level"]
        angle = 0 if direction is None else direction * math.tau / self.spec.directions
        magnitude = level / self.spec.levels * self.spec.max_magnitude
        return {"semantic_state": dict(code), "command": command,
                "visual": {"force": [magnitude * math.cos(angle), magnitude * math.sin(angle)],
                           "pulse_ms": self.pulse_ms, "gap_ms": self.gap_ms},
                "hardware_verified": False, "human_evidence": False}
