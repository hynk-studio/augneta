"""Observations, candidate layouts and counterfactual scoring for the P1 gate task."""

import math
from copy import deepcopy
from dataclasses import dataclass

from augneta.config import Config
from augneta.experiment import Trial
from augneta.simulation import World


OBSERVE_TICKS = 24
HORIZON_TICKS = 32
THROTTLE_DIVISIONS = 20
MIN_THROTTLE_GAP = 2  # Two grid intervals (0.10 of maximum input).
DEVELOPMENT_SEEDS = 48
CONFIRMATION_SEEDS = 80
ANGLES = tuple(i * math.tau / 8 for i in range(8))
SIDES = ("left", "right")
GOALS = ("reach", "release")


@dataclass(frozen=True)
class Layout:
    name: str
    center: tuple
    distance: float
    bearing_deg: float
    radius: float
    first_seed: int

    def geometry(self):
        theta = math.radians(self.bearing_deg)
        dx, dy = self.distance * math.cos(theta), self.distance * math.sin(theta)
        x, y = self.center
        return {"center": self.center, "left": (x - dx, y - dy), "right": (x + dx, y + dy),
                "radius": self.radius}


DEVELOPMENT = (
    Layout("D1", (0., 0.), .37, 0., .15, 1100),
    Layout("D2", (-.05, .06), .43, 16., .16, 2100),
)
CONFIRMATION = (
    Layout("C1", (.03, -.05), .39, -12., .15, 10100),
    Layout("C2", (-.06, -.02), .42, 8., .17, 20100),
    Layout("C3", (.05, .04), .36, 23., .14, 30100),
    Layout("C4", (-.03, .06), .45, -21., .17, 40100),
)


def observe(config, geometry):
    """Read the ordinary display view through decision time. No scoring world is used."""
    trial = Trial(config, "sensory_preview")
    drift = []
    while True:
        view = trial.view()
        position = view["visible"]["position"]
        drift.append(tuple(p + c for p, c in zip(position, geometry["center"])))
        if trial.step == OBSERVE_TICKS:
            break
        trial.advance((0., 0.))
    packet = view["feedback"]
    if packet["encoder_id"] != "polar8-v1" or packet["channel_offset"] != 0 or packet["estimator_id"] != "rw-kalman-v1":
        raise ValueError("The gate study uses the fixed polar8-v1 code and rw-kalman-v1 estimator.")
    signal = {k: packet[k] for k in ("channels", "uncertainty_level", "age_steps", "dropped", "sensor_status")}
    return signal, drift


def gate_axis(geometry):
    dx, dy = (b - a for a, b in zip(geometry["left"], geometry["right"]))
    length = math.hypot(dx, dy)
    return dx / length, dy / length


def projection(vector, axis):
    return sum(x * y for x, y in zip(vector, axis))


def direction(amount):
    if abs(amount) < 1e-9:
        return None
    return "right" if amount > 0 else "left"


def opposite(side):
    return "right" if side == "left" else "left"


def crosses_disk(start, end, target, radius):
    """Include between-tick crossings of the closed target disk."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    t = ((target[0] - start[0]) * dx + (target[1] - start[1]) * dy) / length2 if length2 else 0.
    t = max(0., min(1., t))
    return math.hypot(start[0] + t * dx - target[0], start[1] + t * dy - target[1]) <= radius


def arrives(at_choice, start, target, action, radius):
    world = deepcopy(at_choice)
    world.position, world.velocity = tuple(start), (0., 0.)
    for _ in range(HORIZON_TICKS):
        previous = world.position
        world.advance(action)
        if crosses_disk(previous, world.position, target, radius):
            return True
    return False


def physical_outcomes(config, geometry):
    """Offline evaluator only. Launch both alternatives at exactly the decision tick."""
    at_choice = World(config)
    for _ in range(OBSERVE_TICKS):
        at_choice.advance((0., 0.))
    axis = gate_axis(geometry)
    flow_side = direction(projection(at_choice.evaluation_only()["flow"], axis))
    thrust, hits = {}, {}
    center, radius = geometry["center"], geometry["radius"]
    for side, sign in zip(SIDES, (-1, 1)):
        gate = geometry[side]
        thrust[side] = None
        for level in range(THROTTLE_DIVISIONS + 1):
            action = tuple(sign * level / THROTTLE_DIVISIONS * a for a in axis)
            if arrives(at_choice, center, gate, action, radius):
                thrust[side] = level
                break
        hits[side] = arrives(at_choice, gate, center, (0., 0.), radius)
    return flow_side, thrust, hits


def grade(flow_side, thrust, hits):
    if None in thrust.values():
        return None, "unreachable_gate"
    if abs(thrust["left"] - thrust["right"]) < MIN_THROTTLE_GAP:
        return None, "thrust_tie_or_small_margin"
    if sum(hits.values()) != 1:
        return None, "both_markers_hit" if all(hits.values()) else "neither_marker_hit"
    reach = min(thrust, key=thrust.get)
    release = next(side for side in SIDES if hits[side])
    if reach == release:
        return None, "goals_do_not_reverse"
    if reach != flow_side:
        return None, "departure_disagrees_with_current_at_choice"
    return {"reach": reach, "release": release}, "eligible"


def signal_direction(signal, axis):
    # The fixed display exposes anonymous channel intensities. Decode only those.
    channels = signal["channels"]
    x = sum(v * math.cos(a) for v, a in zip(channels, ANGLES))
    y = sum(v * math.sin(a) for v, a in zip(channels, ANGLES))
    return direction(projection((x, y), axis))


def motion_direction(trail, axis, dt, drag):
    # Infer acceleration from the last three screen positions of an undriven marker.
    # The velocity update uses the previous velocity for drag.
    a, b, c = trail[-3:]
    old_v = tuple((q - p) / dt for p, q in zip(a, b))
    new_v = tuple((q - p) / dt for p, q in zip(b, c))
    force = tuple((v - u) / dt + drag * u for u, v in zip(old_v, new_v))
    return direction(projection(force, axis))


def decisions(goal, geometry, signal, trail, dt, drag):
    axis = gate_axis(geometry)
    sensed = signal_direction(signal, axis) or "right"
    visible = motion_direction(trail, axis, dt, drag) or "right"
    return {
        "always_left": "left",
        "always_right": "right",
        "goal_only": "right" if goal == "reach" else "left",
        "follow_code": sensed,
        "oppose_code": opposite(sensed),
        "screen_and_goal": visible if goal == "reach" else opposite(visible),
        "code_and_goal": sensed if goal == "reach" else opposite(sensed),
    }


def measure_case(layout, seed):
    config, geometry = Config(seed=seed), layout.geometry()
    signal, drift = observe(config, geometry)
    flow, thrust, hits = physical_outcomes(config, geometry)
    answers, reason = grade(flow, thrust, hits)
    anchored = [geometry["center"]] * len(drift)
    choices, drifting_choices = {}, {}
    for goal in GOALS:
        choices[goal] = decisions(goal, geometry, signal, anchored, config.dt_s, config.drag)
        drifting_choices[goal] = decisions(goal, geometry, signal, drift, config.dt_s, config.drag)["screen_and_goal"]
    return {"map": layout.name, "seed": seed, "geometry": geometry, "signal": signal,
            "flow": flow, "thrust": thrust, "hits": hits, "answers": answers, "reason": reason,
            "choices": choices, "drifting_screen": drifting_choices,
            "signal_direction": signal_direction(signal, gate_axis(geometry))}
