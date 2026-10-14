"""Hidden dynamics and a limited sensor; public state contains no hidden force."""

from dataclasses import asdict, dataclass
import math
import random

from .config import Config
from .estimation import SensorObservation


def clip(value, low, high):
    return min(high, max(low, value))


def validate_action(action):
    if not isinstance(action, (list, tuple)) or len(action) != 2:
        raise ValueError("action must have two components")
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1 for v in action):
        raise ValueError("each action must be finite and in [-1, 1]")
    return tuple(float(v) for v in action)


@dataclass(frozen=True, slots=True)
class VisibleState:
    step: int
    time_s: float
    position: tuple[float, float]
    velocity: tuple[float, float]
    target: tuple[float, float]

    def to_dict(self):
        data = asdict(self)
        for key in ("position", "velocity", "target"):
            data[key] = list(data[key])
        return data


class World:
    def __init__(self, config: Config):
        self.config = config
        self.step = 0
        self.position = (0.0, 0.0)
        self.velocity = (0.0, 0.0)
        flow_rng = random.Random(config.seed)
        self.__phases = tuple(flow_rng.uniform(0, math.tau) for _ in range(4))
        self.__sensor_rng = random.Random(config.seed ^ 0xA617)
        self.__pending = []
        self.__sampled_step = -1

    def __flow(self):
        c = self.config
        phase = math.tau * self.step * c.dt_s / c.flow_period_s
        a, b, d, e = self.__phases
        return (c.flow_strength * (math.sin(phase + a) + 0.35 * math.sin(0.43 * phase + b)),
                c.flow_strength * (math.cos(0.79 * phase + d) + 0.35 * math.sin(0.61 * phase + e)))

    def visible(self):
        c = self.config
        phase = math.tau * self.step * c.dt_s / c.target_period_s
        target = (c.target_radius * math.cos(phase), 0.7 * c.target_radius * math.sin(phase))
        return VisibleState(self.step, self.step * c.dt_s, self.position, self.velocity, target)

    def observations(self):
        if self.__sampled_step == self.step:
            raise RuntimeError("sensor was already sampled at this tick")
        self.__sampled_step = self.step
        c = self.config
        if self.step % c.sensor_period_steps == 0:
            # Draw noise even on dropout so changing dropout rates preserves noise draws.
            dropped = self.__sensor_rng.random() < c.sensor_dropout_probability
            noisy = tuple(v + self.__sensor_rng.gauss(0, c.sensor_noise_std) for v in self.__flow())
            self.__pending.append(SensorObservation(
                self.step, self.step + c.sensor_delay_steps, None if dropped else noisy, dropped))
        delivered = tuple(o for o in self.__pending if o.available_step <= self.step)
        self.__pending = [o for o in self.__pending if o.available_step > self.step]
        return delivered

    def evaluation_only(self):
        """Separate evaluator/oracle capability. Never passed to online components."""
        return {"access": "evaluator_only", "step": self.step, "flow": list(self.__flow())}

    def advance(self, action):
        action = validate_action(action)
        c = self.config
        flow = self.__flow()
        velocity = [clip(v + c.dt_s * (c.control_gain * u + f - c.drag * v),
                         -c.max_speed, c.max_speed)
                    for v, u, f in zip(self.velocity, action, flow)]
        position = [p + c.dt_s * v for p, v in zip(self.position, velocity)]
        for axis in range(2):
            if abs(position[axis]) > c.arena_half_width:
                position[axis] = clip(position[axis], -c.arena_half_width, c.arena_half_width)
                velocity[axis] = 0.0
        self.position, self.velocity = tuple(position), tuple(velocity)
        self.step += 1
        return self.visible()
