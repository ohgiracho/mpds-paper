from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")
LABELS = {"raw": "Raw", "eo": "EO", "eop": "EOP", "ds": "DS", "mpds": "MPDS"}
COLORS = {
    "raw": "#7A7A7A",
    "eo": "#56B4E9",
    "eop": "#009E73",
    "ds": "#E69F00",
    "mpds": "#0072B2",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparison_row(rows: list[dict[str, str]], metric: str, comparison: str) -> dict[str, str]:
    matches = [row for row in rows if row["metric"] == metric and row["comparison"] == comparison]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one row for {metric}, {comparison}; found {len(matches)}")
    return matches[0]


def paired_difference_panel(
    axis: plt.Axes,
    lookup: dict[tuple[int, str], dict[str, str]],
    case_ids: list[int],
    metric: str,
    comparison: dict[str, str],
    title: str,
    letter: str,
) -> None:
    differences = np.array(
        [float(lookup[(case_id, "mpds")][metric]) - float(lookup[(case_id, "ds")][metric]) for case_id in case_ids]
    )
    y_positions = np.arange(len(case_ids), 0, -1)
    for case_id, difference, y_position in zip(case_ids, differences, y_positions):
        color = "#0072B2" if difference > 0 else "#D55E00" if difference < 0 else "#7A7A7A"
        axis.plot([0, difference], [y_position, y_position], color=color, linewidth=1.5, alpha=0.75)
        axis.scatter(difference, y_position, color=color, s=34, zorder=3, edgecolor="white", linewidth=0.5)

    mean = float(comparison["mean_difference"])
    low = float(comparison["bootstrap_95ci_low"])
    high = float(comparison["bootstrap_95ci_high"])
    axis.errorbar(
        mean,
        0,
        xerr=np.array([[mean - low], [high - mean]]),
        fmt="D",
        color="#111111",
        capsize=4,
        markersize=6,
        linewidth=1.8,
        label="Mean difference (95% CI)",
    )
    axis.axvline(0, color="#444444", linewidth=1, linestyle="--")
    axis.set_yticks([*y_positions, 0])
    axis.set_yticklabels([*[f"Case {case_id}" for case_id in case_ids], "Mean"])
    axis.set_xlabel("MPDS − DS (points)")
    axis.set_title(f"{letter}  {title}", loc="left", fontweight="bold")
    axis.grid(axis="x", color="#D9D9D9", linewidth=0.6, alpha=0.8)
    axis.set_axisbelow(True)
    axis.text(
        0.02,
        0.02,
        f"Mean {mean:+.2f} [{low:+.2f}, {high:+.2f}]\nExact sign-flip p={float(comparison['sign_flip_p_exact']):.4f}",
        transform=axis.transAxes,
        fontsize=8.5,
        va="bottom",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "#BBBBBB", "alpha": 0.9},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a publication-ready summary figure for the core 10-case Pass 1 analysis.")
    parser.add_argument("--case-means", type=Path, required=True)
    parser.add_argument("--pairwise", type=Path, required=True)
    parser.add_argument("--output-stem", type=Path, required=True)
    args = parser.parse_args()

    case_rows = read_csv(args.case_means.resolve())
    pairwise_rows = read_csv(args.pairwise.resolve())
    if len(case_rows) != 50:
        raise RuntimeError(f"Expected 50 case-condition rows; found {len(case_rows)}")
    lookup = {(int(row["case_id"]), row["condition"]): row for row in case_rows}
    case_ids = sorted({int(row["case_id"]) for row in case_rows})
    if len(case_ids) != 10:
        raise RuntimeError(f"Expected 10 cases; found {len(case_ids)}")

    primary = comparison_row(pairwise_rows, "ihq_without_cpi", "mpds - ds")
    validity = comparison_row(pairwise_rows, "validity_composite_descriptive", "mpds - ds")

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(12.2, 4.5), gridspec_kw={"width_ratios": [1.05, 1, 1]})

    condition_values = {
        condition: np.array([float(lookup[(case_id, condition)]["ihq_without_cpi"]) for case_id in case_ids])
        for condition in CONDITIONS
    }
    positions = np.arange(1, len(CONDITIONS) + 1)
    box = axes[0].boxplot(
        [condition_values[condition] for condition in CONDITIONS],
        positions=positions,
        widths=0.55,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": "#111111", "linewidth": 1.4},
        whiskerprops={"color": "#777777"},
        capprops={"color": "#777777"},
    )
    for patch, condition in zip(box["boxes"], CONDITIONS):
        patch.set_facecolor(COLORS[condition])
        patch.set_alpha(0.25)
        patch.set_edgecolor(COLORS[condition])
    offsets = np.linspace(-0.14, 0.14, len(case_ids))
    for index, condition in enumerate(CONDITIONS, start=1):
        values = condition_values[condition]
        axes[0].scatter(
            index + offsets,
            values,
            color=COLORS[condition],
            s=28,
            alpha=0.9,
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
        )
        axes[0].scatter(index, values.mean(), marker="D", color="#111111", s=34, zorder=4)
    axes[0].set_xticks(positions)
    axes[0].set_xticklabels([LABELS[condition] for condition in CONDITIONS])
    axes[0].set_ylabel("IHQ without CPI (0–15)")
    axes[0].set_ylim(0, 15)
    axes[0].set_title("A  Condition-level case means", loc="left", fontweight="bold")
    axes[0].grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.8)
    axes[0].set_axisbelow(True)
    axes[0].text(
        0.02,
        0.02,
        "Dots: case means across 3 replicates\nDiamonds: condition means",
        transform=axes[0].transAxes,
        fontsize=8.5,
        va="bottom",
    )

    paired_difference_panel(
        axes[1],
        lookup,
        case_ids,
        "ihq_without_cpi",
        primary,
        "Primary IHQ contrast",
        "B",
    )
    paired_difference_panel(
        axes[2],
        lookup,
        case_ids,
        "validity_composite_descriptive",
        validity,
        "Supplementary validity contrast",
        "C",
    )

    figure.suptitle(
        "Core 10-case stochastic replication: blinded Pass 1 evaluation",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    figure.text(
        0.5,
        -0.01,
        "Case means are the inferential units; replicate outputs are not treated as independent cases. CPI, Cross-Perspective Integration.",
        ha="center",
        fontsize=8.5,
    )
    figure.tight_layout(w_pad=2.0)

    output_stem = args.output_stem.resolve()
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    figure.savefig(output_stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)
    manifest = {
        "status": "PASS",
        "figure": "Core 10-case blinded Pass 1 summary",
        "analysis_unit": "case mean across three replicates",
        "case_means": str(args.case_means.resolve()),
        "case_means_sha256": sha256_file(args.case_means.resolve()),
        "pairwise": str(args.pairwise.resolve()),
        "pairwise_sha256": sha256_file(args.pairwise.resolve()),
        "png": str(output_stem.with_suffix(".png")),
        "png_sha256": sha256_file(output_stem.with_suffix(".png")),
        "pdf": str(output_stem.with_suffix(".pdf")),
        "pdf_sha256": sha256_file(output_stem.with_suffix(".pdf")),
    }
    output_stem.with_name(f"{output_stem.name}_manifest").with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output_stem.with_suffix(".png"))
    print(output_stem.with_suffix(".pdf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
