"""Bounded, frozen synthetic diagnostic; paired seeds are the reporting units."""

from dataclasses import replace
import hashlib
import math
from pathlib import Path

from .config import Config, canonical
from .experiment import MAIN_CONDITIONS, SYNTHETIC_POLICY_ID, Trial, evidence, synthetic_action
from .recording import software_identity, write_json

# Retained verbatim after inspection of the initial attempt's check results.
# Re-running these seeds is reproducibility, not a new unseen holdout.
DEVELOPMENT_SEEDS = (7, 19, 31)
CHECK_SEEDS = (101, 113, 127)
FLOW_STRENGTHS = (0.0, 0.65, 1.8)
SENSOR_DELAYS = (0, 4, 24)
PRIMARY_METRICS = {"tracking": "normalized_tracking_rmse", "safe_zone": "normalized_outside_distance"}


def _axis(values, name, limit):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= limit:
        raise ValueError(f"{name} must have 1..{limit} values")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError(f"{name} values must be finite numbers")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} values must be unique")


def validate_design(development, check, strengths, delays):
    for seeds in (development, check):
        _axis(seeds, "seed split", 16)
        for seed in seeds:
            Config(seed=seed)
    if set(development) & set(check):
        raise ValueError("development and check seeds must be disjoint")
    _axis(strengths, "flow strengths", 5)
    _axis(delays, "sensor delays", 5)
    for strength in strengths:
        if not 0 <= strength <= 3:
            raise ValueError("diagnostic strength must be in [0, 3]")
        for delay in delays:
            Config(flow_strength=strength, sensor_delay_steps=delay)
            if delay > 100:
                raise ValueError("diagnostic sensor delay must be <=100 ticks")


def diagnostic_design(development=DEVELOPMENT_SEEDS, check=CHECK_SEEDS,
                      strengths=FLOW_STRENGTHS, delays=SENSOR_DELAYS):
    validate_design(development, check, strengths, delays)
    frozen = (tuple(development), tuple(check), tuple(strengths), tuple(delays)) == (
        DEVELOPMENT_SEEDS, CHECK_SEEDS, FLOW_STRENGTHS, SENSOR_DELAYS)
    return {"version": "sensitivity-v1" if frozen else "custom_diagnostic",
            "development_seeds": list(development), "check_seeds": list(check),
            "flow_strengths": list(strengths), "sensor_delay_steps": list(delays),
            "base_config": Config().to_dict(), "tasks": ["tracking", "safe_zone"],
            "conditions": list(MAIN_CONDITIONS), "policy_id": SYNTHETIC_POLICY_ID,
            "estimator_id": "rw-kalman-v1", "encoder_id": "polar8-v1",
            "tuning": "Frozen before either split; no check-split tuning in v1" if frozen
                      else "Custom settings; not the frozen v1 design",
            "delay_kind": "sensor observation availability only; not feedback/network/stimulus latency"}


def _digest():
    return hashlib.sha256()


def _update(digest, value):
    digest.update((canonical(value) + "\n").encode())


def _run(config, condition):
    trial = Trial(config, condition)
    inputs, trajectory, sensors = _digest(), _digest(), _digest()
    saturated = at_boundary = 0
    while not trial.complete:
        view = trial.view()
        # This is the entire policy input. No record, belief, truth, or seed enters it.
        action = synthetic_action(view, config.control_gain)
        _update(inputs, {"visible": view["visible"], "feedback": view["feedback"],
                         "task": view["task"], "objective": view["objective"]})
        record, _ = trial.advance(action)
        _update(trajectory, {"before": record["visible_before"], "action": record["action"],
                             "after": record["visible_after"]})
        _update(sensors, record["sensor_observations"])
        if config.evaluation_start_step < trial.step <= config.evaluation_end_step:
            saturated += any(abs(v) == 1 for v in action)
            at_boundary += any(abs(v) == config.arena_half_width for v in record["visible_after"]["position"])
    summary = trial.summary()
    samples = config.evaluation_end_step - config.evaluation_start_step
    metric = PRIMARY_METRICS[config.task]
    return {"summary": summary,
            "policy_inputs_sha256": inputs.hexdigest(), "trajectory_sha256": trajectory.hexdigest(),
            "sensor_stream_sha256": sensors.hexdigest(),
            "window_diagnostics": {"action_saturation_fraction": saturated / samples,
                                   "arena_boundary_fraction": at_boundary / samples,
                                   "metric_floor": summary[metric] <= 1e-12,
                                   "metric_near_ceiling": summary[metric] >= 0.95,
                                   "outside_fraction_near_ceiling": (
                                       summary["outside_fraction"] >= 0.95 if config.task == "safe_zone" else None)}}


def _pair(config):
    runs = {condition: _run(config, condition) for condition in MAIN_CONDITIONS}
    summaries = {k: r["summary"] for k, r in runs.items()}
    metric = PRIMARY_METRICS[config.task]
    metrics = [metric] if config.task == "tracking" else [metric, "outside_fraction", "outside_time_s"]
    contrasts = {k: {m: summaries[k][m] - summaries["none"][m] for m in metrics}
                 for k in MAIN_CONDITIONS[1:]}
    # A shared final score alone cannot establish equal information or trajectories.
    matched = all(runs["dashboard"][key] == runs["sensory_preview"][key]
                  for key in ("policy_inputs_sha256", "trajectory_sha256", "sensor_stream_sha256"))
    return {"seed": config.seed, "config": config.to_dict(), "config_sha256": config.identity,
            "summaries": summaries, "audits": {k: {f: v for f, v in r.items() if f != "summary"}
                                               for k, r in runs.items()},
            "paired_differences_vs_none": {k: contrasts[k][metric] for k in contrasts},
            "paired_metric_differences_vs_none": contrasts,
            "matched_views_identical": matched,
            "sensor_streams_matched": len({r["sensor_stream_sha256"] for r in runs.values()}) == 1,
            "floor_conditions": [k for k, r in runs.items() if r["window_diagnostics"]["metric_floor"]],
            "ceiling_conditions": [k for k, r in runs.items() if r["window_diagnostics"]["metric_near_ceiling"]]}


def _split_cells(design, split):
    base = Config.from_dict(design["base_config"])
    cells = []
    for task in design["tasks"]:
        for strength in design["flow_strengths"]:
            for delay in design["sensor_delay_steps"]:
                pairs = [_pair(replace(base, task=task, seed=seed, flow_strength=strength,
                                       sensor_delay_steps=delay)) for seed in design[f"{split}_seeds"]]
                cells.append({"split": split, "task": task, "flow_strength": strength,
                              "sensor_delay_steps": delay, "sensor_delay_s": delay * base.dt_s,
                              "metric": PRIMARY_METRICS[task], "lower_is_better": True, "pairs": pairs,
                              "mean_paired_difference_vs_none": {
                                  k: math.fsum(p["paired_differences_vs_none"][k] for p in pairs) / len(pairs)
                                  for k in MAIN_CONDITIONS[1:]},
                              "zero_flow_degenerate": strength == 0})
    return cells


def diagnostic_results(*, development=DEVELOPMENT_SEEDS, check=CHECK_SEEDS,
                       strengths=FLOW_STRENGTHS, delays=SENSOR_DELAYS, directory=None):
    design = diagnostic_design(development, check, strengths, delays)
    result = {"schema_version": 2, "kind": "synthetic_task_sensitivity_diagnostic", **evidence("synthetic"),
              "design": design, "design_sha256": hashlib.sha256(canonical(design).encode()).hexdigest(),
              "source": software_identity(),
              "run_context": "v1 settings retained after review of initial check results; rerun is not a fresh holdout",
              "interpretation": "Seed-level descriptive differences; correlated ticks are not independent samples. "
                                "New seeds and a scripted policy do not establish learned human transfer. "
                                "Delay need not have a monotonic effect. No inferential significance tests.",
              "diagnostic_definitions": {
                  "metric_floor": "primary metric <=1e-12", "metric_near_ceiling": "primary metric >=0.95",
                  "outside_fraction_near_ceiling": "safe-zone occupancy outside >=0.95",
                  "action_saturation_fraction": "window ticks with any applied action component at +/-1 / window ticks",
                  "arena_boundary_fraction": "window ticks with point on any arena boundary / window ticks",
                  "note": "Descriptive software flags; normalized RMSE need not reach 1 with an interior target."}}
    if directory is not None:
        write_json(directory / "design.json", result)  # freeze complete provenance before either split
    cells = []
    for split in ("development", "check"):
        split_cells = _split_cells(design, split)
        if directory is not None:
            write_json(directory / f"{split}.json", {**result, "cells": split_cells})
        cells.extend(split_cells)
    return {**result, "cells": cells,
            "pairing_verified": all(p["matched_views_identical"] and p["sensor_streams_matched"]
                                    for c in cells for p in c["pairs"])}


def run_diagnostic(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    result = diagnostic_results(directory=directory)
    write_json(directory / "results.json", result)
    return {"results_file": str(directory / "results.json"), "cells": len(result["cells"]),
            "pairing_verified": result["pairing_verified"], "design_sha256": result["design_sha256"],
            **evidence("synthetic")}
