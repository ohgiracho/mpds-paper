from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


DIMENSIONS = (
    "tension_recognition",
    "adaptive_revision",
    "tradeoff_resolution",
    "nonadditive_synthesis",
)
CONDITIONS = ("ds", "mpds", "sair", "ses")
ALIASES = ("Trajectory A", "Trajectory B", "Trajectory C", "Trajectory D")
EVENT_TYPES = {
    "mechanism_revision",
    "architecture_revision",
    "processing_revision",
    "feasibility_constraint",
    "performance_tradeoff",
    "evidence_interpretation",
    "rejection_of_initial_assumption",
    "other",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_config(root: Path, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    config_path = (path or root / "config" / "trajectory_analysis_core10_v1.json").resolve()
    return config_path, json.loads(config_path.read_text(encoding="utf-8"))


def resolve_from_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write an empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_space(value: str) -> str:
    return " ".join(value.replace("\r\n", "\n").replace("\r", "\n").split())
