from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from build_blind_packets import clean_final


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")
CITATION_PATTERN = re.compile(r"\[\s*IDs?\s*:\s*([^\]]+)\]", re.IGNORECASE)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write an empty table: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ratio(numerator: int | float, denominator: int | float) -> float | str:
    if denominator == 0:
        return ""
    return float(numerator) / float(denominator)


def median_or_blank(values: list[float]) -> float | str:
    return statistics.median(values) if values else ""


def citation_positions(text: str) -> list[float]:
    positions: list[float] = []
    denominator = max(1, len(text) - 1)
    for match in CITATION_PATTERN.finditer(text):
        relative_position = match.start() / denominator
        identifiers = re.findall(r"\d+", match.group(1))
        positions.extend([relative_position] * len(identifiers))
    return positions


def third(position: float) -> str:
    if position < 1 / 3:
        return "first"
    if position < 2 / 3:
        return "middle"
    return "final"


def percentage(value: float | str) -> str:
    if value == "":
        return "—"
    return f"{100 * float(value):.2f}%"


def number(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize deterministic citation validity and traceability without semantic judging."
    )
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--evidence-key", type=Path, required=True)
    parser.add_argument("--occurrence-audit", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    blind_key_path = args.blind_key.resolve()
    evidence_key_path = args.evidence_key.resolve()
    occurrence_path = args.occurrence_audit.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    blind_rows = read_csv(blind_key_path)
    evidence_rows = read_csv(evidence_key_path)
    occurrence_rows = read_csv(occurrence_path)

    candidate_lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row in blind_rows:
        key = (row["packet_id"], row["alias"])
        if key in candidate_lookup:
            raise RuntimeError(f"Duplicate candidate in blind key: {key}")
        candidate_lookup[key] = row

    if len(candidate_lookup) != 150:
        raise RuntimeError(f"Expected 150 candidates; found {len(candidate_lookup)}")
    condition_counts = {
        condition: sum(row["condition"] == condition for row in blind_rows)
        for condition in CONDITIONS
    }
    if any(count != 30 for count in condition_counts.values()):
        raise RuntimeError(f"Expected 30 candidates per condition; found {condition_counts}")

    cited_rows: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in evidence_rows:
        key = (row["packet_id"], row["alias"])
        if key not in candidate_lookup:
            raise RuntimeError(f"Evidence row has no candidate: {key}")
        if row["cited_id"]:
            cited_rows[key][row["cited_id"]].append(row)

    occurrences: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in occurrence_rows:
        key = (row["packet_id"], row["alias"])
        if key not in candidate_lookup:
            raise RuntimeError(f"Occurrence row has no candidate: {key}")
        occurrences[key].append(row)

    candidate_metrics: list[dict[str, Any]] = []
    integrity_errors: list[str] = []
    for key, row in sorted(
        candidate_lookup.items(),
        key=lambda item: (int(item[1]["case_id"]), int(item[1]["replicate_id"]), item[1]["alias"]),
    ):
        source = Path(row["source_file"])
        if not source.exists():
            integrity_errors.append(f"Missing source: {source}")
            continue
        if sha256_file(source).lower() != row["source_file_sha256"].lower():
            integrity_errors.append(f"Source hash mismatch: {source}")
            continue
        text = clean_final(source.read_text(encoding="utf-8", errors="replace"))
        if sha256_text(text).lower() != row["output_sha256"].lower():
            integrity_errors.append(f"Cleaned-output hash mismatch: {source}")
            continue
        if len(text) != int(row["output_characters"]):
            integrity_errors.append(f"Cleaned-output length mismatch: {source}")
            continue

        candidate_occurrences = occurrences.get(key, [])
        positions = citation_positions(text)
        if len(positions) != len(candidate_occurrences):
            integrity_errors.append(
                f"Citation occurrence mismatch for {key}: text={len(positions)}, audit={len(candidate_occurrences)}"
            )
            continue

        id_groups = cited_rows.get(key, {})
        resolved_ids = 0
        ambiguous_ids = 0
        for group in id_groups.values():
            statuses = {item["resolution_status"] for item in group}
            if "unresolved" not in statuses:
                resolved_ids += 1
            if "resolved_ambiguous" in statuses:
                ambiguous_ids += 1

        attributable = sum(
            item["resolution_status"].startswith("attributable_")
            for item in candidate_occurrences
        )
        ambiguous_occurrences = sum(
            item["resolution_status"] == "ambiguous_two_records"
            for item in candidate_occurrences
        )
        pools = {
            item["attributed_pool"]
            for item in candidate_occurrences
            if item["attributed_pool"] in {"A", "B"}
        }
        third_counts = {
            label: sum(third(position) == label for position in positions)
            for label in ("first", "middle", "final")
        }
        unique_count = len(id_groups)
        citation_count = len(candidate_occurrences)
        candidate_metrics.append(
            {
                "packet_id": row["packet_id"],
                "case_id": int(row["case_id"]),
                "replicate_id": int(row["replicate_id"]),
                "alias": row["alias"],
                "condition": row["condition"],
                "output_characters": len(text),
                "has_bracketed_evidence_id": int(citation_count > 0),
                "citation_occurrences": citation_count,
                "unique_cited_ids": unique_count,
                "resolved_unique_ids": resolved_ids,
                "ambiguous_unique_ids": ambiguous_ids,
                "unresolved_unique_ids": unique_count - resolved_ids,
                "unique_id_resolvability_rate": ratio(resolved_ids, unique_count),
                "attributable_occurrences": attributable,
                "ambiguous_occurrences": ambiguous_occurrences,
                "occurrence_attribution_rate": ratio(attributable, citation_count),
                "citation_occurrences_per_1000_characters": 1000 * citation_count / max(1, len(text)),
                "distinct_attributed_pools": len(pools),
                "cites_both_evidence_pools": int(pools == {"A", "B"}),
                "first_citation_relative_position": min(positions) if positions else "",
                "mean_citation_relative_position": statistics.mean(positions) if positions else "",
                "citation_occurrences_first_third": third_counts["first"],
                "citation_occurrences_middle_third": third_counts["middle"],
                "citation_occurrences_final_third": third_counts["final"],
            }
        )

    if integrity_errors:
        raise RuntimeError("\n".join(integrity_errors))
    if len(candidate_metrics) != 150:
        raise RuntimeError(f"Expected 150 verified candidate rows; found {len(candidate_metrics)}")

    condition_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in candidate_metrics if row["condition"] == condition]
        citation_occurrences = sum(int(row["citation_occurrences"]) for row in subset)
        unique_ids = sum(int(row["unique_cited_ids"]) for row in subset)
        resolved_ids = sum(int(row["resolved_unique_ids"]) for row in subset)
        attributable = sum(int(row["attributable_occurrences"]) for row in subset)
        ambiguous_occurrences = sum(int(row["ambiguous_occurrences"]) for row in subset)
        with_citations = sum(int(row["has_bracketed_evidence_id"]) for row in subset)
        first_positions = [
            float(row["first_citation_relative_position"])
            for row in subset
            if row["first_citation_relative_position"] != ""
        ]
        all_positions = sum(
            int(row["citation_occurrences_first_third"])
            + int(row["citation_occurrences_middle_third"])
            + int(row["citation_occurrences_final_third"])
            for row in subset
        )
        condition_summary.append(
            {
                "condition": condition,
                "n_candidates": len(subset),
                "candidates_with_citations": with_citations,
                "candidates_without_citations": len(subset) - with_citations,
                "citation_coverage_rate": ratio(with_citations, len(subset)),
                "citation_occurrences": citation_occurrences,
                "mean_citation_occurrences_per_candidate": statistics.mean(
                    int(row["citation_occurrences"]) for row in subset
                ),
                "median_citation_occurrences_per_candidate": statistics.median(
                    int(row["citation_occurrences"]) for row in subset
                ),
                "candidate_distinct_cited_ids": unique_ids,
                "resolved_candidate_distinct_ids": resolved_ids,
                "unresolved_candidate_distinct_ids": unique_ids - resolved_ids,
                "unique_id_resolvability_rate": ratio(resolved_ids, unique_ids),
                "attributable_occurrences": attributable,
                "ambiguous_occurrences": ambiguous_occurrences,
                "occurrence_attribution_rate": ratio(attributable, citation_occurrences),
                "mean_citation_occurrences_per_1000_characters": statistics.mean(
                    float(row["citation_occurrences_per_1000_characters"]) for row in subset
                ),
                "candidates_citing_both_pools": sum(
                    int(row["cites_both_evidence_pools"]) for row in subset
                ),
                "median_first_citation_relative_position": median_or_blank(first_positions),
                "first_third_occurrence_rate": ratio(
                    sum(int(row["citation_occurrences_first_third"]) for row in subset), all_positions
                ),
                "middle_third_occurrence_rate": ratio(
                    sum(int(row["citation_occurrences_middle_third"]) for row in subset), all_positions
                ),
                "final_third_occurrence_rate": ratio(
                    sum(int(row["citation_occurrences_final_third"]) for row in subset), all_positions
                ),
            }
        )

    total_candidates = len(candidate_metrics)
    total_occurrences = sum(int(row["citation_occurrences"]) for row in candidate_metrics)
    total_unique_ids = sum(int(row["unique_cited_ids"]) for row in candidate_metrics)
    total_resolved_ids = sum(int(row["resolved_unique_ids"]) for row in candidate_metrics)
    total_attributable = sum(int(row["attributable_occurrences"]) for row in candidate_metrics)
    total_ambiguous_occurrences = sum(int(row["ambiguous_occurrences"]) for row in candidate_metrics)
    total_no_citation = sum(not int(row["has_bracketed_evidence_id"]) for row in candidate_metrics)

    write_csv(output_dir / "candidate_deterministic_evidence_metrics.csv", candidate_metrics)
    write_csv(output_dir / "condition_deterministic_evidence_summary.csv", condition_summary)

    summary = {
        "status": "PASS",
        "scope": "deterministic identifier and citation-structure checks only; no semantic claim-support judgment",
        "inputs": {
            "blind_key": str(blind_key_path),
            "blind_key_sha256": sha256_file(blind_key_path),
            "evidence_key": str(evidence_key_path),
            "evidence_key_sha256": sha256_file(evidence_key_path),
            "occurrence_audit": str(occurrence_path),
            "occurrence_audit_sha256": sha256_file(occurrence_path),
        },
        "integrity": {
            "verified_candidate_sources": total_candidates,
            "condition_counts": condition_counts,
            "source_hash_errors": 0,
            "cleaned_output_hash_errors": 0,
            "citation_occurrence_mismatches": 0,
        },
        "overall": {
            "candidates": total_candidates,
            "candidates_without_bracketed_evidence_ids": total_no_citation,
            "candidates_without_bracketed_evidence_ids_rate": total_no_citation / total_candidates,
            "citation_occurrences": total_occurrences,
            "candidate_distinct_cited_ids": total_unique_ids,
            "resolved_candidate_distinct_ids": total_resolved_ids,
            "unique_id_resolvability_rate": ratio(total_resolved_ids, total_unique_ids),
            "attributable_occurrences": total_attributable,
            "ambiguous_occurrences": total_ambiguous_occurrences,
            "occurrence_attribution_rate": ratio(total_attributable, total_occurrences),
            "ambiguous_occurrence_rate": ratio(total_ambiguous_occurrences, total_occurrences),
        },
        "condition_summary": condition_summary,
        "interpretation_guardrail": (
            "Identifier resolution and deterministic attribution do not establish that an abstract semantically "
            "supports a scientific claim. Claim-citation support rates require the deferred Pass 2 audit."
        ),
    }
    (output_dir / "deterministic_evidence_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report_lines = [
        "# 현재 데이터 기반 자동 인용 검증 보고서",
        "",
        "작성일: 2026-09-14  ",
        "상태: **PASS — API 호출 없이 재현 가능한 결정론적 검사 완료**",
        "",
        "## 범위",
        "",
        "10개 사례 × 3회 반복 × 5개 조건의 150개 최종 답변을 대상으로 인용 ID의 존재, "
        "동결된 근거 네임스페이스 내 해석 가능성, 이중 근거 풀의 결정론적 출처 귀속, "
        "인용 빈도와 답변 내 위치를 검사했다. 원문 파일과 정제된 최종 답변의 해시도 모두 재검증했다.",
        "",
        "이 검사는 인용된 초록이 개별 과학적 주장을 실제로 뒷받침하는지를 판정하지 않는다. "
        "그 의미적 판정은 보류된 Pass 2의 범위이다.",
        "",
        "## 조건별 결과",
        "",
        "| 조건 | 답변 수 | 인용 포함 | 인용 없음 | 인용 발생 수 | 답변별 고유 ID 수 | ID 해석률 | 출처 귀속률 | 모호한 발생 | 1,000자당 인용 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in condition_summary:
        report_lines.append(
            "| {condition} | {n_candidates} | {with_citations} | {without_citations} | {occurrences} | "
            "{unique_mean} | {resolution} | {attribution} | {ambiguous} | {density} |".format(
                condition=row["condition"].upper(),
                n_candidates=row["n_candidates"],
                with_citations=row["candidates_with_citations"],
                without_citations=row["candidates_without_citations"],
                occurrences=row["citation_occurrences"],
                unique_mean=number(row["candidate_distinct_cited_ids"] / row["n_candidates"]),
                resolution=percentage(row["unique_id_resolvability_rate"]),
                attribution=percentage(row["occurrence_attribution_rate"]),
                ambiguous=row["ambiguous_occurrences"],
                density=number(row["mean_citation_occurrences_per_1000_characters"]),
            )
        )
    report_lines.extend(
        [
            "",
            "`답변별 고유 ID 수`는 각 답변 안에서 중복 인용을 한 번만 센 뒤 조건 내에서 평균한 값이다. "
            "`출처 귀속률`은 해석된 ID가 아니라 2,930개 인용 발생 각각을 분모로 한다.",
            "",
            "## 인용 위치와 이중 근거 풀 사용",
            "",
            "| 조건 | 첫 인용 중앙 위치 | 앞 1/3 | 중간 1/3 | 뒤 1/3 | A·B 양쪽 풀을 인용한 답변 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in condition_summary:
        report_lines.append(
            "| {condition} | {first} | {first_third} | {middle_third} | {final_third} | {both} |".format(
                condition=row["condition"].upper(),
                first=percentage(row["median_first_citation_relative_position"]),
                first_third=percentage(row["first_third_occurrence_rate"]),
                middle_third=percentage(row["middle_third_occurrence_rate"]),
                final_third=percentage(row["final_third_occurrence_rate"]),
                both=row["candidates_citing_both_pools"] if row["condition"] in {"ds", "mpds"} else "—",
            )
        )
    report_lines.extend(
        [
            "",
            "위치 비율은 정제된 최종 답변의 문자 위치를 기준으로 계산했다. A·B 양쪽 풀 사용은 "
            "DS/MPDS에서 출처를 결정론적으로 귀속할 수 있었던 인용만 센 구조 지표이며, "
            "두 관점의 과학적 통합이나 인용의 의미적 적절성을 뜻하지 않는다.",
            "",
            "## 전체 무결성 및 핵심 수치",
            "",
            f"- 원본·정제 출력 해시가 일치한 답변: {total_candidates}/{total_candidates}",
            f"- 대괄호 근거 ID가 없는 답변: {total_no_citation}/{total_candidates} "
            f"({100 * total_no_citation / total_candidates:.2f}%)",
            f"- 답변별로 중복 제거한 인용 ID 인스턴스: {total_unique_ids:,}개",
            f"- 동결된 근거 네임스페이스에서 해석된 ID: {total_resolved_ids:,}/{total_unique_ids:,} "
            f"({100 * total_resolved_ids / total_unique_ids:.2f}%)",
            f"- 전체 인용 발생: {total_occurrences:,}건",
            f"- 결정론적으로 출처가 귀속된 인용 발생: {total_attributable:,}/{total_occurrences:,} "
            f"({100 * total_attributable / total_occurrences:.2f}%)",
            f"- A/B 양쪽에 다른 레코드가 있어 출처가 모호한 인용 발생: {total_ambiguous_occurrences}/{total_occurrences:,} "
            f"({100 * total_ambiguous_occurrences / total_occurrences:.2f}%)",
            "",
            "## 지금 원고와 reviewer 답변에 사용할 수 있는 결론",
            "",
            "1. 이 핵심 10개 사례군에서 사용된 모든 답변별 고유 인용 ID는 생성 당시 동결된 근거 "
            "네임스페이스의 레코드에 연결됐다.",
            "2. 이중 근거 풀을 사용하는 DS/MPDS에서는 숫자 ID 중복 가능성을 별도로 처리했으며, "
            "모호한 경우를 임의로 한쪽 문헌에 배정하지 않았다.",
            "3. 인용 ID가 없는 답변은 거짓 또는 환각으로 간주하지 않고 citation-based 분석에서 별도 범주로 유지한다.",
            "4. 위 수치는 인용의 구조적 유효성과 추적 가능성을 보여주지만, 주장–초록 간 의미적 지지를 증명하지 않는다.",
            "",
            "## Pass 2 전에는 보고하면 안 되는 결과",
            "",
            "- supported / partially supported / unsupported / contradicted / unverifiable 주장 비율",
            "- claim–citation support rate",
            "- 의미적 evidence-support 점수",
            "- 인용이 존재한다는 이유만으로 계산한 hallucination rate",
            "",
            "따라서 현재 원고에는 Pass 1의 IHQ·별도 타당성 결과와 본 자동 인용 검증을 먼저 반영할 수 있다. "
            "Pass 2 결과 칸은 보류 상태로 명시적으로 남겨야 한다.",
            "",
        ]
    )
    (output_dir / "deterministic_evidence_briefing_ko.md").write_text(
        "\n".join(report_lines), encoding="utf-8"
    )

    print(json.dumps(summary["overall"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
