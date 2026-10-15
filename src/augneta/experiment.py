"""The experiment boundary: direct actions in, explicitly restricted views out."""

from dataclasses import asdict, dataclass
import json

from .config import Config, canonical
from .estimation import Belief, CausalEstimator, ESTIMATORS
from .feedback import Encoder, ENCODERS, decode_force
from .metrics import tracking_error, safe_zone_error
from .simulation import World, clip, validate_action


MAIN_CONDITIONS = ("none", "dashboard", "sensory_preview")
ORACLE_CONDITION = "oracle_diagnostic"
SYNTHETIC_POLICY_ID = "visible-pd-v2"


def evidence(participant_kind):
    if participant_kind not in ("synthetic", "developer"):
        raise ValueError("only synthetic and developer inspection runs are supported")
    return {"participant_kind": participant_kind, "human_evidence": False,
            "hardware_verified": False, "output_mode": "software_only",
            "evidence_scope": "technical_verification" if participant_kind == "synthetic"
            else "developer_inspection_not_participant_study"}


def require_software_output(output):
    if output != "software":
        raise ValueError("physical hardware output is unavailable; no device is operated")


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    step: int
    component: str
    identity: str

    def __post_init__(self):
        choices = {"estimator": ESTIMATORS, "encoder": ENCODERS}
        if type(self.step) is not int or self.step < 0:
            raise ValueError("change event needs a nonnegative integer step")
        if self.component not in choices or self.identity not in choices[self.component]:
            raise ValueError("unknown component or version in change event")


class Trial:
    def __init__(self, config: Config, condition, *, changes=(), oracle=False):
        if condition not in MAIN_CONDITIONS and not (oracle and condition == ORACLE_CONDITION):
            raise ValueError("unknown condition; oracle requires explicit diagnostic access")
        if oracle != (condition == ORACLE_CONDITION):
            raise ValueError("oracle and main conditions must remain separate")
        self.config = config
        self.condition = condition
        self.diagnostic = oracle
        self.changes = tuple(changes)
        if any(type(e) is not ChangeEvent or e.step >= config.steps for e in self.changes):
            raise ValueError("change events must occur within the trial")
        if len({(e.step, e.component) for e in self.changes}) != len(self.changes):
            raise ValueError("ambiguous simultaneous component changes")
        if oracle and self.changes:
            raise ValueError("oracle diagnostics do not support model changes")
        self.__world = World(config)
        self.__estimator = CausalEstimator(config.dt_s, config.sensor_noise_std)
        self.__encoder = Encoder()
        self.__packet = None
        self.__states = []
        self.__prepare()

    @property
    def step(self):
        return self.__world.step

    @property
    def complete(self):
        return self.step == self.config.steps

    def __prepare(self):
        self.__events = []
        for event in self.changes:
            if event.step == self.step:
                if event.component == "estimator":
                    previous = self.__estimator.identity
                    self.__estimator = CausalEstimator(
                        self.config.dt_s, self.config.sensor_noise_std, event.identity)
                else:
                    previous = self.__encoder.identity
                    self.__encoder = Encoder(event.identity)
                self.__events.append({**asdict(event), "previous_identity": previous,
                                      "state_transfer": "reset" if event.component == "estimator"
                                      else "stateless"})
        self.__observations = self.__world.observations()
        if self.diagnostic:
            self.__belief = Belief(self.step, tuple(self.__world.evaluation_only()["flow"]),
                                   0.0, self.step, "oracle_diagnostic", False, 0, "oracle-truth-v1")
        else:
            self.__belief = self.__estimator.update(self.step, self.__observations)
        # Version changes cause a logged immediate emission, equally in both displays.
        if self.step % self.config.feedback_period_steps == 0 or self.__events:
            self.__packet = self.__encoder.encode(self.__belief)

    def view(self):
        """The only object provided to a renderer or synthetic decision policy."""
        visible = self.__world.visible().to_dict()
        objective = {"kind": self.config.task}
        if self.config.task == "safe_zone":
            del visible["target"]  # Not part of this task's display or policy input.
            objective.update(shape="closed_square", center=[0.0, 0.0],
                             half_width=self.config.safe_zone_half_width)
        return {"visible": visible,
                "task": self.config.task, "objective": objective, "condition": self.condition,
                "diagnostic": self.diagnostic, "complete": self.complete,
                "feedback": self.__packet.to_dict() if self.condition != "none" else None}

    def advance(self, action):
        if self.complete:
            raise ValueError("trial is already complete")
        action = validate_action(action)
        before = self.__world.visible().to_dict()
        evaluation = self.__world.evaluation_only()
        intended = self.view()["feedback"]
        after = self.__world.advance(action).to_dict()
        self.__states.append(after)
        record = {"step": before["step"], "time_s": before["time_s"],
                  "visible_before": before, "visible_after": after,
                  "sensor_observations": [asdict(o) for o in self.__observations],
                  "belief": asdict(self.__belief), "feedback_packet": self.__packet.to_dict(),
                  "action": list(action), "applied_action": list(action),
                  "intended_feedback": intended, "output_acknowledgement": None,
                  "events": self.__events}
        if not self.complete:
            self.__prepare()
        # JSON-shaped values make serialized and in-memory comparisons identical.
        return json.loads(canonical(record)), evaluation

    def summary(self):
        if self.config.task == "safe_zone":
            metric = safe_zone_error(self.__states, config=self.config, completed=self.complete)
        else:
            metric = tracking_error(self.__states, start_step=self.config.evaluation_start_step,
                                    end_step=self.config.evaluation_end_step,
                                    arena_half_width=self.config.arena_half_width, completed=self.complete)
        return {"condition": self.condition, "diagnostic": self.diagnostic,
                "task": self.config.task, "completed_steps": self.step,
                **metric}


def synthetic_action(view, control_gain):
    """Scripted PD smoke policy; only receives what the display may receive.

    This is never called by the interactive app and is not human evidence.
    """
    state = view["visible"]
    force = decode_force(view["feedback"])
    target = [0.0, 0.0] if view["task"] == "safe_zone" else state["target"]
    return tuple(clip((5.0 * (t - p) - 2.4 * v - f) / control_gain, -1.0, 1.0)
                 for t, p, v, f in zip(target, state["position"], state["velocity"], force))
