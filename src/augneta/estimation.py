"""Causal random-walk Kalman baseline, independent of the simulator and target."""

from dataclasses import dataclass
import math


ESTIMATORS = {"rw-kalman-v1": 0.04, "rw-kalman-v2": 0.12}


@dataclass(frozen=True, slots=True)
class SensorObservation:
    sample_step: int
    available_step: int
    value: tuple[float, float] | None
    dropped: bool

    def __post_init__(self):
        if (type(self.sample_step) is not int or type(self.available_step) is not int
                or not 0 <= self.sample_step <= self.available_step):
            raise ValueError("invalid sensor timestamps")
        if type(self.dropped) is not bool or self.dropped != (self.value is None):
            raise ValueError("missing sensor values require an explicit dropout")
        if self.value is not None:
            if len(self.value) != 2 or not all(math.isfinite(v) for v in self.value):
                raise ValueError("sensor values must be two finite numbers")


@dataclass(frozen=True, slots=True)
class Belief:
    now_step: int
    mean: tuple[float, float]
    variance: float
    last_sample_step: int | None
    sensor_status: str
    dropped: bool
    ignored_stale: int
    estimator_id: str


class CausalEstimator:
    """Stores a posterior at measurement time, then predicts to the present.

    No world, seed, full config, target, action, truth, or future stream is accepted.
    Late samples older than an already assimilated sample are explicitly ignored.
    """

    __slots__ = ("dt_s", "noise_variance", "identity", "q", "mean", "variance",
                 "posterior_step", "last_now", "last_dropped")

    def __init__(self, dt_s, noise_std, identity="rw-kalman-v1"):
        if identity not in ESTIMATORS:
            raise ValueError(f"unknown estimator: {identity}")
        if not math.isfinite(dt_s) or not math.isfinite(noise_std) or min(dt_s, noise_std) <= 0:
            raise ValueError("estimator time and noise scales must be positive and finite")
        self.dt_s = dt_s
        self.noise_variance = noise_std**2
        self.identity = identity
        self.q = ESTIMATORS[identity]
        self.mean = (0.0, 0.0)
        self.variance = 1.0
        self.posterior_step = None
        self.last_now = -1
        self.last_dropped = False

    def update(self, now_step, observations):
        if type(now_step) is not int or now_step <= self.last_now:
            raise ValueError("estimator clock must advance monotonically")
        observations = tuple(observations)
        # Validate the entire batch before touching filter state.
        if any(type(o) is not SensorObservation or o.available_step > now_step
               for o in observations):
            raise ValueError("future or invalid observations are not permitted")
        ignored = 0
        status = "waiting" if self.posterior_step is None else "held"
        for obs in sorted(observations, key=lambda o: (o.sample_step, o.available_step)):
            if self.posterior_step is not None and obs.sample_step <= self.posterior_step:
                ignored += 1
                continue
            self.last_dropped = obs.dropped
            if obs.dropped:
                status = "dropout"
                continue
            previous_step = self.posterior_step if self.posterior_step is not None else 0
            prior = self.variance + self.q * (obs.sample_step - previous_step) * self.dt_s
            gain = prior / (prior + self.noise_variance)
            self.mean = tuple(m + gain * (z - m) for m, z in zip(self.mean, obs.value))
            self.variance = (1 - gain) * prior
            self.posterior_step = obs.sample_step
            status = "fresh"
        posterior_time = self.posterior_step if self.posterior_step is not None else 0
        present_variance = self.variance + self.q * (now_step - posterior_time) * self.dt_s
        self.last_now = now_step
        return Belief(now_step, self.mean, present_variance, self.posterior_step,
                      status, self.last_dropped, ignored, self.identity)
