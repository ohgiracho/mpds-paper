from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import linalg, optimize, stats


METRICS = ("ihq_without_cpi", "full_ihq", "validity_composite_descriptive")
CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")
DUMMY_CONDITIONS = ("raw", "eo", "eop", "mpds")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fit_random_intercept_model(
    y: np.ndarray,
    design: np.ndarray,
    same_case: np.ndarray,
    same_packet: np.ndarray,
) -> dict[str, Any]:
    n = len(y)
    identity = np.eye(n)

    def evaluate(log_variances: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        case_var, packet_var, residual_var = np.exp(log_variances)
        covariance = case_var * same_case + packet_var * same_packet + residual_var * identity
        chol = linalg.cho_factor(covariance, lower=True, check_finite=False)
        vinv_x = linalg.cho_solve(chol, design, check_finite=False)
        vinv_y = linalg.cho_solve(chol, y, check_finite=False)
        information = design.T @ vinv_x
        beta = linalg.solve(information, design.T @ vinv_y, assume_a="sym")
        residual = y - design @ beta
        quadratic = float(residual @ linalg.cho_solve(chol, residual, check_finite=False))
        logdet = 2.0 * float(np.log(np.diag(chol[0])).sum())
        nll = 0.5 * (n * np.log(2.0 * np.pi) + logdet + quadratic)
        return nll, beta, information, np.array([case_var, packet_var, residual_var])

    initial = np.log([0.25, 0.25, max(float(np.var(y)), 0.25)])
    result = optimize.minimize(
        lambda theta: evaluate(theta)[0],
        initial,
        method="L-BFGS-B",
        bounds=[(-16.0, 8.0), (-16.0, 8.0), (-16.0, 8.0)],
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    nll, beta, information, variances = evaluate(result.x)
    beta_covariance = linalg.inv(information)
    standard_errors = np.sqrt(np.diag(beta_covariance))
    z_scores = beta / standard_errors
    p_values = 2.0 * stats.norm.sf(np.abs(z_scores))
    return {
        "converged": bool(result.success),
        "message": str(result.message),
        "nll": nll,
        "beta": beta,
        "standard_errors": standard_errors,
        "p_values": p_values,
        "variances": variances,
        "aic": 2.0 * (len(beta) + 3) + 2.0 * nll,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prespecified output-length sensitivity analysis")
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    scores = read_csv(args.scores.resolve())
    key = read_csv(args.blind_key.resolve())
    lengths = {(row["packet_id"], row["alias"]): int(row["output_characters"]) for row in key}
    data_rows: list[dict[str, Any]] = []
    for row in scores:
        chars = lengths[(row["packet_id"], row["alias"])]
        data_rows.append(
            {
                **row,
                "output_characters": chars,
                "log_output_characters": float(np.log(chars)),
                **{metric: float(row[metric]) for metric in METRICS},
            }
        )
    log_lengths = np.array([row["log_output_characters"] for row in data_rows])
    centered = log_lengths - log_lengths.mean()
    for row, value in zip(data_rows, centered):
        row["log_length_centered"] = float(value)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "scores_with_output_length.csv", data_rows)

    length_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        values = np.array([row["output_characters"] for row in data_rows if row["condition"] == condition], dtype=float)
        length_summary.append(
            {
                "condition": condition,
                "n": len(values),
                "mean_characters": float(values.mean()),
                "sd_characters": float(values.std(ddof=1)),
                "median_characters": float(np.median(values)),
                "q1_characters": float(np.quantile(values, 0.25)),
                "q3_characters": float(np.quantile(values, 0.75)),
            }
        )
    write_csv(output / "output_length_summary.csv", length_summary)

    n = len(data_rows)
    design_columns = ["intercept", *[f"condition_{condition}" for condition in DUMMY_CONDITIONS], "log_length_centered"]
    design = np.column_stack(
        [
            np.ones(n),
            *[np.array([float(row["condition"] == condition) for row in data_rows]) for condition in DUMMY_CONDITIONS],
            centered,
        ]
    )
    case_ids = np.array([str(row["case_id"]) for row in data_rows])
    packet_ids = np.array([row["packet_id"] for row in data_rows])
    same_case = (case_ids[:, None] == case_ids[None, :]).astype(float)
    same_packet = (packet_ids[:, None] == packet_ids[None, :]).astype(float)

    result_rows: list[dict[str, Any]] = []
    variance_rows: list[dict[str, Any]] = []
    for metric in METRICS:
        y = np.array([row[metric] for row in data_rows], dtype=float)
        fitted = fit_random_intercept_model(y, design, same_case, same_packet)
        for index, term in enumerate(design_columns):
            estimate = float(fitted["beta"][index])
            standard_error = float(fitted["standard_errors"][index])
            result_rows.append(
                {
                    "metric": metric,
                    "term": "mpds_minus_ds" if term == "condition_mpds" else term,
                    "estimate": estimate,
                    "standard_error": standard_error,
                    "ci95_low": estimate - 1.959964 * standard_error,
                    "ci95_high": estimate + 1.959964 * standard_error,
                    "p_value_asymptotic": float(fitted["p_values"][index]),
                    "converged": fitted["converged"],
                    "n_rows": n,
                    "aic": float(fitted["aic"]),
                }
            )
        variance_rows.append(
            {
                "metric": metric,
                "case_intercept_variance": float(fitted["variances"][0]),
                "packet_intercept_variance": float(fitted["variances"][1]),
                "residual_variance": float(fitted["variances"][2]),
                "converged": fitted["converged"],
                "optimizer_message": fitted["message"],
            }
        )
    write_csv(output / "length_adjusted_mixed_models.csv", result_rows)
    write_csv(output / "length_adjusted_variance_components.csv", variance_rows)

    summary = {
        "status": "PASS" if all(row["converged"] for row in variance_rows) else "WARNING",
        "rows": n,
        "formula": "score ~ condition (DS reference) + centered log output characters",
        "random_effects": "random intercept covariance for case and nested case-replicate packet",
        "estimation": "custom Gaussian maximum likelihood using SciPy",
        "inference_note": "Asymptotic model p-values are sensitivity-only; exact case-level sign-flip is primary.",
        "metrics": list(METRICS),
    }
    (output / "length_sensitivity_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
