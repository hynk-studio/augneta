"""Packet-to-actuator contract and a deliberately non-physical output simulator.

No driver, socket, Bluetooth service, or device is opened by this module.
Clock values are synthetic milliseconds, not host or skin-level measurements.
"""

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math

from .config import canonical
from .estimation import ESTIMATORS
from .feedback import ENCODERS, FeedbackPacket


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class OutputProfile:
    """Logical channels to actuator indices; command units are NOT acceleration.

    Defaults are test values, not a comfortable or validated human-use profile.
    Each channel has a zero plus four strictly increasing command levels.
    """

    profile_id: str = "mock-eight-channel-linear-v1"
    actuator_count: int = 8
    channel_map: tuple[int, ...] = tuple(range(8))
    levels: tuple[tuple[float, ...], ...] = ((0.0, 0.25, 0.5, 0.75, 1.0),) * 8
    pulse_ms: int = 100
    max_packet_age_ms: int = 250

    def __post_init__(self):
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile needs an identity")
        if type(self.actuator_count) is not int or not 8 <= self.actuator_count <= 64:
            raise ValueError("profile needs 8 to 64 independent actuator slots")
        if (type(self.channel_map) is not tuple or len(self.channel_map) != 8
                or any(type(v) is not int or not 0 <= v < self.actuator_count for v in self.channel_map)
                or len(set(self.channel_map)) != 8):
            raise ValueError("eight logical channels need eight distinct actuator indices")
        if type(self.levels) is not tuple or len(self.levels) != 8:
            raise ValueError("profile needs eight immutable level tables")
        for row in self.levels:
            if (type(row) is not tuple or len(row) != 5
                    or not all(finite_number(v) and 0 <= v <= 1 for v in row)
                    or row[0] != 0 or any(a >= b for a, b in zip(row, row[1:]))):
                raise ValueError("each level table must start at zero and strictly increase within [0, 1]")
        for value in (self.pulse_ms, self.max_packet_age_ms):
            if type(value) is not int or not 1 <= value <= 1000:
                raise ValueError("mock pulse and freshness bounds must be 1 to 1000 ms")
        if self.pulse_ms > self.max_packet_age_ms:
            raise ValueError("pulse must not exceed packet freshness bound")

    def to_dict(self):
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, values):
        if not isinstance(values, dict) or set(values) != {f.name for f in fields(cls)}:
            raise ValueError("output profile fields mismatch")
        return cls(**{**values, "channel_map": tuple(values["channel_map"]),
                      "levels": tuple(tuple(row) for row in values["levels"])})

    @property
    def identity(self):
        return hashlib.sha256(canonical(self.to_dict()).encode()).hexdigest()


def validate_packet(packet):
    """Accept exactly the existing online packet, never truth/action/target fields."""
    if not isinstance(packet, dict) or set(packet) != {f.name for f in fields(FeedbackPacket)}:
        raise ValueError("expected only FeedbackPacket fields")
    limits = {"emitted_step": (0, None), "direction_bin": (0, 7),
              "magnitude_level": (0, 4), "uncertainty_level": (0, 8), "channel_offset": (0, 7)}
    for key, (low, high) in limits.items():
        value = packet[key]
        if type(value) is not int or value < low or (high is not None and value > high):
            raise ValueError(f"invalid packet {key}")
    if packet["estimator_id"] not in ESTIMATORS or packet["encoder_id"] not in ENCODERS:
        raise ValueError("unknown or oracle component is not a main-condition packet")
    if packet["channel_offset"] != ENCODERS[packet["encoder_id"]]:
        raise ValueError("encoder/channel offset mismatch")
    if packet["magnitude_level"] == 0 and packet["direction_bin"] != 0:
        raise ValueError("zero magnitude must not encode a direction")
    sample = packet["last_sample_step"]
    age = packet["age_steps"]
    if sample is None:
        if age is not None:
            raise ValueError("waiting packet cannot have a sample age")
    elif (type(sample) is not int or not 0 <= sample <= packet["emitted_step"]
          or type(age) is not int or age != packet["emitted_step"] - sample):
        raise ValueError("invalid sample age")
    if (type(packet["delayed"]) is not bool or type(packet["dropped"]) is not bool
            or packet["delayed"] != (age is not None and age > 0)
            or packet["sensor_status"] not in ("waiting", "held", "dropout", "fresh")):
        raise ValueError("invalid packet status")
    expected = [0.0] * 8
    expected[(packet["direction_bin"] + packet["channel_offset"]) % 8] = packet["magnitude_level"] / 4
    channels = packet["channels"]
    if (not isinstance(channels, (list, tuple)) or len(channels) != 8
            or not all(finite_number(v) for v in channels) or list(channels) != expected):
        raise ValueError("channels do not match the quantized encoder output")
    return json.loads(canonical(packet))


def render_frame(packet, profile):
    """Only output calibration changes: the shared semantic packet is preserved."""
    packet = validate_packet(packet)
    amplitudes = [0.0] * profile.actuator_count
    for channel, value in enumerate(packet["channels"]):
        amplitudes[profile.channel_map[channel]] = profile.levels[channel][round(value * 4)]
    return {"feedback_packet": packet, "actuator_levels": amplitudes,
            "profile_id": profile.profile_id, "profile_sha256": profile.identity}


class MockOutput:
    """Synchronous, explicit-tick reference lifecycle; NEVER a hardware watchdog.

    A real adapter must enforce duration locally even if its host freezes. This
    mock cannot validate that property, or time a device, or test a browser.
    """

    def __init__(self, profile=None):
        self.profile = profile or OutputProfile()
        self.epoch = 0
        self.armed = False
        self.sequence = 0
        self._last_time = 0.0
        self._last_step = -1
        self._last_emission = -1.0
        self._active = None
        self._events = []

    @property
    def events(self):
        return json.loads(canonical(self._events))

    @property
    def active_frame(self):
        return None if self._active is None else json.loads(canonical(self._active["frame"]))

    def _event(self, kind, now_ms, **values):
        event = {"kind": kind, "at_ms": now_ms, "clock_domain": "synthetic_ms",
                 "epoch": self.epoch, "sequence": self.sequence, **values}
        self._events.append(event)
        return json.loads(canonical(event))

    def tick(self, now_ms):
        if not finite_number(now_ms) or now_ms < self._last_time:
            self._active = None
            self.armed = False
            self._event("stopped", self._last_time, reason="invalid_clock",
                        actuator_levels=[0.0] * self.profile.actuator_count)
            raise ValueError("synthetic clock must be finite, nonnegative, and monotonic")
        self._last_time = now_ms
        if self._active is not None and now_ms >= self._active["expires_at_ms"]:
            deadline = self._active["expires_at_ms"]
            self._active = None
            self._event("expired", now_ms, intended_expiry_ms=deadline,
                        actuator_levels=[0.0] * self.profile.actuator_count)

    def arm(self, now_ms):
        self.tick(now_ms)
        if self.armed:
            raise ValueError("stop the current session before arming again")
        self.epoch += 1
        self.armed = True
        self._last_step = -1
        self._last_emission = -1.0
        self._event("armed", now_ms)
        return self.epoch

    def stop(self, now_ms, reason="stop"):
        if reason not in ("stop", "pause", "disconnect", "complete", "invalid_packet"):
            raise ValueError("unknown stop reason")
        self.tick(now_ms)
        self._active = None
        self.armed = False
        return self._event("stopped", now_ms, reason=reason,
                           actuator_levels=[0.0] * self.profile.actuator_count)

    def deliver(self, packet, *, emitted_at_ms, now_ms, epoch):
        self.tick(now_ms)
        if not self.armed or type(epoch) is not int or epoch != self.epoch:
            return self._event("rejected_session", now_ms)
        try:
            frame = render_frame(packet, self.profile)
            if (not finite_number(emitted_at_ms) or not 0 <= emitted_at_ms <= now_ms):
                raise ValueError("emission and delivery need the same synthetic clock")
        except (ValueError, TypeError):
            self.stop(now_ms, "invalid_packet")
            raise
        # Held packets must neither restart nor extend a pulse. Also reject
        # older asynchronous work, including callbacks from a stopped epoch.
        if packet["emitted_step"] <= self._last_step or emitted_at_ms < self._last_emission:
            return self._event("rejected_order", now_ms)
        self._last_step = packet["emitted_step"]
        self._last_emission = emitted_at_ms
        if now_ms - emitted_at_ms >= self.profile.max_packet_age_ms:
            return self._event("rejected_stale", now_ms)
        self.sequence += 1
        deadline = min(now_ms + self.profile.pulse_ms,
                       emitted_at_ms + self.profile.max_packet_age_ms)
        self._active = {"expires_at_ms": deadline, "frame": frame}
        return self._event("command", now_ms, expires_at_ms=deadline,
                           emitted_at_ms=emitted_at_ms, frame=frame,
                           mock_accepted_at_ms=now_ms, transport_acknowledged_at_ms=None,
                           device_acknowledged_at_ms=None, measured_onset_ms=None)
