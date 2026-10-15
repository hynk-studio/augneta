"""Validated, explicit simulation parameters; all times use seconds or ticks."""

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class Config:
    seed: int = 7
    dt_s: float = 0.05
    steps: int = 600
    evaluation_start_step: int = 100
    evaluation_end_step: int = 600
    arena_half_width: float = 1.0
    control_gain: float = 2.0
    drag: float = 1.2
    max_speed: float = 1.5
    flow_strength: float = 0.65
    flow_period_s: float = 9.0
    target_radius: float = 0.5
    target_period_s: float = 16.0
    sensor_noise_std: float = 0.18
    sensor_period_steps: int = 4
    sensor_delay_steps: int = 4
    sensor_dropout_probability: float = 0.1
    feedback_period_steps: int = 4
    task: str = "tracking"
    safe_zone_half_width: float = 0.2

    def __post_init__(self):
        integers = {"seed", "steps", "evaluation_start_step", "evaluation_end_step",
                    "sensor_period_steps", "sensor_delay_steps", "feedback_period_steps"}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "task":
                if type(value) is not str or value not in ("tracking", "safe_zone"):
                    raise ValueError("unknown task")
                continue
            if field.name in integers:
                if type(value) is not int:
                    raise ValueError(f"{field.name} must be an integer")
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{field.name} must be finite")
        if self.safe_zone_half_width <= 0:
            raise ValueError("safe zone half-width must be positive")
        if self.task == "safe_zone" and self.safe_zone_half_width >= self.arena_half_width:
            raise ValueError("safe zone must fit strictly inside arena")
        if not 0 <= self.seed < 2**32:
            raise ValueError("seed must be in [0, 2**32)")
        if not 0.005 <= self.dt_s <= 0.1 or not 1 <= self.steps <= 100_000:
            raise ValueError("dt_s or steps outside supported range")
        if not 0 <= self.evaluation_start_step < self.evaluation_end_step <= self.steps:
            raise ValueError("evaluation window must satisfy 0 <= start < end <= steps")
        for name in ("arena_half_width", "control_gain", "max_speed", "flow_period_s",
                     "target_period_s", "sensor_noise_std"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.drag < 0 or self.flow_strength < 0:
            raise ValueError("drag and flow_strength cannot be negative")
        if not 0 < self.target_radius < self.arena_half_width:
            raise ValueError("target must fit strictly inside the arena")
        if not 0 <= self.sensor_dropout_probability <= 1:
            raise ValueError("sensor_dropout_probability must be in [0, 1]")
        if self.sensor_period_steps < 1 or self.feedback_period_steps < 1:
            raise ValueError("update periods must be positive ticks")
        if not 0 <= self.sensor_delay_steps <= self.steps:
            raise ValueError("sensor delay must be between zero and trial length")
        for name in ("arena_half_width", "control_gain", "max_speed", "flow_period_s",
                     "target_period_s", "sensor_noise_std"):
            if not 1e-6 <= getattr(self, name) <= 1e3:
                raise ValueError(f"{name} outside numerical support [1e-6, 1000]")
        if self.drag > 1e3 or self.flow_strength > 1e3:
            raise ValueError("drag and flow_strength must not exceed 1000")

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict):
            raise ValueError("config must be an object")
        unknown = set(values) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown config fields: {sorted(unknown)}")
        return cls(**values)

    def to_dict(self):
        return asdict(self)

    @property
    def identity(self):
        return hashlib.sha256(canonical(self.to_dict()).encode()).hexdigest()
