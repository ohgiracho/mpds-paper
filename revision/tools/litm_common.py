from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_NAME = "lost_in_middle_position_control_v1.json"
RECORD_START_RE = re.compile(rb"(?m)^ID:\s*(\d+)\s*\r?$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_config(revision_root: Path, config_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    resolved = (config_path or revision_root / "config" / DEFAULT_CONFIG_NAME).resolve()
    return resolved, read_json(resolved)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def decode_bytes(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def split_knowledge_bytes(payload: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    matches = list(RECORD_START_RE.finditer(payload))
    if not matches:
        raise ValueError("No evidence records beginning with 'ID: <n>' were found")
    header = payload[: matches[0].start()]
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, match in enumerate(matches):
        paper_id = int(match.group(1))
        if paper_id in seen:
            raise ValueError(f"Duplicate evidence ID: {paper_id}")
        seen.add(paper_id)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(payload)
        record = payload[match.start() : end]
        records.append(
            {
                "canonical_index": index + 1,
                "paper_id": paper_id,
                "bytes": record,
                "byte_count": len(record),
                "character_count": len(decode_bytes(record)),
                "sha256": sha256_bytes(record),
            }
        )
    return header, records


def optimal_three_way_contiguous_split(records: list[dict[str, Any]]) -> tuple[int, int]:
    if len(records) < 3:
        raise ValueError("At least three evidence records are required")
    lengths = [int(record["character_count"]) for record in records]
    prefix = [0]
    for length in lengths:
        prefix.append(prefix[-1] + length)
    total = prefix[-1]
    target = total / 3.0
    best: tuple[tuple[float, int, int, int, int], tuple[int, int]] | None = None
    for first in range(1, len(records) - 1):
        first_sum = prefix[first]
        for second in range(first + 1, len(records)):
            sums = (first_sum, prefix[second] - first_sum, total - prefix[second])
            counts = (first, second - first, len(records) - second)
            objective = (
                sum((value - target) ** 2 for value in sums),
                max(sums) - min(sums),
                max(counts) - min(counts),
                first,
                second,
            )
            if best is None or objective < best[0]:
                best = (objective, (first, second))
    if best is None:
        raise RuntimeError("Failed to compute three-way split")
    return best[1]


def input_pool_dir(revision_root: Path, config: dict[str, Any], case_id: int, pool: str) -> Path:
    return (
        revision_root
        / str(config["inputs"]["input_root"])
        / f"case_{case_id:02d}"
        / f"pool_{pool.upper()}"
    )


def ordered_knowledge_path(
    revision_root: Path, config: dict[str, Any], case_id: int, pool: str, ordering: str
) -> Path:
    return input_pool_dir(revision_root, config, case_id, pool) / f"knowledge_order_{ordering}.txt"


def pool_manifest_path(
    revision_root: Path, config: dict[str, Any], case_id: int, pool: str
) -> Path:
    return input_pool_dir(revision_root, config, case_id, pool) / "block_manifest.json"


def environment_value(name: str) -> str:
    value = (os.getenv(name) or "").strip().strip("\"'")
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            stored, _ = winreg.QueryValueEx(key, name)
        return str(stored or "").strip().strip("\"'")
    except (FileNotFoundError, OSError, ImportError):
        return ""
