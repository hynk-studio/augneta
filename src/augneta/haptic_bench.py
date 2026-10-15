"""End-to-end synthetic output check, separate from physical experiment scores."""

from pathlib import Path

from .calibration import calibration_plan
from .config import canonical
from .experiment import SYNTHETIC_POLICY_ID, Trial, evidence, synthetic_action
from .haptics import MockOutput, OutputProfile
from .recording import Recorder, replay, software_identity, write_json


def write_calibration_plan(directory, *, seed=7, blocks=2):
    plan = calibration_plan(seed, blocks)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "plan.json", plan)
    # Intentionally no invented responses. This is not a participant-facing UI.
    write_json(directory / "responses.json", [])
    return {"kind": plan["kind"], "plan_sha256": plan["plan_sha256"],
            "planned_trials": len(plan["trials"]), "responses_collected": 0,
            "human_evidence": False, "hardware_verified": False,
            "directory": str(directory)}


def run_haptic_smoke(directory, config):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    profile = OutputProfile()
    output = MockOutput(profile)
    epoch = output.arm(0)
    trial = Trial(config, "sensory_preview")
    recorder = Recorder(directory / "tracking", trial, participant_kind="synthetic",
                        policy_id=SYNTHETIC_POLICY_ID)
    previous_step = -1
    packets = 0
    try:
        while not trial.complete:
            now_ms = trial.step * config.dt_s * 1000
            output.tick(now_ms)
            view = trial.view()
            packet = view["feedback"]
            if packet["emitted_step"] != previous_step:
                previous_step = packet["emitted_step"]
                event = output.deliver(packet, emitted_at_ms=previous_step * config.dt_s * 1000,
                                       now_ms=now_ms, epoch=epoch)
                if event["kind"] != "command" or output.active_frame["feedback_packet"] != packet:
                    raise ValueError("mock output lost the shared semantic packet")
                packets += 1
            # Original held packet, NOT tactile perceptions or the pulse-gated
            # mirror, drives this existing scripted policy. RMSE is not haptic performance.
            recorder.append(*trial.advance(synthetic_action(view, config.control_gain)))
    finally:
        output.stop(trial.step * config.dt_s * 1000, "complete" if trial.complete else "stop")
        recorder.finish(trial)
        (directory / "output_events.jsonl").write_text(
            "".join(canonical(event) + "\n" for event in output.events))
    replay_result = replay(directory / "tracking")
    result = {"kind": "synthetic_haptic_contract_check", **evidence("synthetic"),
              "software": software_identity(), "output_profile": profile.to_dict(),
              "output_profile_sha256": profile.identity, "clock_domain": "synthetic_ms",
              "steps": trial.step, "command_count": packets, "shared_packet_checks": packets,
              "tracking_replay_verified": replay_result["replay_verified"],
              "final_output_stopped": not output.armed and output.active_frame is None,
              "physical_adapter_available": False, "physical_timing_measurements": 0,
              "note": "Policy uses original held packets; tracking RMSE is not haptic performance."}
    write_json(directory / "results.json", result)
    return result
