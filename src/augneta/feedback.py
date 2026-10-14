"""Target-independent environmental force encoding shared by both displays."""

from dataclasses import asdict, dataclass
import math

from .estimation import Belief


ENCODERS = {"polar8-v1": 0, "polar8-rotated-v1": 2}
MAX_MAGNITUDE = 1.5
MAGNITUDE_LEVELS = 4
UNCERTAINTY_QUANTUM = 0.25


@dataclass(frozen=True, slots=True)
class FeedbackPacket:
    emitted_step: int
    direction_bin: int
    magnitude_level: int
    uncertainty_level: int
    last_sample_step: int | None
    age_steps: int | None
    delayed: bool
    dropped: bool
    sensor_status: str
    estimator_id: str
    encoder_id: str
    channel_offset: int
    channels: tuple[float, ...]

    def to_dict(self):
        value = asdict(self)
        value["channels"] = list(value["channels"])
        return value


class Encoder:
    __slots__ = ("identity",)

    def __init__(self, identity="polar8-v1"):
        if identity not in ENCODERS:
            raise ValueError(f"unknown encoder: {identity}")
        self.identity = identity

    def encode(self, belief: Belief):
        # Only belief is accepted: no target, desired action, position, or hidden truth.
        angle = math.atan2(belief.mean[1], belief.mean[0]) % math.tau
        direction = int(math.floor(angle / (math.tau / 8) + 0.5)) % 8
        magnitude = min(MAGNITUDE_LEVELS, int(math.floor(
            math.hypot(*belief.mean) / MAX_MAGNITUDE * MAGNITUDE_LEVELS + 0.5)))
        if magnitude == 0:
            direction = 0  # Do not leak direction through a nominally zero code.
        uncertainty = min(8, int(math.floor(math.sqrt(belief.variance) / UNCERTAINTY_QUANTUM + 0.5)))
        offset = ENCODERS[self.identity]
        channels = [0.0] * 8
        channels[(direction + offset) % 8] = magnitude / MAGNITUDE_LEVELS
        age = None if belief.last_sample_step is None else belief.now_step - belief.last_sample_step
        return FeedbackPacket(belief.now_step, direction, magnitude, uncertainty,
                              belief.last_sample_step, age, age is not None and age > 0,
                              belief.dropped, belief.sensor_status, belief.estimator_id,
                              self.identity, offset, tuple(channels))


def decode_force(packet):
    """Decode only the displayed, quantized information for a synthetic policy."""
    if packet is None:
        return (0.0, 0.0)
    angle = packet["direction_bin"] * math.tau / 8
    magnitude = packet["magnitude_level"] / MAGNITUDE_LEVELS * MAX_MAGNITUDE
    return magnitude * math.cos(angle), magnitude * math.sin(angle)
