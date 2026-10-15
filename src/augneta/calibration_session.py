"""A visual rehearsal of calibration, with separate fit and holdout responses.

This is not tactile stimulation, a perceptually calibrated profile, or a study.
Only the server holds the stimulus schedule; export is available after stopping.
"""

from collections import Counter
import json
from pathlib import Path
import random
import time
import uuid

from .config import canonical
from .tactile import TactileProfile


def schedule(profile, seed):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be a uint32")
    phases = {}
    for name, salt in (("fit", 0xA617), ("validation", 0x6CA1)):
        codes = [profile.spec.code(d, level) for d in range(profile.spec.directions)
                 for level in range(1, profile.spec.levels + 1)]
        codes += [profile.spec.code(None, 0)] * 2
        random.Random(seed ^ salt).shuffle(codes)
        phases[name] = codes
    return phases


def score(records, spec):
    confusion = [[0] * (spec.directions + 2) for _ in range(spec.directions + 1)]
    magnitude = [[0] * (spec.levels + 2) for _ in range(spec.levels + 1)]
    correct = 0
    for r in records:
        expected, answer = r["expected"], r["response"]
        row = spec.directions if expected["direction"] is None else expected["direction"]
        if answer["kind"] == "unknown":
            column = spec.directions + 1
        else:
            column = spec.directions if answer["direction"] is None else answer["direction"]
        confusion[row][column] += 1
        magnitude[expected["level"]][spec.levels + 1 if answer["kind"] == "unknown" else answer["level"]] += 1
        correct += int(answer["kind"] != "unknown" and
                       (answer["direction"], answer["level"]) ==
                       (expected["direction"], expected["level"]))
    return {"answered": len(records), "joint_correct": correct,
            "joint_accuracy": correct / len(records) if records else None,
            "direction_confusion": confusion,
            "magnitude_confusion": magnitude,
            "rows": [f"D{i}" for i in range(spec.directions)] + ["zero"],
            "columns": [f"D{i}" for i in range(spec.directions)] + ["zero", "unknown"],
            "response_counts": dict(Counter(r["response"]["kind"] for r in records)),
            "inference": "visual_rehearsal_only"}


class CalibrationSession:
    def __init__(self, root, profile=None, seed=7, participant_kind="developer", clock=time.monotonic):
        if participant_kind not in ("developer", "synthetic"):
            raise ValueError("this workflow supports development rehearsal only")
        self.profile = profile or TactileProfile()
        self.plan = schedule(self.profile, seed)
        self.id = str(uuid.uuid4())
        self.directory = Path(root) / self.id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.clock = clock
        self.started_at = clock()
        self.seed = seed
        self.phase = "fit"
        self.state = "ready"
        self.index = 0
        self.records = {"fit": [], "validation": []}
        self.presentations = []
        self.fit_profile = self.profile.to_dict()
        self.validation_profile = None
        self.participant_kind = participant_kind
        self.events = []
        self._event("started")

    def labels(self):
        return {"output_mode": "visual_rehearsal", "participant_kind": self.participant_kind,
                "response_provenance": "synthetic" if self.participant_kind == "synthetic" else "developer_visual_rehearsal",
                "human_evidence": False, "hardware_verified": False,
                "evidence_scope": "software_workflow_not_tactile_calibration"}

    def _event(self, kind, **values):
        self.events.append({"kind": kind, "host_elapsed_ms": (self.clock() - self.started_at) * 1000,
                            "phase": self.phase, "index": self.index, **values})
        self.save()

    def save(self):
        data = self.export_data()
        pending = self.directory / "session.json.tmp"
        pending.write_text(canonical(data) + "\n", encoding="utf-8")
        pending.replace(self.directory / "session.json")

    def view(self):
        reports = {}
        if len(self.records["fit"]) == len(self.plan["fit"]) or self.state == "stopped":
            reports["fit"] = score(self.records["fit"], self.profile.spec)
        if self.state in ("complete", "stopped"):
            reports["validation"] = score(self.records["validation"], self.profile.spec)
        return {"session_id": self.id, "phase": self.phase, "state": self.state,
                "index": self.index, "phase_total": len(self.plan[self.phase]),
                "profile": self.profile.to_dict(), "profile_sha256": self.profile.identity,
                "reports": reports, **self.labels()}

    def present(self, expected_index):
        if self.state != "ready" or type(expected_index) is not int or expected_index != self.index:
            raise ValueError("presentation is duplicate, stale, or not ready")
        code = self.plan[self.phase][self.index]
        command = self.profile.render(code)
        self.presented_at = self.clock()
        self.presentations.append({"phase": self.phase, "index": self.index, "command": command,
                                   "host_elapsed_ms": (self.presented_at - self.started_at) * 1000,
                                   "measured_onset_ms": None, "device_acknowledged_at_ms": None})
        self.state = "awaiting_response"
        self._event("command_previewed")
        # No expected direction/level, seed, future schedule or correctness feedback.
        return {**self.view(), "stimulus": command}

    def respond(self, expected_index, response):
        if (self.state != "awaiting_response" or type(expected_index) is not int or
                expected_index != self.index):
            raise ValueError("response is duplicate, stale, or has no presentation")
        if (self.clock() - self.presented_at) * 1000 + 1e-6 < self.profile.pulse_ms + self.profile.gap_ms:
            raise ValueError("wait for the preview pulse and gap before responding")
        if not isinstance(response, dict) or set(response) != {"kind", "direction", "level"}:
            raise ValueError("response fields mismatch")
        kind = response["kind"]
        if kind == "unknown":
            if response["direction"] is not None or response["level"] is not None:
                raise ValueError("unknown response cannot include a guess")
        elif kind in ("identified", "zero"):
            self.profile.spec.code(response["direction"], response["level"])
            if (kind == "zero") != (response["level"] == 0):
                raise ValueError("zero and identified responses must remain distinct")
        else:
            raise ValueError("unknown response kind")
        self.records[self.phase].append({"index": self.index,
            "expected": self.plan[self.phase][self.index], "response": dict(response),
            "profile_sha256": self.profile.identity,
            "server_response_interval_ms": (self.clock() - self.presented_at) * 1000,
            "interval_scope": "includes_transport_not_perceptual_reaction_time"})
        self.index += 1
        self.state = "ready" if self.index < len(self.plan[self.phase]) else (
            "review" if self.phase == "fit" else "complete")
        self._event("response_recorded")
        return self.view()

    def freeze(self, profile):
        if self.state != "review":
            raise ValueError("finish the fit block before freezing a profile")
        if profile.spec != self.profile.spec or profile.patterns != self.profile.patterns:
            raise ValueError("meaning and patterns must stay fixed; start a new session to change them")
        self.profile = profile
        self.validation_profile = profile.to_dict()
        self.phase, self.index, self.state = "validation", 0, "ready"
        self._event("profile_frozen", selection_method="manual_rehearsal_configuration",
                    profile_sha256=profile.identity)
        return self.view()

    def stop(self):
        if self.state not in ("stopped", "complete"):
            self.state = "stopped"
            self._event("stopped")
        return self.view()

    def export_data(self):
        return {"schema_version": 1, "kind": "calibration_visual_rehearsal", "session_id": self.id,
                "state": self.state, "phase": self.phase, "seed": self.seed,
                "fit_profile": self.fit_profile, "validation_profile": self.validation_profile,
                "planned_per_phase": {k: len(v) for k, v in self.plan.items()},
                "responses": self.records, "presentations": self.presentations, "events": self.events,
                "reports": {k: score(v, self.profile.spec) for k, v in self.records.items()},
                "profile": self.profile.to_dict(), "profile_sha256": self.profile.identity,
                "profile_status": "unvalidated_hardware_candidate", **self.labels()}

    def export(self):
        if self.state not in ("complete", "stopped"):
            raise ValueError("stop or finish the session before exporting response records")
        return json.loads(canonical(self.export_data()))
