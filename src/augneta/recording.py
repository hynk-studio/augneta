"""Append-only trial traces and deterministic verification, with private truth files."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
import uuid

from . import __version__
from .config import Config, canonical
from .experiment import ChangeEvent, ORACLE_CONDITION, Trial, evidence


def software_identity():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".js", ".html", ".css"):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    repo = root.parent.parent
    commit = None
    dirty = None
    if (repo / ".git").exists():
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True))
        except (OSError, subprocess.CalledProcessError):
            pass
    return {"package_version": __version__, "source_sha256": digest.hexdigest(),
            "git_commit": commit, "working_tree_dirty": dirty,
            "python": platform.python_version(), "platform": platform.platform()}


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


class Recorder:
    def __init__(self, directory, trial, *, participant_kind, session_id=None, policy_id=None):
        labels = evidence(participant_kind)
        if policy_id is not None and participant_kind != "synthetic":
            raise ValueError("scripted policies must be labelled synthetic")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.metadata = {
            "schema_version": 1, "run_id": str(uuid.uuid4()),
            "session_id": session_id or str(uuid.uuid4()), "trial_id": str(uuid.uuid4()),
            "seed": trial.config.seed, "config": trial.config.to_dict(),
            "config_sha256": trial.config.identity, "software": software_identity(),
            "time_units": {"simulation_time": "seconds", "step": "fixed simulation tick"},
            "condition": trial.condition, "diagnostic": trial.diagnostic,
            "initial_estimator_id": "oracle-truth-v1" if trial.diagnostic else "rw-kalman-v1",
            "initial_encoder_id": "polar8-v1", "policy_id": policy_id,
            "changes": [asdict(e) for e in trial.changes], **labels,
            "truth_file": "evaluation_only.jsonl",
            "truth_access": "offline_evaluator_or_explicit_oracle_only",
            "clock_note": "Simulation time; browser/network latency is not physical stimulus timing.",
        }
        self.started_at = time.monotonic()
        if trial.presentation:
            self.metadata.update(schema_version=2, candidate=trial.candidate,
                                 presentation=trial.presentation.contract(),
                                 initial_encoder_id=trial.presentation.contract()['encoder_id'],
                                 response_provenance='synthetic' if participant_kind == 'synthetic' else 'developer_direct_controls')
            (self.directory / 'lifecycle.jsonl').touch()
            (self.directory / 'transport.jsonl').touch()
        write_json(self.directory / "metadata.json", self.metadata)
        self.__trace = (self.directory / "trace.jsonl").open("x")
        self.__truth = (self.directory / "evaluation_only.jsonl").open("x")
        self.__closed = False

    def append(self, record, evaluation):
        if self.__closed:
            raise ValueError("recording is closed")
        self.__trace.write(canonical(record) + "\n")
        self.__truth.write(canonical(evaluation) + "\n")
        self.__trace.flush()
        self.__truth.flush()

    def transport(self, kind, trial):
        if trial.presentation:
            with (self.directory / 'transport.jsonl').open('a') as out:
                out.write(canonical({'kind': kind, 'step': trial.step,
                    'epoch': trial.presentation.epoch,
                    'server_elapsed_ms': (time.monotonic() - self.started_at) * 1000,
                    'clock_scope': 'server_request_handling_not_browser_render_or_skin_onset',
                    'browser_render_ms': None, 'measured_onset_ms': None}) + '\n')

    def transition(self, trial, action, expected_epoch=None):
        if self.__closed:
            raise ValueError('recording already closed')
        event = trial.transition(action, expected_epoch)
        with (self.directory / 'lifecycle.jsonl').open('a') as out:
            out.write(canonical(event) + '\n')
        self.transport(action, trial)
        return event

    def finish(self, trial):
        if not self.__closed and trial.presentation and trial.presentation.lifecycle not in ('stopped', 'complete'):
            self.transition(trial, 'stop')
        summary = {**trial.summary(), **evidence(self.metadata["participant_kind"])}
        if not self.__closed:
            self.__trace.close()
            self.__truth.close()
            self.__closed = True
            write_json(self.directory / "summary.json", summary)
        return summary


def replay(directory):
    """Re-execute recorded actions and changes; fail on any mismatch or promotion.

    No truth from disk is supplied to a filter or policy. The separate evaluator
    file is compared only after each simulated transition.
    """
    directory = Path(directory)
    metadata = json.loads((directory / "metadata.json").read_text())
    labels = evidence(metadata["participant_kind"])
    if any(metadata.get(k) != v for k, v in labels.items()):
        raise ValueError("evidence labels were promoted or altered")
    if metadata.get("policy_id") is not None and metadata["participant_kind"] != "synthetic":
        raise ValueError("scripted policies must remain labelled synthetic")
    if metadata.get("schema_version") not in (1, 2):
        raise ValueError("unsupported recording schema")
    software = software_identity()
    if any(metadata["software"].get(k) != software[k]
           for k in ("package_version", "source_sha256", "python")):
        raise ValueError("replay requires the recorded implementation and Python version")
    config = Config.from_dict(metadata["config"])
    if metadata.get("config_sha256") != config.identity or metadata.get("seed") != config.seed:
        raise ValueError("configuration identity mismatch")
    oracle = metadata["condition"] == ORACLE_CONDITION
    if type(metadata.get("diagnostic")) is not bool or metadata["diagnostic"] != oracle:
        raise ValueError("oracle diagnostic label mismatch")
    initial_estimator = "oracle-truth-v1" if oracle else "rw-kalman-v1"
    trial = Trial(config, metadata["condition"], oracle=oracle,
                  changes=[ChangeEvent(**e) for e in metadata["changes"]],
                  candidate=metadata.get('candidate'))
    expected_encoder = trial.presentation.contract()['encoder_id'] if trial.presentation else 'polar8-v1'
    if metadata.get('initial_estimator_id') != initial_estimator or metadata.get('initial_encoder_id') != expected_encoder:
        raise ValueError('initial component identity mismatch')
    if (metadata['schema_version'] == 2) != bool(trial.presentation):
        raise ValueError('presentation schema mismatch')
    if trial.presentation and (metadata.get('presentation') != trial.presentation.contract() or
            metadata.get('response_provenance') != ('synthetic' if labels['participant_kind'] == 'synthetic' else 'developer_direct_controls')):
        raise ValueError('presentation contract/provenance mismatch')
    records = [json.loads(line) for line in (directory / "trace.jsonl").read_text().splitlines()]
    truths = [json.loads(line) for line in (directory / "evaluation_only.jsonl").read_text().splitlines()]
    if len(records) != len(truths):
        raise ValueError("trace/evaluation length mismatch")
    events = [json.loads(line) for line in (directory / 'lifecycle.jsonl').read_text().splitlines()] if trial.presentation else []
    event_index = 0
    for index in range(len(records) + 1):
        while event_index < len(events) and events[event_index]['at_step'] == trial.step:
            event = events[event_index]
            if trial.transition(event['action'], event['expected_epoch']) != event:
                raise ValueError('lifecycle replay mismatch')
            event_index += 1
        if index < len(records):
            actual, actual_truth = trial.advance(records[index]['action'])
            if actual != records[index] or actual_truth != truths[index]:
                raise ValueError(f"replay mismatch at step {index}")
    if event_index != len(events) or (trial.presentation and trial.presentation.lifecycle not in ('stopped', 'complete')):
        raise ValueError('unfinished or invalid lifecycle trace')
    summary = json.loads((directory / "summary.json").read_text())
    if summary != {**trial.summary(), **labels}:
        raise ValueError("summary/evidence mismatch")
    return {"replay_verified": True, "steps": len(records), **summary}
