"""CPU-only smoke, replay, and development server entry points."""

import argparse
import json
from pathlib import Path
import sys
import uuid

from .config import Config
from .experiment import MAIN_CONDITIONS, ORACLE_CONDITION, Trial, require_software_output, synthetic_action
from .recording import Recorder, replay, write_json


def run_smoke(directory, config, *, oracle=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    conditions = (ORACLE_CONDITION,) if oracle else MAIN_CONDITIONS
    session_id = str(uuid.uuid4())
    reports = []
    for condition in conditions:
        trial = Trial(config, condition, oracle=oracle)
        recorder = Recorder(directory / condition, trial, participant_kind="synthetic",
                            session_id=session_id, policy_id="visible-pd-v1")
        try:
            while not trial.complete:
                action = synthetic_action(trial.view(), config.control_gain)
                recorder.append(*trial.advance(action))
        finally:
            report = recorder.finish(trial)
        verified = replay(directory / condition)
        reports.append({**report, "replay_verified": verified["replay_verified"],
                        "recording": str(directory / condition)})
    result = {"kind": "oracle_diagnostic" if oracle else "synthetic_smoke",
              "participant_kind": "synthetic", "human_evidence": False,
              "hardware_verified": False, "results": reports}
    write_json(directory / "results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Augneta development experiment; no hardware or human-study claims")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "oracle-smoke"):
        command = commands.add_parser(name)
        command.add_argument("--out", type=Path, required=True, help="new output directory (never overwritten)")
        command.add_argument("--seed", type=int, help="override config seed (default config uses 7)")
        command.add_argument("--config", type=Path, help="JSON configuration overrides")
        command.add_argument("--output", default="software", choices=("software", "hardware"))
    replay_parser = commands.add_parser("replay")
    replay_parser.add_argument("directory", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--log-dir", type=Path, default=Path("runs/ui"))
    serve.add_argument("--participant-kind", choices=("developer", "synthetic"), default="developer")
    serve.add_argument("--config", type=Path, help="JSON configuration overrides; seed is selected in the UI")
    serve.add_argument("--public-origin", help="one trusted preview origin (scheme://host[:port]); forwarded headers remain untrusted")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .web import create_app
            config = Config.from_dict(json.loads(args.config.read_text())) if args.config else Config()
            create_app(args.log_dir, participant_kind=args.participant_kind, config=config,
                       public_origin=args.public_origin).run(
                host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
            return 0
        if args.command == "replay":
            result = replay(args.directory)
        else:
            require_software_output(args.output)
            values = json.loads(args.config.read_text()) if args.config else {}
            if not isinstance(values, dict):
                raise ValueError("config must be a JSON object")
            if args.seed is not None:
                values["seed"] = args.seed
            result = run_smoke(args.out, Config.from_dict(values), oracle=args.command == "oracle-smoke")
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"augneta: {error}", file=sys.stderr)
        return 2
