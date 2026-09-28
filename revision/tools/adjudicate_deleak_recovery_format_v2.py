from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from run_deleak_target_recovery_anthropic import FEATURES, LABELS, packet_content, read_json, validate
from run_independent_judge_anthropic_v3 import extract_tool_input


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[*_`~]", "", value).split()).casefold()


def quote_supported(excerpt: str, answer: str) -> tuple[bool, str]:
    quote = normalize_text(excerpt)
    source = normalize_text(answer)
    if quote in source:
        return True, "exact_after_markdown_whitespace_normalization"
    if "..." in quote:
        segments = [part.strip() for part in quote.split("...") if part.strip()]
        if segments and all(len(part) >= 12 and part in source for part in segments):
            return True, "all_ellipsis_segments_present"
    match = difflib.SequenceMatcher(None, quote, source, autojunk=False).find_longest_match(0, len(quote), 0, len(source))
    if match.size >= 30 and match.size / max(len(quote), 1) >= 0.45:
        return True, "long_literal_fragment_present"
    return False, "no_sufficient_literal_support"


def derived_overall(case_id: int, labels: dict[str, str]) -> str:
    if case_id == 1:
        explicit = labels["combined_dual_allocation"] == "explicit_target_like" and labels["surface_lpscl_contact"] != "absent" and labels["interstitial_lpscl_network"] != "absent"
    elif case_id == 8:
        explicit = labels["combined_cube_wall_graphene_architecture"] == "explicit_target_like"
    elif case_id == 22:
        explicit = labels["nested_inner_outer_tubes"] == "explicit_target_like" and labels["internal_void_as_strain_buffer"] != "absent"
    else:
        raise RuntimeError(f"Unexpected case ID: {case_id}")
    return "explicit_target_like" if explicit else "partial_general" if any(label != "absent" for label in labels.values()) else "absent"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result_dir = root / "results" / "deleak_target_recovery_sonnet5_v1"
    packet_dir = root / "evaluation" / "blind_packets_deleak_target_recovery_v1"
    output = root / "analysis" / "deleak_recovery_blind_format_adjudication_v2.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite adjudication: {output}")
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for packet in sorted(packet_dir.glob("audit_*.md")):
        audit_id = packet.stem
        case_id, answer = packet_content(packet)
        manifest = read_json(result_dir / audit_id / "run_manifest.json")
        attempt = len(manifest["attempts"])
        response_path = result_dir / audit_id / f"attempt_{attempt:02d}_response.json"
        response = read_json(response_path)
        if manifest["attempts"][-1].get("returned_model") != "claude-sonnet-5":
            failed.append({"audit_id": audit_id, "error": "Returned model mismatch"})
            continue
        data, _ = extract_tool_input(response, "submit_target_recovery")
        original_errors = validate(data, audit_id, case_id, answer)
        structural_errors = [error for error in original_errors if not (error.startswith("Overall label contradicts") or error.startswith("Non-absent feature requires an exact supporting excerpt") or error.startswith("Absent feature requires excerpt 'none'"))]
        if structural_errors:
            failed.append({"audit_id": audit_id, "error": structural_errors})
            continue
        features: list[dict[str, Any]] = []
        unsupported: list[str] = []
        labels: dict[str, str] = {}
        for feature in data["features"]:
            feature_id, label, excerpt = feature["feature_id"], feature["label"], feature["excerpt"]
            if feature_id not in FEATURES[case_id] or label not in LABELS:
                unsupported.append(str(feature_id))
                continue
            labels[feature_id] = label
            if label == "absent":
                supported, method = True, "not_applicable_absent"
            else:
                supported, method = quote_supported(excerpt, answer)
            if not supported:
                unsupported.append(feature_id)
            features.append({"feature_id": feature_id, "label": label, "model_excerpt": excerpt, "excerpt_support_method": method})
        if unsupported or set(labels) != set(FEATURES[case_id]):
            failed.append({"audit_id": audit_id, "error": "unsupported or incomplete feature evidence", "features": unsupported})
            continue
        overall = derived_overall(case_id, labels)
        rows.append({
            "audit_id": audit_id, "case_id": case_id, "source_attempt": attempt,
            "source_response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
            "strict_original_status": manifest["status"],
            "strict_original_validation_errors": original_errors,
            "features": features,
            "model_overall_recovery": data["overall_recovery"],
            "rubric_derived_overall_recovery": overall,
            "overall_was_corrected": data["overall_recovery"] != overall,
            "feature_labels_changed": False,
            "rationale": data["rationale"],
        })
    if len(rows) + len(failed) != 18:
        raise RuntimeError("Did not account for all 18 blind recovery packets")
    result = {
        "status": "PASS" if len(rows) == 18 and not failed else "NEEDS_REVIEW",
        "scope": "condition-blind post-format adjudication; no new API calls",
        "protocol_basis": "protocol/deleak_target_recovery_anthropic_v1.md",
        "selection_rule": "last returned tool response for every audit packet, regardless of strict original status",
        "feature_labels_changed": False,
        "accepted": len(rows), "needs_review": failed,
        "strict_complete_original": sum(row["strict_original_status"] == "COMPLETE" for row in rows),
        "overall_corrections": sum(row["overall_was_corrected"] for row in rows),
        "rows": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
