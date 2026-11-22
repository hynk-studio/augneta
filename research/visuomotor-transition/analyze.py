"""Reanalyze the baseline-corrected reaching data from Modchalingam et al. (2023)."""

import argparse
import hashlib
from io import StringIO
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, StrMethodFormatter
import numpy as np
import pandas as pd
from scipy import stats


SOURCE = {
    "paper_doi": "10.1038/s41598-023-32068-8",
    "file_record": "https://api.osf.io/v2/files/6279ce1247df8504916f00fd/",
    "download": "https://osf.io/download/es9m7/?revision=1",
    "version": 1,
    "sha256": "79bb76e60114d59210e70c80f2ccc352e3e03554f2f57721ca3c0411a1099d06",
}
GROUPS = {"abrupt": "Abrupt", "ramped": "Ramp", "stepped": "Step"}
PERSON = ["exp", "ppt"]
BOOTSTRAP_SEED = 20261122
BOOTSTRAP_RESAMPLES = 10000


def load_trials(path):
    with path.open("rb") as source_file:
        if hashlib.file_digest(source_file, "sha256").hexdigest() != SOURCE["sha256"]:
            raise ValueError("Input does not match OSF version 1. Check the download and SHA-256.")
        source_file.seek(0)
        trials = pd.read_csv(source_file)

    audit = {
        "rows": len(trials),
        "participants": len(trials[PERSON].drop_duplicates()),
        "cursor_reaches": int(trials["reach_type"].eq("reach").sum()),
        "no_cursor_reaches": int(trials["reach_type"].eq("nocursor").sum()),
        "rows_with_missing_cells": int(trials.isna().any(axis=1).sum()),
        "duplicated_trial_keys": int(trials.duplicated([*PERSON, "trial_num_cont"]).sum()),
        "nonfinite_normalized_deviations": int((~np.isfinite(trials["norm_angular_dev"])).sum()),
    }
    used_angles = trials[["rotation_angle", "angular_dev", "block_num_detailed"]]
    if audit["duplicated_trial_keys"] or not np.isfinite(used_angles).all().all():
        raise ValueError("A trial key is duplicated or an angle or block used in the analysis is missing.")

    # block_num marks selected trial sets (and uses 10 for many training reaches).
    # The integer part of the detailed field identifies the actual rotated block.
    trials["block"] = np.floor(trials["block_num_detailed"]).astype(int)
    return trials.sort_values([*PERSON, "trial_num_cont"]), audit


def participant_measures(trials):
    cursor = trials.loc[trials["reach_type"].eq("reach")].copy()
    # Positive hand deviations compensate negative (clockwise) rotations.
    residual = cursor["angular_dev"] + cursor["rotation_angle"]
    cursor["abs_error"] = ((residual + 180) % 360 - 180).abs()
    cursor["rotation_size"] = cursor["rotation_angle"].abs()
    cursor["at_60"] = cursor["rotation_size"].eq(60)
    transition = cursor.loc[cursor["block"].between(1, 3)]
    final = cursor.loc[cursor["block"].eq(4)]
    no_cursor = trials.loc[trials["reach_type"].eq("nocursor")]
    probe = no_cursor.loc[no_cursor["block"].eq(4) & no_cursor["strat_use"].eq(0)]

    people = transition.groupby(PERSON).agg(
        transition_error_deg_reaches=("abs_error", "sum"),
        transition_cursor_reaches=("abs_error", "size"),
        transition_rotation_deg_reaches=("rotation_size", "sum"),
        transition_60deg_cursor_reaches=("at_60", "sum"),
    )
    people["transition_no_cursor_reaches"] = no_cursor.loc[
        no_cursor["block"].between(1, 3)
    ].groupby(PERSON).size()
    final_groups = final.groupby(PERSON)
    people["final_cursor_reaches"] = final_groups.size()
    people["final_cursor_error_deg"] = final_groups["abs_error"].mean()
    last_six = final_groups.tail(6)
    people["last_six_hand_deviation_deg"] = last_six.groupby(PERSON)["angular_dev"].mean()
    people["final_without_strategy_reaches"] = probe.groupby(PERSON).size()
    people["final_aftereffect_deg"] = probe.groupby(PERSON)["angular_dev"].mean()
    if people.isna().any().any() or not final["rotation_size"].eq(60).all():
        raise ValueError("Incomplete participant measurements or unexpected terminal rotation.")
    return people


def mean_interval(values):
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    half_width = float(stats.t.ppf(0.975, len(values) - 1) * sd / np.sqrt(len(values)))
    return {"mean": mean, "sd": sd, "ci95": [mean - half_width, mean + half_width]}


def spearman_rho(x, y, axis):
    return stats.spearmanrho(x, y, axis=axis).statistic


def paired_correlation(cost, final):
    x, y = cost.to_numpy(), final.to_numpy()
    interval = stats.bootstrap(
        (x, y), spearman_rho, paired=True, vectorized=True, batch=256,
        n_resamples=BOOTSTRAP_RESAMPLES, rng=np.random.default_rng(BOOTSTRAP_SEED),
        method="percentile",
    ).confidence_interval
    return {
        "rho": float(spearman_rho(x, y, axis=0)),
        "paired_percentile_ci95": [float(interval.low), float(interval.high)],
    }


def summarize_group(group):
    exposure_columns = [
        "transition_cursor_reaches", "transition_no_cursor_reaches",
        "transition_rotation_deg_reaches", "transition_60deg_cursor_reaches",
        "final_cursor_reaches", "final_without_strategy_reaches",
    ]
    # Each schedule in this release has identical exposure for all its participants.
    exposure = {column: int(group[column].unique().item()) for column in exposure_columns}
    outcomes = [
        "transition_error_deg_reaches", "final_cursor_error_deg",
        "final_aftereffect_deg", "last_six_hand_deviation_deg",
    ]
    cost = group["transition_error_deg_reaches"]
    correlations = {
        column: paired_correlation(cost, group[column])
        for column in ["final_cursor_error_deg", "final_aftereffect_deg"]
    }
    return {
        "participants": len(group),
        "per_participant_exposure": exposure,
        "outcomes": {column: mean_interval(group[column]) for column in outcomes},
        "spearman_with_transition_error": correlations,
    }


def compare_aftereffects(people):
    groups = [people.loc[name, "final_aftereffect_deg"].to_numpy() for name in GROUPS]
    omnibus = stats.f_oneway(*groups)
    grand_mean = np.concatenate(groups).mean()
    between = sum(len(values) * (values.mean() - grand_mean) ** 2 for values in groups)
    total = sum(np.square(values - grand_mean).sum() for values in groups)
    anova = {
        "df_between": len(groups) - 1, "df_within": len(people) - len(groups),
        "F": float(omnibus.statistic), "p": float(omnibus.pvalue),
        "eta_squared": float(between / total),
    }
    tukey = stats.tukey_hsd(*groups)
    ci = tukey.confidence_interval()
    names = list(GROUPS)
    contrasts = {}
    for i, j in [(2, 0), (2, 1), (0, 1)]:
        contrasts[f"{names[i]}_minus_{names[j]}"] = {
            "difference_deg": float(tukey.statistic[i, j]),
            "simultaneous_ci95_deg": [float(ci.low[i, j]), float(ci.high[i, j])],
            "adjusted_p": float(tukey.pvalue[i, j]),
        }
    return {"one_way_anova": anova, "tukey_kramer": contrasts}


def plot_results(groups, destination):
    panels = [
        ("Transition cost", "Blocks 1–3 · cursor", "transition_error_deg_reaches", "Cumulative absolute error (°·reach)"),
        ("Final cursor error", "Block 4 · cursor", "final_cursor_error_deg", "Mean absolute error (°)"),
        ("Aftereffect", "Block 4 · no cursor, exclude strategy", "final_aftereffect_deg", "Mean signed hand deviation (°)"),
    ]
    colors = ["#246189", "#9e5318", "#187263"]
    with plt.rc_context({"svg.fonttype": "none", "svg.hashsalt": "augneta-visuomotor-v1",
                         "font.family": "DejaVu Sans", "font.size": 10}):
        fig, axes = plt.subplots(1, 3, figsize=(10.4, 3.45), sharey=True)
        fig.subplots_adjust(left=.144, right=.985, bottom=.24, top=.72, wspace=.29)
        fig.suptitle("Rotation training and the common 60° test", x=.02, y=.98, ha="left",
                     fontsize=16, fontweight="bold", color="#172d3d")
        for ax, (title, phase, outcome, unit) in zip(axes, panels):
            ax.set_title(title, fontsize=12, fontweight="bold", loc="left", pad=21)
            ax.text(0, 1.05, phase, transform=ax.transAxes, fontsize=8.5, color="#405563")
            summaries = [group["outcomes"][outcome] for group in groups.values()]
            for row, (summary, color) in enumerate(zip(summaries, colors)):
                low, high = summary["ci95"]
                ax.hlines(row, low, high, color=color, linewidth=2.5)
                ax.scatter(summary["mean"], row, color=color, s=43, zorder=3)
            ax.set_xlim(0, max(s["ci95"][1] for s in summaries) * 1.08)
            ax.set_ylim(2.55, -.55)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
            ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.set_axisbelow(True)
            ax.grid(axis="x", color="#dfe5e8", linewidth=.8)
            ax.spines[["top", "right", "left"]].set_visible(False)
            ax.spines["bottom"].set_color("#9ba9af")
            ax.tick_params(length=0, labelsize=9)
            ax.set_xlabel(unit, fontsize=9, labelpad=6)
        labels = [f"{GROUPS[name]}  (n = {groups[name]['participants']})" for name in groups]
        axes[0].set_yticks(range(len(groups)), labels)
        fig.text(.02, .038, "Points show group means. Lines show 95% confidence intervals across participants.",
                 fontsize=9, color="#405563")
        svg = StringIO()
        fig.savefig(svg, format="svg", metadata={"Date": None, "Creator": "Augneta"})
        plt.close(fig)
        lines = (line.rstrip() for line in svg.getvalue().splitlines())
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="OSF v1 bl_corrected_data.csv")
    parser.add_argument("--out", type=Path, required=True, help="Directory for the aggregate JSON and SVG")
    args = parser.parse_args()
    trials, audit = load_trials(args.data)
    people = participant_measures(trials)
    groups = {name: summarize_group(people.loc[name]) for name in GROUPS}
    results = {
        "source": SOURCE, "audit": audit, "groups": groups,
        "correlation_bootstrap": {"participant_resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED},
        "final_without_strategy_test": compare_aftereffects(people),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    plot_results(groups, args.out / "figure.svg")
    (args.out / "results.json").write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
